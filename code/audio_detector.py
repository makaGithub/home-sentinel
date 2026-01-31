# audio_detector.py
"""
Аудиодетектор с YAMNet:
- берёт звук из того же RTSP-потока, что и видео (config.VIDEO_URL)
- через ffmpeg вытягивает PCM (s16le)
- использует YAMNet для классификации звуков (речь, лай собаки, стук в дверь)
- записывает статистику при обнаружении отслеживаемых звуков
"""

import os
import select
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
                # Индексы YAMNet только для классов из YAMNET_CLASSES (точное совпадение имени)
                # "knock" не матчит "Engine knocking", "door" не матчит "Doorbell"/"Sliding door"
                self._tracked_indices = []
                for idx, name in class_names.items():
                    if name.lower() in config.YAMNET_CLASSES:
                        self._tracked_indices.append((idx, name))
                log("✅ Система распознавания звуков YAMNet готова")
            except Exception as e:
                log(f"❌ Не удалось загрузить YAMNet: {e}")
                self.yamnet_model = None

        self._tracked_indices = getattr(self, "_tracked_indices", [])

        # Буфер для накопления аудио
        self.yamnet_window_size = 15680
        self.audio_buffer = deque(maxlen=self.yamnet_window_size * 2)
        
        # Порог уверенности для классификации
        self.confidence_threshold = 0.3

        # Анти-спам по времени
        self.min_interval_sec = 5.0
        self._last_event_ts = 0.0
        self._last_detected_sound = None

        # Отладочное логирование scores (раз в N сек)
        self._debug_interval_sec = 15.0
        self._last_debug_ts = 0.0

        # Переподключение при обрыве потока
        self._reconnect_delay_sec = 5.0
        self._no_data_timeout_sec = 10.0

    # ----------------------------------------------------
    def _start_ffmpeg(self):
        """Запускает ffmpeg, который достаёт аудио из RTSP/HTTP и выдаёт сырое PCM в stdout.
        Ожидается поток go2rtc: H.264 + Opus (2ch, 32k) → декодируем в mono 16kHz для YAMNet.
        Можно использовать отдельный AUDIO_URL (например HTTP-FLV) для большей стабильности.
        """
        if self.proc is not None:
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None
        
        # Используем AUDIO_URL если задан, иначе VIDEO_URL
        src = config.AUDIO_URL if config.AUDIO_URL else str(config.VIDEO_URL)
        is_rtsp = src.lower().startswith("rtsp://")

        # Базовые опции
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel", "error",
        ]
        
        # Опции для RTSP
        if is_rtsp:
            cmd.extend([
                "-rtsp_transport", "tcp",
                "-rtsp_flags", "prefer_tcp",
                "-stimeout", "5000000",      # socket timeout 5 сек (в микросекундах)
            ])
        else:
            # Для HTTP-FLV/HTTP переподключение при обрыве
            cmd.extend([
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
            ])
        
        cmd.extend([
            "-fflags", "+nobuffer+genpts+discardcorrupt",
            "-flags", "low_delay",
            "-probesize", "131072",
            "-analyzeduration", "500000",
            "-i", src,
        ])
        
        # Для HTTP-FLV/MP4 явно выбираем аудио поток и игнорируем видео ошибки
        if not is_rtsp:
            cmd.extend(["-map", "0:a:0"])  # первый аудио поток
        else:
            cmd.append("-vn")
        
        cmd.extend([
            "-ac", "1",
            "-ar", str(config.AUDIO_SAMPLE_RATE),
            "-f", "s16le",
            "pipe:1",
        ])

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
    def _classify_with_yamnet(self, audio_data: np.ndarray) -> tuple[str | None, float]:
        """Классифицирует звук с помощью YAMNet. Возвращает (имя_класса, confidence)."""
        if not self.yamnet_model or audio_data.size < self.yamnet_window_size:
            return (None, 0.0)
        
        if not self.yamnet_class_names:
            return (None, 0.0)
        
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

            # Редкое отладочное логирование (только при DEBUG=1): scores по отслеживаемым классам и топ-3 общих
            now = time.time()
            if config.DEBUG and self._enabled and (now - self._last_debug_ts) >= self._debug_interval_sec:
                self._last_debug_ts = now
                tracked_parts = [f"{name}={float(scores_mean[idx]):.3f}" for idx, name in self._tracked_indices]
                top3_idx = np.argsort(scores_mean)[-3:][::-1]
                top3_parts = [f"{self.yamnet_class_names.get(int(i), '?')}={float(scores_mean[i]):.3f}" for i in top3_idx]
                log(f"🔊 [YAMNet] отслеживаемые: {' '.join(tracked_parts)} | топ-3: {' '.join(top3_parts)}")
            
            # Проверяем все отслеживаемые классы, порог — из YAMNET_CLASS_THRESHOLDS или общий
            default_threshold = config.YAMNET_CONFIDENCE_THRESHOLD
            best_name = None
            best_score = 0.0
            for idx, class_name in self._tracked_indices:
                if idx >= len(scores_mean):
                    continue
                confidence = float(scores_mean[idx])
                threshold = config.YAMNET_CLASS_THRESHOLDS.get(class_name.lower(), default_threshold)
                if confidence >= threshold and confidence > best_score:
                    best_score = confidence
                    best_name = class_name
            return (best_name, best_score) if best_name else (None, 0.0)
        except Exception as e:
            log(f"⚠️ Ошибка классификации YAMNet: {e}")
            return (None, 0.0)

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
            detected_sound, confidence = self._classify_with_yamnet(audio_array)
            
            # Логируем и записываем статистику только если детекция включена
            # Общий cooldown для любых звуков (не только одинаковых)
            if detected_sound and self._enabled:
                now = time.time()
                if (now - self._last_event_ts) > self.min_interval_sec:
                    self._last_event_ts = now
                    self._last_detected_sound = detected_sound
                    frame_info = f" (кадр {self._current_frame})" if self._current_frame > 0 else ""
                    log(f"🔊 Обнаружен звук: {detected_sound} (confidence={confidence:.3f}){frame_info}")
                    stats.record_sound_detected(detected_sound)
                    send_sound_detected(detected_sound, frame=self._current_frame)
                    
                    # Уведомляем трекер присутствия (для звуков двери)
                    tracker = get_tracker()
                    if tracker:
                        tracker.on_door_sound(detected_sound)

    # ----------------------------------------------------
    def audio_loop(self):
        """Основной цикл чтения аудио из ffmpeg. При обрыве — переподключение."""
        chunk_size = 4096

        while not self._stop:
            self._start_ffmpeg()
            if not self.proc or not self.proc.stdout:
                log("❌ Не удалось запустить ffmpeg для аудио, переподключение через %.0f сек" % self._reconnect_delay_sec)
                time.sleep(self._reconnect_delay_sec)
                continue

            audio_src = config.AUDIO_URL if config.AUDIO_URL else str(config.VIDEO_URL)
            if ".flv" in audio_src.lower():
                log("⚠️ FLV не поддерживает Opus! Используй MP4: ?src=cam1 → stream.mp4?src=cam1")
            log(f"🔊 Аудиопоток подключён (YAMNet): {audio_src[:80]}...")
            last_data_ts = time.time()
            stdout_fd = self.proc.stdout.fileno()

            while not self._stop:
                try:
                    if self.proc.poll() is not None:
                        log(f"❌ ffmpeg завершился с кодом {self.proc.returncode}, переподключение через %.0f сек" % self._reconnect_delay_sec)
                        break

                    # Неблокирующее чтение через select с таймаутом 1 сек
                    ready, _, _ = select.select([stdout_fd], [], [], 1.0)
                    if not ready:
                        # Таймаут select — данных нет
                        if (time.time() - last_data_ts) > self._no_data_timeout_sec:
                            log("❌ Нет данных от ffmpeg %.0f сек, переподключение" % self._no_data_timeout_sec)
                            break
                        continue

                    # os.read возвращает только доступные данные (не блокируется)
                    data = os.read(stdout_fd, chunk_size)
                    if not data:
                        # EOF — ffmpeg закрыл stdout
                        log("❌ ffmpeg закрыл stdout, переподключение через %.0f сек" % self._reconnect_delay_sec)
                        break

                    last_data_ts = time.time()
                    self._process_chunk(data)
                except Exception as e:
                    log(f"❌ Ошибка в аудиопотоке: {e}, переподключение через %.0f сек" % self._reconnect_delay_sec)
                    break

            if not self._stop:
                time.sleep(self._reconnect_delay_sec)

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
