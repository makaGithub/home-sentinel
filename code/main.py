#!/usr/bin/env python3
"""
main.py — home-sentinel (CPU): RTSP/аудио, компактные цветные логи, демо-режим, скриншоты.
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
from demo_state import (
    clear_demo_alert_key,
    emit_demo_alert,
    emit_demo_event,
    get_demo_stage,
    init_demo_state,
)
from gpu_client import GpuHelperClient
from mqtt_client import (
    init_mqtt,
    send_face_recognized,
    send_person_arrived,
    send_person_left,
    update_person_detected,
)
from presence_tracker import get_tracker, init_presence_tracker
from utils import (
    C_BG_GREEN,
    C_BG_YELLOW,
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_WHITE,
    C_YELLOW,
    ensure_dirs,
    format_box,
    format_object_short,
    log,
)

warnings.filterwarnings("ignore")

# Фоновые/стационарные классы в помещении, которые мешают на этапе «Объекты» в демо
DEMO_OBJECT_NOISE = {
    "traffic light",
    "oven",
    "microwave",
    "refrigerator",
    "sink",
    "toilet",
    "bed",
    "chair",
    "couch",
    "dining table",
    "tv",
    "bench",
}


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

    tracked: dict[str, dict[str, float]] = {}
    last_reported: set[str] = set()
    last_object_announce_ts: dict[str, float] = {}
    frame = 0

    no_frame_count = 0
    last_no_frame_log = 0
    last_stream_frame_id = -1
    first_frame_processed = False
    camera_was_down = False
    gpu_vision_was_down = False
    last_unknown_face_ts = 0.0
    last_no_person_ts = 0.0
    empty_announced = False
    guest_announced = False
    prev_stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")

    if prev_stage == "idle":
        log(
            f"⏸  {C_YELLOW}Демо-режим активен:{C_RESET} "
            f"ожидание команды (введите {C_GREEN}demo{C_RESET})"
        )
    else:
        log(f"🎬 {C_CYAN}Обработка видеопотока запущена{C_RESET}")

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

    def get_debounce_params(label: str, stage: str):
        base = (label.split("(", 1)[0] if "(" in label else label).lower()
        if stage == "objects":
            # Приоритетные предметы (кружка, цветок, телефон): быстрое появление + долгое удержание без дребезга
            if base in config.DEMO_PRIORITY_OBJECTS:
                return 35, 2
            # Остальные предметы переднего плана: строже на вход, долгое удержание
            return 35, 5
        if stage == "faces":
            return 20, 2
        if base in config.IMPORTANT_OBJECTS:
            return config.MAX_MISSING, config.MIN_STABLE
        return config.MAX_MISSING_OTHER, config.MIN_STABLE_OTHER

    while True:
        stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
        if stage != prev_stage:
            tracked.clear()
            last_reported.clear()
            last_object_announce_ts.clear()
            last_unknown_face_ts = 0.0
            last_no_person_ts = 0.0
            empty_announced = False
            guest_announced = False
            prev_stage = stage

        # idle/finale — пауза GPU; sounds — только аудио (видео не шлём)
        if stage in ("idle", "sounds", "finale"):
            time.sleep(0.1)
            continue

        if stream is None:
            log(f"🔄 {C_YELLOW}Переподключение к камере...{C_RESET}")
            camera_was_down = True
            emit_demo_alert(
                f"⚠️ {C_YELLOW}Камера:{C_RESET} нет потока, переподключение…",
                kind="warn",
                stage=stage if stage in ("objects", "faces") else "*",
                key="camera_reconnect",
                min_interval=10.0,
            )
            time.sleep(5)
            stream = open_camera_stream()
            continue

        img, stream_frame_id, last_ok_ts = stream.get_latest()
        now = time.time()

        if img is None or stream_frame_id == last_stream_frame_id:
            if last_ok_ts == 0.0 or (now - last_ok_ts) > config.STREAM_STALE_SEC:
                no_frame_count += 1
                if no_frame_count == 1 or (
                    no_frame_count % 15 == 0 and now - last_no_frame_log > 5
                ):
                    log(f"⚠️ Ожидание кадра с камеры... ({no_frame_count})")
                    last_no_frame_log = now
                    camera_was_down = True
                    emit_demo_alert(
                        f"⚠️ {C_YELLOW}Камера:{C_RESET} нет кадров (ждём go2rtc/RTSP)…",
                        kind="warn",
                        stage=stage if stage in ("objects", "faces") else "*",
                        key="camera_no_frames",
                        min_interval=10.0,
                    )

                if no_frame_count >= config.STREAM_RECONNECT_ATTEMPTS:
                    try:
                        stream.close()
                    except Exception:
                        pass
                    stream = None
                    time.sleep(config.STREAM_RECONNECT_DELAY)
                    for _ in range(3):
                        stream = open_camera_stream()
                        if stream is not None:
                            no_frame_count = 0
                            last_stream_frame_id = -1
                            break
                        time.sleep(3)
                    continue
            time.sleep(0.05)
            continue

        last_stream_frame_id = stream_frame_id
        no_frame_count = 0
        if camera_was_down:
            camera_was_down = False
            clear_demo_alert_key("camera_reconnect")
            clear_demo_alert_key("camera_no_frames")
            emit_demo_alert(
                f"✅ {C_GREEN}Камера снова в эфире{C_RESET}",
                kind="info",
                stage=stage if stage in ("objects", "faces", "idle") else "*",
                key="camera_ok",
                min_interval=3.0,
            )

        frame += 1
        if audio_detector:
            audio_detector.set_frame(frame)

        if not first_frame_processed:
            first_frame_processed = True
            if stage == "normal":
                log(f"✅ {C_GREEN}Поток активен, анализ в реальном времени{C_RESET}")

        try:
            raw_objects = gpu.vision(img)
            if gpu_vision_was_down:
                gpu_vision_was_down = False
                clear_demo_alert_key("gpu_vision")
                emit_demo_alert(
                    f"✅ {C_GREEN}GPU vision снова отвечает{C_RESET}",
                    kind="info",
                    stage=stage if stage in ("objects", "faces") else "*",
                    key="gpu_vision_ok",
                    min_interval=3.0,
                )
        except Exception as e:
            if config.DEBUG:
                log(f"⚠️ GPU vision: {e}")
            gpu_vision_was_down = True
            emit_demo_alert(
                f"⚠️ {C_YELLOW}GPU:{C_RESET} vision недоступен, жду…",
                kind="warn",
                stage=stage if stage in ("objects", "faces") else "*",
                key="gpu_vision",
                min_interval=8.0,
            )
            time.sleep(0.2)
            continue

        # Фильтрация объектов в зависимости от этапа демо и близости к камере (передний план)
        img_h, img_w = img.shape[:2]
        frame_area = float(max(1, img_h * img_w))
        detected_objects = []
        foreground_boost: set[str] = set()

        for obj in raw_objects:
            lbl = obj["label"]
            lbl_low = lbl.lower()
            is_person = lbl == "person" or lbl.startswith("person(")
            area_ratio = (float(obj.get("w", 0)) * float(obj.get("h", 0))) / frame_area
            conf = float(obj.get("confidence", 0.0))

            if stage == "objects":
                # Этап 1: ТОЛЬКО предметы (без людей и без фоновой мебели)
                if is_person or lbl_low in DEMO_OBJECT_NOISE:
                    continue
                if lbl_low in config.DEMO_PRIORITY_OBJECTS:
                    # Приоритетные предметы (кружка, цветок, телефон)
                    if (
                        conf < config.DEMO_PRIORITY_MIN_CONF
                        or area_ratio < config.DEMO_PRIORITY_MIN_AREA
                    ):
                        continue
                    if area_ratio >= config.DEMO_FOREGROUND_FAST_AREA and conf >= 0.32:
                        foreground_boost.add(lbl)
                else:
                    # Неприоритетные предметы — только если крупно поднесены на передний план!
                    if (
                        conf < config.DEMO_OTHER_MIN_CONF
                        or area_ratio < config.DEMO_OTHER_MIN_AREA
                    ):
                        continue
                detected_objects.append(obj)
            elif stage == "faces":
                # Этап 3: ТОЛЬКО люди и лица
                if not is_person:
                    continue
                detected_objects.append(obj)
            else:
                detected_objects.append(obj)

        seen: dict[str, float] = {}
        seen_area: dict[str, float] = {}
        for obj in detected_objects:
            label = obj["label"]
            conf = float(obj.get("confidence", 0.0))
            area_ratio = (float(obj.get("w", 0)) * float(obj.get("h", 0))) / frame_area
            if label not in seen or conf > seen[label]:
                seen[label] = conf
            if label not in seen_area or area_ratio > seen_area[label]:
                seen_area[label] = area_ratio
            if label.startswith("person("):
                name = label[7:-1]
                stats.record_person_seen(name)

        for lbl in list(tracked.keys()):
            max_missing, min_stable = get_debounce_params(lbl, stage)
            if lbl not in seen:
                tracked[lbl]["last"] += 1
                # В обычном режиме плавно гасим stable; в демо держим стабильно без мигания до конца max_missing
                if stage not in ("objects", "faces") and tracked[lbl]["last"] > max_missing // 2:
                    tracked[lbl]["stable"] = max(0, tracked[lbl]["stable"] - 1)
                if tracked[lbl]["last"] > max_missing:
                    tracked.pop(lbl)
            else:
                tracked[lbl]["last"] = 0
                step = 2 if lbl in foreground_boost else 1
                tracked[lbl]["stable"] = min(
                    tracked[lbl]["stable"] + step, min_stable
                )
                tracked[lbl]["conf"] = max(
                    seen[lbl], tracked[lbl].get("conf", seen[lbl]) * 0.85
                )
                tracked[lbl]["area"] = seen_area.get(
                    lbl, tracked[lbl].get("area", 0.0)
                )

        for lbl, conf in seen.items():
            if lbl not in tracked:
                step = 2 if lbl in foreground_boost else 1
                tracked[lbl] = {
                    "last": 0,
                    "stable": step,
                    "conf": conf,
                    "area": seen_area.get(lbl, 0.0),
                }

        current = {
            lbl
            for lbl, v in tracked.items()
            if v["stable"] >= get_debounce_params(lbl, stage)[1]
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
                objects_by_label = {}
                for obj in detected_objects:
                    label = obj["label"]
                    if (
                        label not in objects_by_label
                        or obj["confidence"] > objects_by_label[label]["confidence"]
                    ):
                        objects_by_label[label] = obj

                def _fmt(lbl: str) -> str:
                    conf = (
                        objects_by_label[lbl]["confidence"]
                        if lbl in objects_by_label
                        else (tracked[lbl].get("conf") if lbl in tracked else None)
                    )
                    return format_object_short(lbl, conf)

                def _priority_sort_key(lbl: str) -> tuple[int, float, str]:
                    low = lbl.lower()
                    is_prio = 0 if low in config.DEMO_PRIORITY_OBJECTS else 1
                    area = -(tracked[lbl].get("area", 0.0) if lbl in tracked else 0.0)
                    return (is_prio, area, low)

                # Сохранение скриншота (тихо, без спама длинным путём)
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
                        label_text = f"{label} {obj['confidence']:.2f}"
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

                # === Вывод для ЭТАПА 1: ОБЪЕКТЫ ===
                if stage == "objects":
                    announced_now = []
                    for a in sorted(truly_added, key=_priority_sort_key):
                        if (now - last_object_announce_ts.get(a, 0.0)) < 6.0:
                            continue
                        last_object_announce_ts[a] = now
                        announced_now.append(a)
                        msg = f"➕ {_fmt(a)}"
                        log(msg)
                        emit_demo_event("objects", msg, kind="added")
                    # Сводку «В кадре» печатаем только когда реально добавился новый предмет
                    if announced_now and current:
                        items = " · ".join(
                            _fmt(c) for c in sorted(current, key=_priority_sort_key)
                        )
                        msg = f"🎯 В кадре: {items}"
                        log(msg)
                        emit_demo_event("objects", msg, kind="summary")

                # === Вывод для ЭТАПА 3: ЛЮДИ И ЛИЦА ===
                elif stage == "faces":
                    if "person" in truly_added and not faces_recognized:
                        if not guest_announced:
                            msg1 = (
                                f"{C_BG_YELLOW} ❓ НЕ В БАЗЕ {C_RESET} "
                                f"{_fmt('person')} "
                                f"{C_DIM}· лицо не распознано{C_RESET}"
                            )
                            msg2 = f"🏠 {C_CYAN}Умный дом:{C_RESET} гость в кадре 📸"
                            log(msg1)
                            log(msg2)
                            emit_demo_event("faces", msg1, kind="person")
                            emit_demo_event("faces", msg2, kind="ha")
                            last_unknown_face_ts = now
                            guest_announced = True

                    for name in faces_recognized:
                        lbl = f"person({name})"
                        conf = (
                            objects_by_label[lbl]["confidence"]
                            if lbl in objects_by_label
                            else 0.94
                        )
                        pct = int(round(conf * 100))
                        msg1 = (
                            f"{C_BG_GREEN} ✅ СВОЙ {C_RESET} "
                            f"{C_BOLD}{C_GREEN}{name}{C_RESET} "
                            f"{C_YELLOW}{pct}%{C_RESET}"
                        )
                        msg2 = f"🏠 {C_CYAN}Умный дом:{C_RESET} привет, {name.split()[0]}! 💡"
                        log(msg1)
                        log(msg2)
                        emit_demo_event("faces", msg1, kind="face")
                        emit_demo_event("faces", msg2, kind="ha")
                        last_unknown_face_ts = now

                # === Вывод для ОСНОВНОГО РЕЖИМА ===
                else:
                    if current:
                        items = " · ".join(_fmt(c) for c in sorted(current))
                        log(f"🎯 В кадре: {items}")
                    if truly_added:
                        added_str = ", ".join(_fmt(a) for a in sorted(truly_added))
                        log(f"➕ {C_GREEN}Появились:{C_RESET} {added_str}")
                    for name in faces_recognized:
                        log(
                            f"{C_BG_GREEN} 👤 ЛИЦО {C_RESET} "
                            f"{C_BOLD}{C_GREEN}{name}{C_RESET}"
                        )
                    if truly_removed:
                        rem_str = ", ".join(
                            format_object_short(r) for r in sorted(truly_removed)
                        )
                        log(f"➖ {C_RED}Ушли:{C_RESET} {rem_str}")

                # Отправка событий по распознанным лицам в MQTT / трекер
                for name in faces_recognized:
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

            last_reported = current

        # Этап faces: «никого нет» / «гость» — по одному разу на эпизод, без повторов
        if stage == "faces":
            has_person = any(
                c == "person" or c.startswith("person(") for c in current
            )
            if has_person:
                empty_announced = False
            else:
                guest_announced = False
                if not empty_announced:
                    msg = (
                        f"👤 {C_YELLOW}В кадре никого нет{C_RESET} "
                        f"{C_DIM}· подойдите к камере{C_RESET}"
                    )
                    log(msg)
                    emit_demo_event("faces", msg, kind="empty")
                    empty_announced = True
                    last_no_person_ts = now


if __name__ == "__main__":
    print(
        "\n"
        + "\n".join(
            format_box(f" 🛡️  {C_BOLD}{C_GREEN}СТРАЖ ДОМА · AI SENTINEL{C_RESET}", C_CYAN)
        ),
        flush=True,
    )

    try:
        stats.init_tables()

        # Чтобы алерты старта сразу попали в demo-консоль (если она уже открыта)
        if config.DEMO_MODE:
            init_demo_state(True, faces_count=0)

        gpu = GpuHelperClient()
        if not gpu.wait_ready():
            emit_demo_alert(
                f"❌ {C_RED}GPU недоступна{C_RESET} — демо не стартует",
                kind="error",
                stage="*",
                key="boot_gpu",
                min_interval=0,
            )
            raise RuntimeError("GPU недоступна")

        faces_count = gpu.sync_faces()
        init_demo_state(config.DEMO_MODE, faces_count=faces_count)
        if config.DEMO_MODE and faces_count <= 0:
            emit_demo_alert(
                f"⚠️ {C_YELLOW}Immich/лица:{C_RESET} в памяти 0 — этап «Лица» будет пустым",
                kind="warn",
                stage="*",
                key="boot_faces",
                min_interval=0,
            )

        stream = open_camera_stream()
        if stream is None:
            time.sleep(5)
            stream = open_camera_stream()
            if stream is None:
                emit_demo_alert(
                    f"❌ {C_RED}Камера недоступна{C_RESET} — нет RTSP/go2rtc",
                    kind="error",
                    stage="*",
                    key="boot_camera",
                    min_interval=0,
                )
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
        log(f"🚫 {C_RED}Ошибка старта:{C_RESET} {e}")
        emit_demo_alert(
            f"❌ {C_RED}Старт:{C_RESET} {e}",
            kind="error",
            stage="*",
            key="boot_fatal",
            min_interval=0,
        )
        import traceback

        traceback.print_exc()
        raise SystemExit(1)

    if audio:
        audio.enable()

    recognize_objects_and_faces(stream, gpu, audio)
