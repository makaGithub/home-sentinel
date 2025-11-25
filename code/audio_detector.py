# audio_detector.py
"""
Аудиодетектор с YAMNet:
- берёт звук из того же RTSP-потока, что и видео (config.VIDEO_URL)
- через ffmpeg вытягивает PCM (s16le)
- использует YAMNet для классификации звуков (речь, лай собаки, стук в дверь)
- записывает статистику при обнаружении отслеживаемых звуков
"""

import subprocess
import threading
import time
from collections import deque

import numpy as np

try:
    import tensorflow as tf
    import tensorflow_hub as hub
    YAMNET_AVAILABLE = True
except ImportError:
    YAMNET_AVAILABLE = False

import config
import stats
from utils import log


class AudioDetector:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self._stop = False

        # YAMNet настройки
        self.yamnet_model = None
        self.yamnet_class_names = None
        
        if YAMNET_AVAILABLE:
            try:
                log("🎵 Загрузка модели YAMNet...")
                self.yamnet_model = hub.load('https://tfhub.dev/google/yamnet/1')
                # Загружаем названия классов YAMNet
                class_map_path = self.yamnet_model.class_map_path().numpy().decode('utf-8')
                class_names = {}
                with open(class_map_path, 'r') as f:
                    for line in f:
                        parts = line.strip().split(',')
                        if len(parts) >= 2:
                            class_names[int(parts[0])] = parts[1]
                self.yamnet_class_names = class_names
                log("✅ YAMNet загружен успешно")
            except Exception as e:
                log(f"⚠️ Не удалось загрузить YAMNet: {e}")
                log("   Будет использоваться простая детекция по громкости")
                self.yamnet_model = None
        else:
            log("⚠️ TensorFlow не установлен, используется простая детекция по громкости")

        # Буфер для накопления аудио (YAMNet работает с окнами ~0.96 сек)
        # 16kHz * 0.96 = 15360 сэмплов
        self.yamnet_window_size = 15680  # YAMNet требует именно это количество
        self.audio_buffer = deque(maxlen=self.yamnet_window_size * 2)  # буфер на 2 окна
        
        # Маппинг классов YAMNet на наши звуки
        self.sound_mapping = {
            "Speech": "speech",
            "Dog": "dog_bark",
            "Dog bark, bow-wow": "dog_bark",
            "Bark": "dog_bark",
            "Knock": "door_knock",
            "Door": "door_knock",
        }
        
        # Порог уверенности для классификации
        self.confidence_threshold = 0.3

        # Анти-спам по времени (минимальный интервал между событиями, сек)
        self.min_interval_sec = 5.0
        self._last_event_ts = 0.0
        self._last_detected_sound = None

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
    def _classify_with_yamnet(self, audio_data: np.ndarray) -> str | None:
        """Классифицирует звук с помощью YAMNet."""
        if not self.yamnet_model or audio_data.size < self.yamnet_window_size:
            return None
        
        try:
            # Нормализуем в диапазон [-1, 1]
            audio_float = audio_data.astype(np.float32) / 32768.0
            
            # YAMNet ожидает именно 15680 сэмплов
            if audio_float.size > self.yamnet_window_size:
                audio_float = audio_float[:self.yamnet_window_size]
            elif audio_float.size < self.yamnet_window_size:
                # Дополняем нулями если не хватает
                padding = np.zeros(self.yamnet_window_size - audio_float.size, dtype=np.float32)
                audio_float = np.concatenate([audio_float, padding])
            
            # Классификация
            scores, embeddings, spectrogram = self.yamnet_model(audio_float)
            
            # Берем топ-3 предсказания
            top_indices = np.argsort(scores.numpy())[-3:][::-1]
            
            for idx in top_indices:
                confidence = float(scores.numpy()[idx])
                if confidence < self.confidence_threshold:
                    continue
                
                class_name = self.yamnet_class_names.get(int(idx), "")
                
                # Проверяем маппинг
                for yamnet_name, our_sound in self.sound_mapping.items():
                    if yamnet_name.lower() in class_name.lower():
                        if our_sound in config.SOUNDS_TO_TRACK:
                            return our_sound
            
            return None
        except Exception as e:
            log(f"⚠️ Ошибка классификации YAMNet: {e}")
            return None

    # ----------------------------------------------------
    def _process_chunk(self, chunk: bytes):
        """Обработка одного куска PCM-данных."""
        if not chunk:
            return

        # int16 → float32
        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if pcm.size == 0:
            return

        # Добавляем в буфер
        self.audio_buffer.extend(pcm)
        
        # Если накопили достаточно данных для YAMNet
        if len(self.audio_buffer) >= self.yamnet_window_size and self.yamnet_model:
            audio_array = np.array(list(self.audio_buffer)[-self.yamnet_window_size:])
            detected_sound = self._classify_with_yamnet(audio_array)
            
            if detected_sound:
                now = time.time()
                # Проверяем анти-спам и что это новый звук
                if (now - self._last_event_ts) > self.min_interval_sec or \
                   self._last_detected_sound != detected_sound:
                    self._last_event_ts = now
                    self._last_detected_sound = detected_sound
                    log(f"🔊 Обнаружен звук: {detected_sound}")
                    stats.record_sound_detected(detected_sound)
        else:
            # Fallback: простая детекция по громкости (если YAMNet не работает)
        rms = float(np.sqrt(np.mean(pcm**2)))
            rms_threshold = 1000.0

        now = time.time()
            if rms > rms_threshold and (now - self._last_event_ts) > self.min_interval_sec:
            self._last_event_ts = now
            log(f"🔊 Обнаружен громкий звук (RMS={rms:.1f})")

            # как заглушка: если в конфиге есть "speech" — логируем её
            if "speech" in config.SOUNDS_TO_TRACK:
                stats.record_sound_detected("speech")
                elif config.SOUNDS_TO_TRACK:
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
