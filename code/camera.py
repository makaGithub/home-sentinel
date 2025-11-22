# camera.py
"""
Работа с видеопотоком (камера/RTSP).
"""

import cv2

import config
from utils import log


def open_camera():
    """
    Открывает видеопоток через OpenCV (FFMPEG).
    При RTSP принудительно добавляет TCP-транспорт.
    """
    src = config.VIDEO_URL
    log(f"🎥 Подключаюсь к видеопотоку: {src}")

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
