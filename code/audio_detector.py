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
import traceback
from collections import deque

import numpy as np

import config
import stats
from mqtt_client import send_sound_detected
from presence_tracker import get_tracker
from utils import log


class AudioDetector:
    def __init__(self):
        classes = ', '.join(config.YAMNET_CLASSES) if config.YAMNET_CLASSES else 'все'
        log(f"🎧 Инициализация системы распознавания звуков YAMNet: {classes}")
        
        self.proc: subprocess.Popen | None = None
        self._stop = False
        self._enabled = False  # Детекция начнётся только после enable()
        self._current_frame = 0  # Номер текущего кадра (обновляется из main.py)

        # YAMNet настройки
        self.yamnet_model = None
        self.yamnet_class_names = None
        
        # Пробуем загрузить TensorFlow и YAMNet
        hub = None
        yamnet_available = False
        
        try:
            log("   Загрузка TensorFlow...")
            import tensorflow as tf
            import tensorflow_hub as hub
            yamnet_available = True
        except ImportError:
            log("⚠️ TensorFlow не установлен, детекция звуков недоступна")
        except Exception as e:
            log(f"⚠️ Ошибка импорта TensorFlow: {e}")
    
        if yamnet_available and hub is not None:
            try:
                log("   Загрузка модели YAMNet...")
                self.yamnet_model = hub.load('https://tfhub.dev/google/yamnet/1')
                
                # Загружаем названия классов YAMNet
                import csv
                class_map_path = self.yamnet_model.class_map_path().numpy().decode('utf-8')
                class_names = {}
                with open(class_map_path, 'r') as f:
                    reader = csv.reader(f)
                    for line_num, row in enumerate(reader):
                        if line_num == 0:
                            continue
                        if len(row) >= 3:
                            try:
                                class_names[int(row[0])] = row[2]
                            except ValueError:
                                continue
                self.yamnet_class_names = class_names
                log("✅ Система распознавания звуков YAMNet готова")
            except Exception as e:
                log(f"❌ Не удалось загрузить YAMNet: {e}")
                self.yamnet_model = None

        # Буфер для накопления аудио
        self.yamnet_window_size = 15680
        self.audio_buffer = deque(maxlen=self.yamnet_window_size * 2)
        
        # Порог уверенности для классификации
        self.confidence_threshold = 0.3

        # Анти-спам по времени
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
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", src,
            "-vn",
            "-ac", "1",
            "-ar", str(config.AUDIO_SAMPLE_RATE),
            "-f", "s16le",
            "pipe:1",
        ]

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=4096,
            )
            
            time.sleep(2.0)
            if self.proc.poll() is not None:
                stderr_output = ""
                if self.proc.stderr:
                    try:
                        stderr_output = self.proc.stderr.read().decode('utf-8', errors='ignore')
                    except:
                        pass
                log(f"❌ ffmpeg завершился с кодом {self.proc.returncode}")
                if stderr_output:
                    log(f"   {stderr_output[-500:]}")
        except Exception as e:
            log(f"❌ Ошибка запуска ffmpeg: {e}")
            self.proc = None

    # ----------------------------------------------------
    def _classify_with_yamnet(self, audio_data: np.ndarray) -> str | None:
        """Классифицирует звук с помощью YAMNet."""
        if not self.yamnet_model or audio_data.size < self.yamnet_window_size:
            return None
        
        if not self.yamnet_class_names:
            return None
        
        try:
            audio_float = audio_data.astype(np.float32) / 32768.0
            
            if audio_float.size > self.yamnet_window_size:
                audio_float = audio_float[:self.yamnet_window_size]
            elif audio_float.size < self.yamnet_window_size:
                padding = np.zeros(self.yamnet_window_size - audio_float.size, dtype=np.float32)
                audio_float = np.concatenate([audio_float, padding])
            
            scores, embeddings, spectrogram = self.yamnet_model(audio_float)
            scores_np = scores.numpy()
            
            if scores_np.ndim == 2:
                scores_mean = np.mean(scores_np, axis=0)
            else:
                scores_mean = scores_np
            
            # Берём top-10 для большего охвата
            top_indices = np.argsort(scores_mean)[-10:][::-1]
            
            for idx in top_indices:
                if idx >= len(scores_mean):
                    continue
                    
                confidence = float(scores_mean[idx])
                class_name = self.yamnet_class_names.get(int(idx), "")
                class_name_lower = class_name.lower()
                
                # Проверяем, содержит ли class_name любой из отслеживаемых классов
                for tracked in config.YAMNET_CLASSES:
                    if tracked in class_name_lower:
                        # Низкий порог для всех отслеживаемых звуков
                        if confidence >= 0.1:
                            return class_name  # Возвращаем оригинальное название класса
            
            return None
        except Exception as e:
            log(f"⚠️ Ошибка классификации YAMNet: {e}")
            return None

    # ----------------------------------------------------
    def _process_chunk(self, chunk: bytes):
        """Обработка одного куска PCM-данных."""
        if not chunk:
            return

        pcm = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        if pcm.size == 0:
            return

        self.audio_buffer.extend(pcm)
        
        if len(self.audio_buffer) >= self.yamnet_window_size and self.yamnet_model:
            audio_array = np.array(list(self.audio_buffer)[-self.yamnet_window_size:])
            detected_sound = self._classify_with_yamnet(audio_array)
            
            # Логируем и записываем статистику только если детекция включена
            if detected_sound and self._enabled:
                now = time.time()
                if (now - self._last_event_ts) > self.min_interval_sec or \
                   self._last_detected_sound != detected_sound:
                    self._last_event_ts = now
                    self._last_detected_sound = detected_sound
                    frame_info = f" (кадр {self._current_frame})" if self._current_frame > 0 else ""
                    log(f"🔊 Обнаружен звук: {detected_sound}{frame_info}")
                    stats.record_sound_detected(detected_sound)
                    send_sound_detected(detected_sound, frame=self._current_frame)
                    
                    # Уведомляем трекер присутствия (для звуков двери)
                    tracker = get_tracker()
                    if tracker:
                        tracker.on_door_sound(detected_sound)

    # ----------------------------------------------------
    def audio_loop(self):
        """Основной цикл чтения аудио из ffmpeg."""
        self._start_ffmpeg()
        if not self.proc or not self.proc.stdout:
            log("❌ Не удалось запустить ffmpeg для аудио")
            return

        chunk_size = 4096
        
        while not self._stop:
            try:
                if self.proc.poll() is not None:
                    log(f"❌ ffmpeg завершился с кодом {self.proc.returncode}")
                    break
                
                data = self.proc.stdout.read(chunk_size)
                if not data:
                    time.sleep(0.05)
                    continue
                
                self._process_chunk(data)
            except Exception as e:
                log(f"❌ Ошибка в аудиопотоке: {e}")
                break

    # ----------------------------------------------------
    def start(self):
        """Запускает аудиодетектор в отдельном потоке."""
        t = threading.Thread(target=self.audio_loop, daemon=True, name="AudioDetector")
        t.start()

    def enable(self):
        """Включает детекцию звуков (вызывать после завершения инициализации)."""
        self._enabled = True

    def set_frame(self, frame_num: int):
        """Обновляет номер текущего кадра (для логирования)."""
        self._current_frame = frame_num

    def stop(self):
        """Останавливает аудиодетектор и ffmpeg."""
        self._stop = True
        try:
            if self.proc:
                self.proc.kill()
        except Exception:
            pass
