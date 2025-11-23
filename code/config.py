# config.py
"""
Глобальная конфигурация home-sentinel.
Все пути, пороги, env-переменные — здесь.
"""

import os

# Директории
CACHE_DIR = "/app/cache"
MODEL_DIR = "/app/models"

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

# YOLO
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolo11n.pt")   # YOLOv11
YOLO_FORCE_GPU = True

# InsightFace
INSIGHTFACE_MODEL = "antelopev2"  # строго для Immich

# Пороги распознавания лиц
FACE_SIM_THRESHOLD = float(os.getenv("FACE_SIM_THRESHOLD", "0.55"))  # базовый порог
MIN_SIM_DIFF = float(os.getenv("MIN_SIM_DIFF", "0.08"))  # мин. разница лучшего и второго

# Анти-дребезг
MAX_MISSING = int(os.getenv("MAX_MISSING", "30"))
MIN_STABLE = int(os.getenv("MIN_STABLE", "10"))

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
