# utils.py
"""
Утилиты: логирование, директории, нормализация, предобработка лиц.
"""

import os
from datetime import datetime

import cv2
import numpy as np

import config


def log(msg: str):
    """Стандартный логгер с timestamp."""
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def ensure_dirs():
    """Создаёт необходимые директории и настраивает INSIGHTFACE_ROOT."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)

    # InsightFace ожидает root/models/antelopev2
    insight_root = os.path.dirname(config.MODEL_DIR) or "/app"
    if insight_root.endswith("/models"):
        insight_root = os.path.dirname(insight_root)
    os.environ["INSIGHTFACE_ROOT"] = insight_root


def _l2_normalize(v: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """L2-нормализация вектора/массивов по последней оси."""
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def preprocess_face_crop(crop: np.ndarray) -> np.ndarray:
    """Предобработка изображения лица: CLAHE для улучшения контраста."""
    if crop.size == 0:
        return crop
    try:
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return crop


def adaptive_threshold(face_size: int, base_threshold: float) -> float:
    """Адаптивный порог сходства в зависимости от размера лица (в пикселях)."""
    if face_size < 100:
        # Немного более строгий для маленьких лиц
        return max(0.5, base_threshold - 0.03)
    elif face_size > 200:
        # Немного более мягкий для крупных лиц
        return min(0.6, base_threshold + 0.02)
    return base_threshold
