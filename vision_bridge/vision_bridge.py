#!/usr/bin/env python3
"""
vision_bridge.py — компактная версия (~600 строк)

Функции:
- Загружает embeddings из Immich → кэширует → распознаёт лица
- YOLOv11 — детекция объектов
- InsightFace antelopev2 — сравнение лиц
- Анти-дребезг (MIN_STABLE/MAX_MISSING)
- Лог "сейчас в кадре — person, bed, tv..."
- Вариант C: person → всегда добавляется, person(Имя) заменяет person
- Полное подавление DLASCL / LAPACK / OpenBLAS C-вывода

Автор: ChatGPT специально для Aleksandr / Immich vision-bridge
"""

# ============================================================
# 🔇 ПОЛНОЕ подавление C-level stdout/stderr (OpenBLAS/MKL/LAPACK)
# ============================================================
import os
import sys

try:
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    # Сохраняем настоящие stdout/stderr Python
    py_stdout_fd = os.dup(1)
    py_stderr_fd = os.dup(2)

    # Перенаправляем C stdout/stderr → /dev/null
    os.dup2(devnull_fd, 1)   # fd=1 C stdout
    os.dup2(devnull_fd, 2)   # fd=2 C stderr

    # Восстанавливаем Python stdout/stderr в отдельные объекты
    sys.stdout = os.fdopen(py_stdout_fd, "w", buffering=1)
    sys.stderr = os.fdopen(py_stderr_fd, "w", buffering=1)

    os.close(devnull_fd)
except Exception:
    pass

# ============================================================
# 📦 Импорты
# ============================================================
import json
import time
import warnings
from datetime import datetime

import cv2
import numpy as np
import psycopg2
from insightface.app import FaceAnalysis
from ultralytics import YOLO

warnings.filterwarnings("ignore")

# ============================================================
# ⚙️ Конфигурация
# ============================================================

CACHE_DIR = "/app/cache"
MODEL_DIR = "/app/models"

EMBEDDINGS_PATH = os.path.join(CACHE_DIR, "embeddings.npy")
NAMES_PATH = os.path.join(CACHE_DIR, "names.json")
IDS_PATH = os.path.join(CACHE_DIR, "ids.json")

DB_CONFIG = {
    "host": os.getenv("IMMICH_DB_HOST", "immich_postgres"),
    "port": os.getenv("IMMICH_DB_PORT", "5432"),
    "dbname": os.getenv("IMMICH_DB_NAME", "immich"),
    "user": os.getenv("IMMICH_DB_USER", "postgres"),
    "password": os.getenv("IMMICH_DB_PASSWORD", "postgres"),
}

VIDEO_URL = os.getenv("VIDEO_URL", "0")

YOLO_MODEL = os.getenv("YOLO_MODEL", "yolo11n.pt")   # YOLOv11
YOLO_FORCE_GPU = True

INSIGHTFACE_MODEL = "antelopev2"  # строго для Immich

FACE_SIM_THRESHOLD = float(os.getenv("FACE_SIM_THRESHOLD", "0.5"))
MAX_MISSING = int(os.getenv("MAX_MISSING", "30"))
MIN_STABLE = int(os.getenv("MIN_STABLE", "10"))

# ============================================================
# 🧰 Утилиты
# ============================================================

def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    # InsightFace ожидает root/models/antelopev2
    insight_root = os.path.dirname(MODEL_DIR) or "/app"
    if insight_root.endswith("/models"):
        insight_root = os.path.dirname(insight_root)
    os.environ["INSIGHTFACE_ROOT"] = insight_root

def _l2_normalize(v: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)

# ============================================================
# 🗄️ Embeddings Immich
# ============================================================

def fetch_embeddings_from_db():
    log("📡 Подключаюсь к базе Immich...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.name, fs.embedding
        FROM person p
        JOIN asset_face af ON af."personId" = p.id
        JOIN face_search fs ON fs."faceId" = af.id
        WHERE p.name IS NOT NULL AND TRIM(p.name) <> ''
        ORDER BY p.id;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    by_id = {}

    for pid, pname, emb in rows:
        if not pname or emb is None:
            continue
        if isinstance(emb, str):
            try:
                emb = json.loads(emb)
            except Exception:
                emb = [float(x) for x in emb.strip("[] ").split(",") if x.strip()]

        emb = np.asarray(emb, dtype=np.float32)
        if emb.ndim != 1:
            continue

        rec = by_id.setdefault(pid, {"name": pname.strip(), "embs": []})
        rec["embs"].append(emb)

    ids, names, embs = [], [], []
    for pid, rec in by_id.items:
        pass
    for pid, rec in by_id.items():
        mean_emb = np.vstack(rec["embs"]).mean(axis=0)
        ids.append(pid)
        names.append(rec["name"])
        embs.append(mean_emb)

    if embs:
        embs = _l2_normalize(np.vstack(embs).astype(np.float32))
    else:
        embs = np.zeros((0, 512), dtype=np.float32)

    log(f"✅ Загружено {len(ids)} лиц из Immich:")
    for pid, name in zip(ids, names):
        log(f"   - {pid:<4} | {name}")

    return embs, names, ids


def load_or_refresh_cache(force_refresh=False):
    ensure_dirs()

    cache_exists = (
        os.path.exists(EMBEDDINGS_PATH)
        and os.path.exists(NAMES_PATH)
        and os.path.exists(IDS_PATH)
    )

    if cache_exists and not force_refresh:
        log("📦 Загружаю embeddings из кэша...")
        emb = np.load(EMBEDDINGS_PATH)
        emb = _l2_normalize(emb) if emb.size else emb

        with open(NAMES_PATH, "r", encoding="utf-8") as f:
            names = json.load(f)
        with open(IDS_PATH, "r", encoding="utf-8") as f:
            ids = json.load(f)

        log(f"✅ Кэш загружен ({len(emb)} лиц).")
        if ids:
            log("👥 Лица из кэша:")
            for pid, name in zip(ids, names):
                log(f"   - {pid:<4} | {name}")

        return emb, names, ids

    # если кэша нет → грузим из БД
    emb, names, ids = fetch_embeddings_from_db()
    np.save(EMBEDDINGS_PATH, emb)
    with open(NAMES_PATH, "w", encoding="utf-8") as f:
        json.dump(names, f, ensure_ascii=False, indent=2)
    with open(IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2)

    log("💾 Кэш обновлён.")
    return emb, names, ids

# ============================================================
# 🧠 InsightFace
# ============================================================

def init_face_analysis():
    insight_root = os.environ.get("INSIGHTFACE_ROOT", "/app")

    log(f"🧠 Инициализация InsightFace ({INSIGHTFACE_MODEL}), root={insight_root}")

    try:
        app = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            root=insight_root,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        log("✅ InsightFace запущен с CUDA/CPU.")
        return app
    except Exception as e:
        log(f"⚠️ Ошибка GPU InsightFace: {e}, пробую CPU...")
        app = FaceAnalysis(
            name=INSIGHTFACE_MODEL,
            root=insight_root,
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        log("✅ InsightFace запущен на CPU.")
        return app

# ============================================================
# 🤖 YOLOv11
# ============================================================

def init_yolo():
    log(f"🤖 Инициализация YOLOv11 модели: {YOLO_MODEL}")

    path = YOLO_MODEL
    if not os.path.isabs(path):
        os.makedirs(MODEL_DIR, exist_ok=True)
        path = os.path.join(MODEL_DIR, YOLO_MODEL)

    model = YOLO(path)

    if YOLO_FORCE_GPU:
        try:
            model.to("cuda")
            log("✅ YOLO GPU.")
        except Exception as e:
            log(f"⚠️ YOLO GPU не удалось ({e}), CPU...")
            model.to("cpu")
    else:
        model.to("cpu")
        log("YOLO CPU.")

    return model

# ============================================================
# 🎥 Камера
# ============================================================

def open_camera():
    src = VIDEO_URL
    log(f"🎥 Подключаюсь к видеопотоку: {src}")

    # Если RTSP → принудительно TCP
    if isinstance(src, str) and src.startswith("rtsp://") and "rtsp_transport" not in src:
        sep = "&" if "?" in src else "?"
        src += f"{sep}rtsp_transport=tcp"
        log(f"   Использую RTSP over TCP: {src}")

    cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        log("❌ Не удалось открыть видеопоток.")
        return None

    log("✅ Видеопоток открыт.")
    return cap

# ============================================================
# 🔁 Главный цикл YOLO + InsightFace
# ============================================================

def recognize_objects_and_faces(embeddings, names):
    cap = open_camera()
    if cap is None:
        time.sleep(5)
        cap = open_camera()
        if cap is None:
            raise RuntimeError("🚫 Камера недоступна.")

    yolo = init_yolo()
    face_app = init_face_analysis()

    tracked = {}       # { label: { "last": int, "stable": int } }
    last_reported = set()
    frame = 0
    reconnect_delay = 2

    while True:
        ret, img = cap.read()
        if not ret:
            log("⚠️ Кадр не получен — переподключение...")
            cap.release()
            time.sleep(reconnect_delay)
            cap = open_camera()
            if cap is None:
                reconnect_delay = min(reconnect_delay * 2, 60)
                continue
            reconnect_delay = 2
            continue

        frame += 1

        results = yolo.predict(img, verbose=False)
        seen = {}

        # ---------------------------------------------
        # YOLOv11 → детекция объектов (+ логика C)
        # ---------------------------------------------
        for r in results:
            boxes = r.boxes.xyxy.cpu().numpy()
            classes = r.boxes.cls.cpu().numpy().astype(int)

            for (x1, y1, x2, y2), cls in zip(boxes, classes):
                label = yolo.names.get(cls, str(cls))

                # === ВАЖНО ===
                # Сначала всегда добавляем "person"
                if label == "person":
                    seen["person"] = True
                else:
                    seen[label] = True

                # Только для person → попытка распознать лицо
                if label != "person" or embeddings.shape[0] == 0:
                    continue

                x1i, y1i = max(0, int(x1)), max(0, int(y1))
                x2i, y2i = max(0, int(x2)), max(0, int(y2))

                if x2i <= x1i or y2i <= y1i:
                    continue

                crop = img[y1i:y2i, x1i:x2i]
                if crop.size == 0 or crop.shape[0] < 64 or crop.shape[1] < 64:
                    continue

                try:
                    faces = face_app.get(crop, max_num=1)
                except Exception:
                    faces = []

                if not faces:
                    continue

                face = faces[0]

                try:
                    face_emb = np.asarray(face.embedding, dtype=np.float32)
                    if face_emb.ndim != 1:
                        continue

                    face_emb = _l2_normalize(face_emb)
                    sims = embeddings @ face_emb
                    if sims.size == 0:
                        continue

                    idx = int(np.argmax(sims))
                    max_sim = float(sims[idx])

                    if max_sim >= FACE_SIM_THRESHOLD:
                        name = names[idx] if idx < len(names) else f"id:{idx}"
                        new_label = f"person({name})"

                        log(f"🔍 Кадр {frame}: распознано лицо → {name}, sim={max_sim:.3f}")

                        # Перезаписываем "person" → "person(Имя)"
                        if "person" in seen:
                            del seen["person"]
                        seen[new_label] = True

                except Exception:
                    pass

        # ---------------------------------------------
        # Анти-дребезг
        # ---------------------------------------------
        for lbl in list(tracked.keys()):
            if lbl not in seen:
                tracked[lbl]["last"] += 1
                if tracked[lbl]["last"] > MAX_MISSING // 2:
                    tracked[lbl]["stable"] = max(0, tracked[lbl]["stable"] - 1)
                if tracked[lbl]["last"] > MAX_MISSING:
                    tracked.pop(lbl)
            else:
                tracked[lbl]["last"] = 0
                tracked[lbl]["stable"] = min(tracked[lbl]["stable"] + 1, MIN_STABLE)

        for lbl in seen:
            if lbl not in tracked:
                tracked[lbl] = {"last": 0, "stable": 0}

        current = {l for l, v in tracked.items() if v["stable"] >= MIN_STABLE}

        # ---------------------------------------------
        # Логируем изменения
        # ---------------------------------------------
        if current != last_reported:
            added = current - last_reported
            removed = last_reported - current

            if added:
                log(f"➕ Кадр {frame}: появились — {', '.join(sorted(added))}")
            if removed:
                log(f"➖ Кадр {frame}: ушли — {', '.join(sorted(removed))}")

            if added or removed:
                log(f"📸 Кадр {frame}: сейчас в кадре — {', '.join(sorted(current)) or 'никого'}")

            last_reported = current

# ============================================================
# 🚀 main
# ============================================================

if __name__ == "__main__":
    log("🚀 vision_bridge.py стартовал")

    embeddings, names, ids = load_or_refresh_cache()
    recognize_objects_and_faces(embeddings, names)
