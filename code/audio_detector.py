# audio_detector.py
"""
Аудиодетектор:
- берёт звук из того же RTSP-потока, что и видео (config.VIDEO_URL)
- через ffmpeg вытягивает PCM (s16le)
- считает RMS (громкость)
- если звук громче порога → считает, что "speech" (как заглушка) и пишет статистику

Цель: не упасть на старте, иметь готовую структуру, легко заменить детектор позже.
"""

import subprocess
import threading
import time

import numpy as np

import config
import stats
from utils import log


class AudioDetector:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self._stop = False

        # Порог громкости (эмпирически, можно менять)
        self.rms_threshold = 1000.0

        # Анти-спам по времени (минимальный интервал между событиями, сек)
        self.min_interval_sec = 5.0
        self._last_event_ts = 0.0

    # ----------------------------------------------------
    def _start_ffmpeg(self):
        """Запускает ffmpeg, который достаёт аудио из RTSP и выдаёт сырое PCM в stdout."""
        src = str(config.VIDEO_URL)

        cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", src,
            "-vn",                      # без видео
            "-ac", "1",                 # моно
            "-ar", str(config.AUDIO_SAMPLE_RATE),
            "-f", "s16le",              # сырое PCM
            "pipe:1",
        ]

        log(f"🎤 Запуск ffmpeg аудиопотока для {src}...")
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=4096,
        )

    # ----------------------------------------------------
    def _process_chunk(self, chunk: bytes):
        """Обработка одного куска PCM-данных."""
        if not chunk:
            return

        # int16 → float32
        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if pcm.size == 0:
            return

        # RMS громкость
        rms = float(np.sqrt(np.mean(pcm**2)))

        # Если громко и прошло достаточно времени — считаем событие
        now = time.time()
        if rms > self.rms_threshold and (now - self._last_event_ts) > self.min_interval_sec:
            self._last_event_ts = now
            log(f"🔊 Обнаружен громкий звук (RMS={rms:.1f})")

            # как заглушка: если в конфиге есть "speech" — логируем её
            if "speech" in config.SOUNDS_TO_TRACK:
                stats.record_sound_detected("speech")
            else:
                # иначе — просто первый из списка
                if config.SOUNDS_TO_TRACK:
                    stats.record_sound_detected(config.SOUNDS_TO_TRACK[0])

    # ----------------------------------------------------
    def audio_loop(self):
        """Основной цикл чтения аудио из ffmpeg."""
        self._start_ffmpeg()
        if not self.proc or not self.proc.stdout:
            log("⚠️ Не удалось запустить ffmpeg для аудио")
            return

        chunk_size = 4096

        log("🎶 Аудиодетектор запущен, читаю аудиопоток...")
        while not self._stop:
            try:
                data = self.proc.stdout.read(chunk_size)
                if not data:
                    # маленький sleep, чтобы не крутить пустой цикл
                    time.sleep(0.05)
                    continue
                self._process_chunk(data)
            except Exception as e:
                log(f"⚠️ Ошибка в аудиопотоке: {e}")
                break

        log("🛑 Аудиодетектор остановлен")

    # ----------------------------------------------------
    def start(self):
        """Запускает аудиодетектор в отдельном потоке."""
        t = threading.Thread(target=self.audio_loop, daemon=True)
        t.start()
        log("🎧 AudioDetector запущен в фоновом потоке")

    def stop(self):
        """Останавливает аудиодетектор и ffmpeg."""
        self._stop = True
        try:
            if self.proc:
                self.proc.kill()
        except Exception:
            pass
