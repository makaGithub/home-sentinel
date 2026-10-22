#!/usr/bin/env python3
"""
main.py — home-sentinel (CPU): RTSP/аудио, красивые логи, скриншоты.
GPU-инференс — удалённый hs-gpu-helper (k8s).
"""

import c_silence  # noqa: F401

import os
import time
import warnings
from datetime import datetime

import config

num_threads = config.CPU_THREADS
os.environ["OPENCV_NUM_THREADS"] = str(num_threads)
os.environ["OMP_NUM_THREADS"] = str(num_threads)
os.environ["MKL_NUM_THREADS"] = str(num_threads)
os.environ["NUMEXPR_NUM_THREADS"] = str(num_threads)

import cv2

cv2.setNumThreads(num_threads)
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import stats
from audio_detector import AudioDetector
from camera import open_camera_stream
from demo_boot_log import replay_immich_faces_boot
from gpu_client import GpuHelperClient
from mqtt_client import (
    init_mqtt,
    send_face_recognized,
    send_person_arrived,
    send_person_left,
    update_person_detected,
)
from presence_tracker import get_tracker, init_presence_tracker
from utils import ensure_dirs, log

warnings.filterwarnings("ignore")


def draw_text_unicode(
    img,
    text,
    position,
    font_size=20,
    text_color=(255, 255, 255),
    bg_color=None,
):
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size
        )
    except Exception:
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                font_size,
            )
        except Exception:
            font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x, y = position

    if bg_color:
        padding = 3
        draw.rectangle(
            [
                (x - padding, y - text_height - padding - 2),
                (x + text_width + padding, y + padding),
            ],
            fill=bg_color,
            outline=(0, 0, 0),
            width=1,
        )
        brightness = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        text_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)

    shadow_color = (0, 0, 0) if text_color == (255, 255, 255) else (255, 255, 255)
    draw.text((x + 1, y - text_height + 1), text, font=font, fill=shadow_color)
    draw.text((x, y - text_height), text, font=font, fill=text_color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def recognize_objects_and_faces(stream, gpu: GpuHelperClient, audio_detector=None):
    ensure_dirs()
    log("🎬 Запуск обработки видеопотока...")

    tracked: dict[str, dict[str, int]] = {}
    last_reported: set[str] = set()
    frame = 0

    no_frame_count = 0
    last_no_frame_log = 0
    last_stream_frame_id = -1
    first_frame_processed = False
    warmup_times = []

    object_emojis = {
        "person": "👤",
        "dog": "🐕",
        "cat": "🐱",
        "tv": "📺",
        "laptop": "💻",
        "cell phone": "📱",
        "chair": "🪑",
        "couch": "🛋️",
        "dining table": "🍽️",
        "bed": "🛏️",
        "book": "📖",
        "cup": "☕",
        "bottle": "🍼",
        "keyboard": "⌨️",
        "mouse": "🖱️",
    }
    object_colors = {
        "person": (0, 120, 255),
        "dog": (0, 200, 0),
        "cat": (255, 100, 0),
        "tv": (255, 0, 150),
        "laptop": (200, 0, 200),
        "cell phone": (255, 150, 0),
        "chair": (0, 150, 0),
        "couch": (150, 0, 150),
        "dining table": (200, 150, 0),
        "bed": (0, 100, 200),
        "book": (0, 180, 180),
        "cup": (50, 50, 200),
        "bottle": (150, 100, 0),
        "keyboard": (150, 0, 100),
        "mouse": (100, 50, 150),
    }

    def get_debounce_params(label: str):
        base = label.split("(", 1)[0] if "(" in label else label
        if base in config.IMPORTANT_OBJECTS:
            return config.MAX_MISSING, config.MIN_STABLE
        return config.MAX_MISSING_OTHER, config.MIN_STABLE_OTHER

    while True:
        if stream is None:
            log("🔄 Камера недоступна, пробую подключиться...")
            time.sleep(5)
            stream = open_camera_stream()
            continue

        img, stream_frame_id, last_ok_ts = stream.get_latest()
        now = time.time()

        if img is None or stream_frame_id == last_stream_frame_id:
            if last_ok_ts == 0.0 or (now - last_ok_ts) > config.STREAM_STALE_SEC:
                no_frame_count += 1
                if no_frame_count == 1 or (
                    no_frame_count % 10 == 0 and now - last_no_frame_log > 5
                ):
                    log(
                        f"⚠️ Кадр не обновляется — пробую ещё... "
                        f"(попытка {no_frame_count})"
                    )
                    last_no_frame_log = now

                if no_frame_count >= config.STREAM_RECONNECT_ATTEMPTS:
                    log(
                        f"🔄 Переподключение к удалённому видеопотоку после "
                        f"{no_frame_count} неудачных попыток..."
                    )
                    try:
                        stream.close()
                    except Exception:
                        pass
                    stream = None
                    time.sleep(config.STREAM_RECONNECT_DELAY)
                    for attempt in range(3):
                        stream = open_camera_stream()
                        if stream is not None:
                            no_frame_count = 0
                            last_stream_frame_id = -1
                            log("✅ Переподключение выполнено")
                            break
                        log(
                            f"❌ Попытка переподключения {attempt + 1}/3 "
                            "не удалась, жду..."
                        )
                        time.sleep(5 * (attempt + 1))
                    else:
                        log(
                            "⚠️ Все попытки переподключения не удались, "
                            "продолжаю пытаться..."
                        )
                        no_frame_count = 0
                        time.sleep(10)
                    continue
            time.sleep(0.05)
            continue

        last_stream_frame_id = stream_frame_id
        if no_frame_count > 0:
            if no_frame_count > 1:
                log(f"✅ Видеопоток восстановлен после {no_frame_count} попыток")
            no_frame_count = 0

        frame += 1
        if audio_detector:
            audio_detector.set_frame(frame)

        frame_start_time = time.time()
        if not first_frame_processed:
            log("✅ Первый кадр получен")
            log("✅ Инициализация завершена, система работает")
            log("🔥 Прогрев (первые кадры могут быть медленнее)...")
            first_frame_processed = True

        try:
            detected_objects = gpu.vision(img)
        except Exception as e:
            log(f"⚠️ GPU vision: {e}")
            time.sleep(0.2)
            continue

        seen: dict[str, bool] = {}
        for obj in detected_objects:
            label = obj["label"]
            seen[label] = True
            if label.startswith("person("):
                name = label[7:-1]
                stats.record_person_seen(name)
            obj["emoji"] = object_emojis.get(
                label.split("(")[0] if "(" in label else label, "📦"
            )

        for lbl in list(tracked.keys()):
            max_missing, min_stable = get_debounce_params(lbl)
            if lbl not in seen:
                tracked[lbl]["last"] += 1
                if tracked[lbl]["last"] > max_missing // 2:
                    tracked[lbl]["stable"] = max(0, tracked[lbl]["stable"] - 1)
                if tracked[lbl]["last"] > max_missing:
                    tracked.pop(lbl)
            else:
                tracked[lbl]["last"] = 0
                tracked[lbl]["stable"] = min(
                    tracked[lbl]["stable"] + 1, min_stable
                )

        for lbl in seen:
            if lbl not in tracked:
                tracked[lbl] = {"last": 0, "stable": 1}
                if frame <= 20:
                    log(f"👁️ Кадр {frame}: обнаружен {lbl} (стабилизация...)")

        current = {
            lbl
            for lbl, v in tracked.items()
            if v["stable"] >= get_debounce_params(lbl)[1]
        }

        if current != last_reported:
            added = current - last_reported
            removed = last_reported - current
            person_count = sum(
                1 for c in current if c == "person" or c.startswith("person(")
            )
            update_person_detected(person_count > 0)

            faces_recognized = []
            truly_added = []
            truly_removed = []

            for a in added:
                if a.startswith("person("):
                    faces_recognized.append(a[7:-1])
                elif a == "person":
                    if not any(x.startswith("person(") for x in added):
                        truly_added.append(a)
                else:
                    truly_added.append(a)

            for r in removed:
                if r.startswith("person("):
                    person_still_here = "person" in current or "person" in added
                    if not person_still_here:
                        truly_removed.append(r)
                elif r == "person":
                    if not any(x.startswith("person(") for x in added):
                        truly_removed.append(r)
                else:
                    truly_removed.append(r)

            has_changes = faces_recognized or truly_added or truly_removed
            if has_changes:
                log(f"📸 Кадр {frame}: Обнаружены объекты:")
                objects_by_label = {}
                for obj in detected_objects:
                    label = obj["label"]
                    if (
                        label not in objects_by_label
                        or obj["confidence"] > objects_by_label[label]["confidence"]
                    ):
                        objects_by_label[label] = obj

                for label in sorted(current):
                    if label in objects_by_label:
                        obj = objects_by_label[label]
                        log(
                            f"   {obj.get('emoji', '📦')} {label} "
                            f"(confidence: {obj['confidence']:.2f}) "
                            f"[x: {obj['x']}, y: {obj['y']}, "
                            f"w: {obj['w']}, h: {obj['h']}]"
                        )
                    else:
                        emoji = object_emojis.get(
                            label.split("(")[0] if "(" in label else label, "📦"
                        )
                        log(f"   {emoji} {label}")

                current_screenshot_path = None

                def _current_has_screenshot_objects():
                    if not config.SCREENSHOT_OBJECTS:
                        return True
                    for lbl in current:
                        base = lbl.split("(", 1)[0] if "(" in lbl else lbl
                        if base.lower() in config.SCREENSHOT_OBJECTS:
                            return True
                    return False

                if config.SCREENSHOTS_ENABLED and _current_has_screenshot_objects():
                    img_with_boxes = img.copy()
                    for obj in detected_objects:
                        label = obj["label"]
                        display_label = label
                        base = label.split("(")[0] if "(" in label else label
                        x1, y1 = obj["x"], obj["y"]
                        x2, y2 = x1 + obj["w"], y1 + obj["h"]
                        color = object_colors.get(base, (255, 0, 0))
                        line_width = 3 if base == "person" else 2
                        cv2.rectangle(
                            img_with_boxes,
                            (x1, y1),
                            (x2, y2),
                            (0, 0, 0),
                            line_width + 2,
                        )
                        cv2.rectangle(
                            img_with_boxes, (x1, y1), (x2, y2), color, line_width
                        )
                        label_text = f"{display_label} {obj['confidence']:.2f}"
                        bg_color_rgb = (color[2], color[1], color[0])
                        img_with_boxes = draw_text_unicode(
                            img_with_boxes,
                            label_text,
                            (x1, y1),
                            font_size=18 if base == "person" else 16,
                            text_color=(255, 255, 255),
                            bg_color=bg_color_rgb,
                        )

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    current_screenshot_path = os.path.join(
                        config.SCREENSHOTS_DIR,
                        f"frame_{timestamp}_{frame}.jpg",
                    )
                    cv2.imwrite(current_screenshot_path, img_with_boxes)
                    log(f"💾 Скриншот сохранен: {current_screenshot_path}")

                if truly_added:
                    log(f"➕ Появились: {', '.join(sorted(truly_added))}")

                for name in faces_recognized:
                    log(f"👤 Распознано лицо на кадре: {name}")
                    screenshot_url = None
                    if current_screenshot_path and config.SCREENSHOTS_WEB_URL:
                        filename = os.path.basename(current_screenshot_path)
                        screenshot_url = (
                            f"{config.SCREENSHOTS_WEB_URL.rstrip('/')}"
                            f"/screenshots/{filename}"
                        )
                    send_face_recognized(
                        name, frame=frame, screenshot_url=screenshot_url
                    )
                    tracker = get_tracker()
                    if tracker:
                        tracker.on_face_recognized(name, current_screenshot_path)

                if truly_removed:
                    log(f"➖ Ушли: {', '.join(sorted(truly_removed))}")

            last_reported = current

        if frame <= 15:
            frame_time = time.time() - frame_start_time
            warmup_times.append(f"{frame}:{frame_time:.2f}с")
            if frame % 5 == 0 or frame == 15:
                log(f"   ⏱️ Кадры {', '.join(warmup_times)}")
                warmup_times.clear()
        elif frame == 16:
            log("✅ Прогрев завершён, система работает в штатном режиме")


if __name__ == "__main__":
    # Отделяет новый запуск от хвоста docker logs после restart
    print(
        "\n" * 4
        + "═" * 64
        + "\n"
        + "  ★  NEW RUN  ·  home-sentinel  ★".center(64)
        + "\n"
        + "═" * 64
        + "\n",
        flush=True,
    )
    log("🚀 home-sentinel стартует")

    try:
        stats.init_tables()

        gpu = GpuHelperClient()
        if not gpu.wait_ready():
            raise RuntimeError("GPU недоступна")

        # Демо: проигрываем сохранённый лог Immich (реальная БД не нужна)
        replay_immich_faces_boot()

        stream = open_camera_stream()
        if stream is None:
            time.sleep(5)
            stream = open_camera_stream()
            if stream is None:
                raise RuntimeError("Камера недоступна")

        audio = None
        if config.YAMNET_CLASSES:
            audio = AudioDetector(gpu=gpu)
            audio.start()

        init_mqtt()
        tracker = init_presence_tracker()
        if tracker:
            tracker.set_callbacks(
                on_arrived=send_person_arrived, on_left=send_person_left
            )

    except Exception as e:
        log(f"🚫 Критическая ошибка инициализации: {e}")
        import traceback

        traceback.print_exc()
        raise SystemExit(1)

    if audio:
        audio.enable()

    recognize_objects_and_faces(stream, gpu, audio)
