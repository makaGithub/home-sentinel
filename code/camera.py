# camera.py
"""
Работа с видеопотоком (камера/RTSP).
"""

import os
import cv2
import threading
import time

import config
from utils import log


def open_camera(src: str, label: str = ""):
    """
    Открывает один видеопоток через OpenCV (FFMPEG).
    При RTSP принудительно добавляет TCP-транспорт.
    label — для лога (например номер камеры).
    """
    prefix = f" [{label}]" if label else ""
    log(f"🎥 Подключение к видеопотоку{prefix}: {src}")

    if isinstance(src, str) and src.startswith("rtsp://") and "rtsp_transport" not in src:
        sep = "&" if "?" in src else "?"
        src = src + f"{sep}rtsp_transport=tcp"
        log(f"   Использую RTSP over TCP{prefix}")

    # Low-latency опции для OpenCV/FFMPEG (чтобы не копить кадры “на минуты”)
    # Важно: переменная окружения должна быть задана ДО создания VideoCapture.
    if config.OPENCV_FFMPEG_CAPTURE_OPTIONS:
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = config.OPENCV_FFMPEG_CAPTURE_OPTIONS

    cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        log(f"❌ Не удалось открыть видеопоток{prefix}.")
        return None

    # Устанавливаем размер буфера на 1 кадр для минимизации задержки
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    log(f"✅ Видеопоток подключен{prefix}")
    return cap


class LatestFrameStream:
    """
    Читает видеопоток в отдельном потоке и хранит только последний кадр.
    Это устраняет накопление буфера и “задержку на минуты” при медленной обработке.
    """

    def __init__(self, cap: cv2.VideoCapture):
        self._cap = cap
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self._frame = None
        self._frame_id = 0
        self._last_ok_ts = 0.0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            ret, frame = self._cap.read()
            now = time.time()
            if ret and frame is not None:
                # Важно: OpenCV на каждом read() отдаёт новый массив,
                # поэтому достаточно просто заменить ссылку — старый кадр не “портится”.
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
                    self._last_ok_ts = now
            else:
                # Небольшая пауза, чтобы не крутить 100% CPU при потере потока
                time.sleep(0.05)

    def get_latest(self):
        """Возвращает (frame, frame_id, last_ok_ts). frame может быть None."""
        with self._lock:
            return self._frame, self._frame_id, self._last_ok_ts

    def close(self):
        self._stop.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._cap.release()
        except Exception:
            pass


def open_camera_stream(src: str | None = None, label: str = ""):
    """Открывает один видеопоток и возвращает LatestFrameStream или None. src=None — первый из config.STREAM_URLS."""
    if src is None:
        urls = config.STREAM_URLS
        src = urls[0] if urls else config.VIDEO_URL or "0"
    cap = open_camera(src, label=label)
    if cap is None:
        return None
    return LatestFrameStream(cap)


def open_camera_streams(urls: list[str]) -> list:
    """
    Открывает несколько видеопотоков. Возвращает список LatestFrameStream (или None для неудачных).
    """
    if not urls:
        return []
    streams = []
    for i, url in enumerate(urls):
        label = str(i) if len(urls) > 1 else ""
        s = open_camera_stream(src=url, label=label)
        streams.append(s)
    return streams
