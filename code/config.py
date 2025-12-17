# config.py
"""
Глобальная конфигурация home-sentinel.
Все пути, пороги, env-переменные — здесь.
"""

import os

# Директории
CACHE_DIR = "/app/cache"
MODEL_DIR = "/app/models"
SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "/app/data/screenshots")

# Скриншоты: включить/выключить сохранение
SCREENSHOTS_ENABLED = os.getenv("SCREENSHOTS_ENABLED", "true").lower() in ("true", "1", "yes")

# Пути к файлам кэша (старый формат)
EMBEDDINGS_PATH = os.path.join(CACHE_DIR, "embeddings.npy")
NAMES_PATH = os.path.join(CACHE_DIR, "names.json")
IDS_PATH = os.path.join(CACHE_DIR, "ids.json")

# Подключение к Immich
DB_CONFIG = {
    "host": os.getenv("IMMICH_DB_HOST", "immich_postgres"),
    "port": os.getenv("IMMICH_DB_PORT", "5432"),
    "dbname": os.getenv("IMMICH_DB_NAME", "immich"),
    "user": os.getenv("IMMICH_DB_USER", "postgres"),
    "password": os.getenv("IMMICH_DB_PASSWORD", "postgres"),
}

# Отдельное имя БД для статистики home-sentinel
VISION_DB_NAME = os.getenv("VISION_DB_NAME", "home-sentinel")

# Источник видео/аудио (RTSP или локальное устройство)
VIDEO_URL = os.getenv("VIDEO_URL", "0")

# Переподключение к видеопотоку
STREAM_RECONNECT_ATTEMPTS = int(os.getenv("STREAM_RECONNECT_ATTEMPTS", "50"))  # после N неудач — переподключение
STREAM_RECONNECT_DELAY = float(os.getenv("STREAM_RECONNECT_DELAY", "2.0"))     # пауза перед переподключением (сек)
STREAM_STALE_SEC = float(os.getenv("STREAM_STALE_SEC", "2.0"))                 # если нет новых кадров дольше N сек — считаем поток “застрявшим”

# OpenCV/FFMPEG low-latency опции (применяются при открытии VideoCapture)
# Формат: "key;value|key;value|..."
OPENCV_FFMPEG_CAPTURE_OPTIONS = os.getenv(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|max_delay;0",
)

# YOLO
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolo11n.pt")   # YOLOv11
YOLO_FORCE_GPU = True
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "640"))     # размер изображения для обработки (меньше = быстрее)
YOLO_FP16 = os.getenv("YOLO_FP16", "true").lower() in ("true", "1", "yes")  # FP16 инференс (GPU)
YOLO_CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.25"))  # мин. confidence для объектов
YOLO_PERSON_CONFIDENCE = float(os.getenv("YOLO_PERSON_CONFIDENCE", "0.2"))        # отдельный порог для person (ниже)

# Игнорируемые классы YOLO (через запятую в .env)
_ignore_str = os.getenv("YOLO_IGNORE_CLASSES", "bed")
YOLO_IGNORE_CLASSES = set(c.strip() for c in _ignore_str.split(",") if c.strip())

# InsightFace
INSIGHTFACE_MODEL = "antelopev2"  # строго для Immich

# Пороги распознавания лиц
FACE_SIM_THRESHOLD = float(os.getenv("FACE_SIM_THRESHOLD", "0.55"))  # базовый порог
MIN_SIM_DIFF = float(os.getenv("MIN_SIM_DIFF", "0.08"))  # мин. разница лучшего и второго

# Анти-дребезг для важных объектов (person, dog, cat)
MAX_MISSING = int(os.getenv("MAX_MISSING", "30"))   # сколько кадров объект может отсутствовать
MIN_STABLE = int(os.getenv("MIN_STABLE", "10"))     # сколько кадров для "стабильного" появления

# Анти-дребезг для остальных объектов (более строгий)
MAX_MISSING_OTHER = int(os.getenv("MAX_MISSING_OTHER", "120"))   # дольше могут отсутствовать
MIN_STABLE_OTHER = int(os.getenv("MIN_STABLE_OTHER", "25"))      # дольше должны присутствовать

# Важные объекты (используют основные параметры анти-дребезга)
_important_str = os.getenv("IMPORTANT_OBJECTS", "person,dog,cat")
IMPORTANT_OBJECTS = set(c.strip() for c in _important_str.split(",") if c.strip())

# Улучшения распознавания лиц
FACE_PADDING_RATIO = float(os.getenv("FACE_PADDING_RATIO", "0.2"))        # 20% расширения bounding box
MAX_FACES_PER_CROP = int(os.getenv("MAX_FACES_PER_CROP", "10"))          # максимум лиц на crop
FACE_DET_SIZE = int(os.getenv("FACE_DET_SIZE", "1280"))                   # размер детекции InsightFace
MIN_FACE_SIZE = int(os.getenv("MIN_FACE_SIZE", "64"))                     # мин. размер лица (px)
FACE_TRACKING_FRAMES = int(os.getenv("FACE_TRACKING_FRAMES", "5"))        # кадров для трекинга

# Настройки кэша лиц
FACE_CACHE_VALIDITY_FRAMES = 30  # кэш действителен N кадров

# список звуков по которым вести статистику (структура ЗАРАНЕЕ)
SOUNDS_TO_TRACK = [
    "speech",
    "dog_bark",
]

# Аудио с камеры приведём к этому sample rate
AUDIO_SAMPLE_RATE = 16000

# Количество CPU потоков для обработки
CPU_THREADS = int(os.getenv("CPU_THREADS", "4"))  # количество ядер CPU для использования
