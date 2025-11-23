#!/usr/bin/env python3
"""
main.py — модульный home-sentinel для Immich.

Функции:
- YOLOv11 детекция объектов
- InsightFace (antelopev2) распознавание лиц (векторные представления из Immich)
- Анти-дребезг
- Лог "кто в кадре"
- Запись статистики по людям
- Запуск простого аудиодетектора с RTSP (AudioDetector) и запись статистики по звукам
"""

# Первым глушим C-level stdout/stderr
import c_silence  # noqa: F401

import time
import warnings

import cv2
import numpy as np

import config
import stats
from audio_detector import AudioDetector
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

    while True:
        ret, img = cap.read()
        if not ret:
            log("⚠️ Кадр не получен — пробую ещё...")
            time.sleep(0.2)
            continue

        frame += 1
        results = yolo.predict(img, verbose=False)
        seen: dict[str, bool] = {}

        # ---------------- YOLO ----------------
        for r in results:
            boxes = r.boxes.xyxy.cpu().numpy()
            classes = r.boxes.cls.cpu().numpy().astype(int)

            for (x1, y1, x2, y2), cls in zip(boxes, classes):
                label = yolo.names.get(cls, str(cls))

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

                            log(
                                f"🔍 Кадр {frame}: {best_name} "
                                f"sim={best_sim:.3f}, diff={diff:.3f}, thr={thr:.3f}"
                            )
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
    log("🚀 home-sentinel (RTSP video + RTSP audio) стартует")

    # Инициализация таблиц статистики
    stats.init_tables()

    # Запускаем аудио-детектор в фоне (простая заглушка по громкости)
    audio = AudioDetector()
    audio.start()

    # Загружаем векторные представления Immich
    all_embeddings_list, names, ids, all_confidences_list = load_or_refresh_cache()

    # Запускаем основной цикл видео
    recognize_objects_and_faces(all_embeddings_list, names, all_confidences_list)
