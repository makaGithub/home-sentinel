#!/usr/bin/env python3
"""
main.py — модульный home-sentinel для Immich.

Функции:
- YOLOv11 детекция объектов
- InsightFace (antelopev2) распознавание лиц (векторные представления из Immich)
- Анти-дребезг
- Лог "кто в кадре"
- Запись статистики по людям
- Запуск простого аудиодетектора с RTSP (AudioDetector) и запись статистики по звукам (временно отключено)
"""

# Первым глушим C-level stdout/stderr
import c_silence  # noqa: F401

import os
import time
import warnings
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
import stats
# from audio_detector import AudioDetector  # Временно отключено
from camera import open_camera
from embeddings import load_or_refresh_cache
from models import init_face_analysis, init_yolo
from utils import (
    adaptive_threshold,
    ensure_dirs,
    log,
    preprocess_face_crop,
    _l2_normalize,
)

warnings.filterwarnings("ignore")


# ============================================================
# 🎨 Функция для отрисовки текста с поддержкой Unicode
# ============================================================
def draw_text_unicode(img, text, position, font_size=20, text_color=(255, 255, 255), bg_color=None):
    """
    Отрисовывает текст с поддержкой Unicode (включая русские символы) на изображении OpenCV.
    
    Args:
        img: изображение OpenCV (BGR)
        text: текст для отрисовки
        position: (x, y) позиция текста
        font_size: размер шрифта
        text_color: цвет текста (RGB)
        bg_color: цвет фона (RGB) или None
    
    Returns:
        изображение с отрисованным текстом
    """
    # Конвертируем OpenCV изображение (BGR) в PIL (RGB)
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    
    # Пытаемся загрузить шрифт, если не получается - используем default
    try:
        # Пробуем найти системный шрифт
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except:
        try:
            # Альтернативный путь
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", font_size)
        except:
            # Используем default шрифт (может не поддерживать все символы)
            font = ImageFont.load_default()
    
    # Получаем размеры текста
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x, y = position
    
    # Рисуем фон если указан
    if bg_color:
        draw.rectangle(
            [(x, y - text_height - 5), (x + text_width, y + 5)],
            fill=bg_color
        )
    
    # Рисуем текст
    draw.text((x, y - text_height), text, font=font, fill=text_color)
    
    # Конвертируем обратно в OpenCV (BGR)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


# ============================================================
# 💡 Функция сходства лица и эмбеддингов человека
# ============================================================
def compute_face_similarity(
    face_emb: np.ndarray,
    person_embeddings_list: list,
    person_confidences: list | None = None,
) -> float:
    """
    Вычисляет максимальное сходство между лицом и всеми векторными представлениями человека.
    Немного учитывает confidence, если он есть.
    """
    if not person_embeddings_list:
        return 0.0

    face_emb = _l2_normalize(face_emb)
    max_sim = -1.0

    for idx, emb in enumerate(person_embeddings_list):
        emb = _l2_normalize(emb)
        sim = float(np.dot(face_emb, emb))

        if person_confidences and idx < len(person_confidences):
            conf = max(0.5, float(person_confidences[idx]))
            sim *= (0.7 + 0.3 * conf)

        if sim > max_sim:
            max_sim = sim

    return max_sim


# ============================================================
# 🔁 Главный цикл: видео, объекты, лица, статистика
# ============================================================
def recognize_objects_and_faces(
    all_embeddings_list: list,
    names: list,
    all_confidences_list: list,
):
    ensure_dirs()

    cap = open_camera()
    if cap is None:
        time.sleep(5)
        cap = open_camera()
        if cap is None:
            raise RuntimeError("🚫 Камера недоступна.")

    yolo = init_yolo()
    face_app = init_face_analysis()

    tracked: dict[str, dict[str, int]] = {}
    last_reported: set[str] = set()
    frame = 0

    face_cache: dict[int, tuple[int, str | None, float]] = {}
    cache_validity = config.FACE_CACHE_VALIDITY_FRAMES
    
    # Счетчик для уменьшения флуда логов при отсутствии кадров
    no_frame_count = 0
    last_no_frame_log = 0
    
    # Словарь эмодзи для разных объектов
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
    
    # Цветовая палитра для разных типов объектов (BGR формат для OpenCV)
    object_colors = {
        "person": (255, 100, 0),      # Синий
        "dog": (0, 255, 255),          # Желтый
        "cat": (255, 165, 0),          # Оранжевый
        "tv": (255, 0, 255),           # Пурпурный
        "laptop": (255, 20, 147),      # Розовый
        "cell phone": (0, 191, 255),   # Голубой
        "chair": (34, 139, 34),        # Зеленый
        "couch": (139, 0, 139),        # Темно-фиолетовый
        "dining table": (0, 206, 209), # Бирюзовый
        "bed": (255, 140, 0),          # Темно-оранжевый
        "book": (255, 215, 0),         # Золотой
        "cup": (255, 69, 0),           # Красно-оранжевый
        "bottle": (0, 250, 154),       # Зелено-голубой
        "keyboard": (138, 43, 226),    # Фиолетовый
        "mouse": (255, 105, 180),      # Розово-красный
    }

    while True:
        ret, img = cap.read()
        if not ret:
            no_frame_count += 1
            # Логируем только каждые 10 попыток или при первой попытке
            if no_frame_count == 1 or (no_frame_count % 10 == 0 and time.time() - last_no_frame_log > 5):
                log(f"⚠️ Кадр не получен — пробую ещё... (попытка {no_frame_count})")
                last_no_frame_log = time.time()
            time.sleep(0.2)
            continue

        # Если кадр получен успешно, сбрасываем счетчик
        if no_frame_count > 0:
            if no_frame_count > 1:
                log(f"✅ Видеопоток восстановлен после {no_frame_count} попыток")
            no_frame_count = 0

        frame += 1
        results = yolo.predict(img, verbose=False)
        seen: dict[str, bool] = {}

        # ---------------- YOLO ----------------
        detected_objects = []  # Список для логирования
        
        for r in results:
            boxes = r.boxes.xyxy.cpu().numpy()
            classes = r.boxes.cls.cpu().numpy().astype(int)
            confidences = r.boxes.conf.cpu().numpy()  # Получаем confidence

            for (x1, y1, x2, y2), cls, conf in zip(boxes, classes, confidences):
                label = yolo.names.get(cls, str(cls))
                
                # Сохраняем информацию об объекте для логирования
                emoji = object_emojis.get(label, "📦")
                w = int(x2 - x1)
                h = int(y2 - y1)
                detected_objects.append({
                    "label": label,
                    "emoji": emoji,
                    "confidence": float(conf),
                    "x": int(x1),
                    "y": int(y1),
                    "w": w,
                    "h": h
                })

                # всегда считаем person как базовую сущность
                if label == "person":
                    seen["person"] = True
                else:
                    seen[label] = True

                # если это не person — лица не ищем
                if label != "person" or len(all_embeddings_list) == 0:
                    continue

                h, w = img.shape[:2]
                x1i, y1i = max(0, int(x1)), max(0, int(y1))
                x2i, y2i = min(w, int(x2)), min(h, int(y2))

                if x2i <= x1i or y2i <= y1i:
                    continue

                # padding вокруг bounding box
                box_w = x2i - x1i
                box_h = y2i - y1i
                pad = config.FACE_PADDING_RATIO

                x1p = max(0, int(x1i - box_w * pad))
                y1p = max(0, int(y1i - box_h * pad))
                x2p = min(w, int(x2i + box_w * pad))
                y2p = min(h, int(y2i + box_h * pad))

                crop = img[y1p:y2p, x1p:x2p]
                if (
                    crop.size == 0
                    or crop.shape[0] < config.MIN_FACE_SIZE
                    or crop.shape[1] < config.MIN_FACE_SIZE
                ):
                    continue

                crop = preprocess_face_crop(crop)

                try:
                    faces = face_app.get(crop, max_num=config.MAX_FACES_PER_CROP)
                except Exception:
                    faces = []

                if not faces:
                    continue

                recognized_names: set[str] = set()

                # ----------- распознаём все лица в crop -----------
                for face in faces:
                    try:
                        face_emb = np.asarray(face.embedding, dtype=np.float32)
                        if face_emb.ndim != 1:
                            continue

                        face_hash = hash(tuple(face_emb[:10].astype(int)))
                        if face_hash in face_cache:
                            cached_frame, cached_name, cached_sim = face_cache[face_hash]
                            if frame - cached_frame < cache_validity and cached_name:
                                recognized_names.add(cached_name)
                                continue

                        sims: list[tuple[float, int, str | None]] = []

                        for idx, person_embs in enumerate(all_embeddings_list):
                            confs = (
                                all_confidences_list[idx]
                                if idx < len(all_confidences_list)
                                else None
                            )
                            sim = compute_face_similarity(face_emb, person_embs, confs)
                            pname = names[idx] if idx < len(names) else None
                            sims.append((sim, idx, pname))

                        if not sims:
                            continue

                        sims.sort(reverse=True, key=lambda x: x[0])
                        best_sim, best_idx, best_name = sims[0]
                        second_sim = sims[1][0] if len(sims) > 1 else 0.0
                        diff = best_sim - second_sim

                        face_size = max(box_w, box_h)
                        thr = adaptive_threshold(face_size, config.FACE_SIM_THRESHOLD)

                        high = best_sim >= thr + 0.1
                        good_diff = diff >= config.MIN_SIM_DIFF

                        if best_sim >= thr and (good_diff or high) and best_name:
                            if high:
                                face_cache[face_hash] = (frame, best_name, best_sim)

                            recognized_names.add(best_name)
                            stats.record_person_seen(best_name)

                            # Логирование распознавания лиц убрано для уменьшения флуда
                            # Информация о распознанных лицах будет в логах "➕ Появились: person(Имя)"
                        else:
                            # Диагностический лог (опционально)
                            pass

                    except Exception:
                        # локальные ошибки — не роняем поток
                        pass

                # если кого-то узнали — заменяем base "person" на именованные
                if recognized_names:
                    if "person" in seen:
                        del seen["person"]
                    for nm in recognized_names:
                        seen[f"person({nm})"] = True

                # периодическая чистка кэша
                if frame % 100 == 0:
                    face_cache = {
                        k: v for k, v in face_cache.items() if frame - v[0] < cache_validity
                    }

        # ---------------- Анти-дребезг ----------------
        for lbl in list(tracked.keys()):
            if lbl not in seen:
                tracked[lbl]["last"] += 1
                if tracked[lbl]["last"] > config.MAX_MISSING // 2:
                    tracked[lbl]["stable"] = max(0, tracked[lbl]["stable"] - 1)
                if tracked[lbl]["last"] > config.MAX_MISSING:
                    tracked.pop(lbl)
            else:
                tracked[lbl]["last"] = 0
                tracked[lbl]["stable"] = min(
                    tracked[lbl]["stable"] + 1, config.MIN_STABLE
                )

        for lbl in seen:
            if lbl not in tracked:
                tracked[lbl] = {"last": 0, "stable": 1}

        current = {l for l, v in tracked.items() if v["stable"] >= config.MIN_STABLE}

        if current != last_reported:
            added = current - last_reported
            removed = last_reported - current

            if added or removed:
                # Логируем детали объектов только при изменениях
                log(f"📸 Кадр {frame}: Обнаружены объекты:")
                
                # Создаем словарь для быстрого поиска объектов по label
                objects_by_label = {}
                for obj in detected_objects:
                    label = obj["label"]
                    # Если person был распознан с именем, используем его
                    for seen_label in seen.keys():
                        if seen_label.startswith("person(") and label == "person":
                            label = seen_label
                            break
                    if label not in objects_by_label or obj["confidence"] > objects_by_label[label]["confidence"]:
                        objects_by_label[label] = obj
                
                # Создаем копию изображения для отрисовки
                img_with_boxes = img.copy()
                
                # Отрисовываем все обнаруженные объекты
                for obj in detected_objects:
                    label = obj["label"]
                    # Если person был распознан с именем, используем его
                    display_label = label
                    for seen_label in seen.keys():
                        if seen_label.startswith("person(") and label == "person":
                            display_label = seen_label
                            break
                    
                    # Отрисовываем bounding box
                    x1, y1 = obj['x'], obj['y']
                    x2, y2 = x1 + obj['w'], y1 + obj['h']
                    
                    # Цвет для разных типов объектов из палитры
                    color = object_colors.get(label, (255, 0, 0))  # По умолчанию красный
                    
                    # Рисуем прямоугольник с более толстой линией для person
                    line_width = 3 if label == "person" else 2
                    cv2.rectangle(img_with_boxes, (x1, y1), (x2, y2), color, line_width)
                    
                    # Текст с label и confidence (с поддержкой Unicode)
                    label_text = f"{display_label} {obj['confidence']:.2f}"
                    
                    # Конвертируем BGR color в RGB для PIL
                    bg_color_rgb = (color[2], color[1], color[0])  # BGR -> RGB
                    
                    # Размер шрифта и цвет текста
                    font_size = 18 if label == "person" else 16
                    text_color = (255, 255, 255)  # Белый текст для лучшей читаемости
                    
                    # Отрисовываем текст с поддержкой Unicode
                    img_with_boxes = draw_text_unicode(
                        img_with_boxes,
                        label_text,
                        (x1, y1),
                        font_size=font_size,
                        text_color=text_color,
                        bg_color=bg_color_rgb
                    )
                
                # Логируем только объекты, которые есть в current
                for label in sorted(current):
                    if label in objects_by_label:
                        obj = objects_by_label[label]
                        log(
                            f"   {obj['emoji']} {label} "
                            f"(confidence: {obj['confidence']:.2f}) "
                            f"[x: {obj['x']}, y: {obj['y']}, w: {obj['w']}, h: {obj['h']}]"
                        )
                    else:
                        # Если объекта нет в detected_objects (например, person с именем), используем эмодзи по умолчанию
                        emoji = object_emojis.get(label.split("(")[0] if "(" in label else label, "📦")
                        log(f"   {emoji} {label}")
                
                # Сохраняем скриншот
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(
                    config.SCREENSHOTS_DIR,
                    f"frame_{frame}_{timestamp}.jpg"
                )
                cv2.imwrite(screenshot_path, img_with_boxes)
                log(f"💾 Скриншот сохранен: {screenshot_path}")

            if added:
                log(f"➕ Появились: {', '.join(sorted(added))}")
            if removed:
                log(f"➖ Ушли: {', '.join(sorted(removed))}")

            log(
                f"📸 Сейчас в кадре: {', '.join(sorted(current)) or 'никого'}"
            )

            last_reported = current


# ============================================================
# 🚀 MAIN
# ============================================================
if __name__ == "__main__":
    log("🚀 home-sentinel (RTSP video) стартует")

    # Инициализация таблиц статистики
    stats.init_tables()

    # Запускаем аудио-детектор в фоне (простая заглушка по громкости)
    # audio = AudioDetector()  # Временно отключено
    # audio.start()  # Временно отключено

    # Загружаем векторные представления Immich
    all_embeddings_list, names, ids, all_confidences_list = load_or_refresh_cache()

    # Запускаем основной цикл видео
    recognize_objects_and_faces(all_embeddings_list, names, all_confidences_list)
