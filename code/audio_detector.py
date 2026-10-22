# audio_detector.py
"""
Аудиодетектор: ffmpeg → PCM, классификация через hs-gpu-helper (/v1/audio).
"""

import os
import select
import subprocess
import threading
import time
from collections import deque

import numpy as np

import config
import stats
from gpu_client import GpuHelperClient
from mqtt_client import send_sound_detected
from presence_tracker import get_tracker
from utils import log


class AudioDetector:
    def __init__(self, gpu: GpuHelperClient | None = None):
        classes = ", ".join(config.YAMNET_CLASSES) if config.YAMNET_CLASSES else "все"
        log(f"🎧 Инициализация аудио (YAMNet / GPU): {classes}")

        self.gpu = gpu or GpuHelperClient()
        self.proc: subprocess.Popen | None = None
        self._stop = False
        self._enabled = False
        self._current_frame = 0
        self._stderr_thread: threading.Thread | None = None
        self._last_ffmpeg_err = ""

        self.yamnet_window_size = 15680
        self.audio_buffer = deque(maxlen=self.yamnet_window_size * 2)

        self.min_interval_sec = 5.0
        self._last_event_ts = 0.0
        self._last_detected_sound = None

        self._reconnect_delay_sec = 5.0
        self._reconnect_delay_max_sec = 60.0
        self._no_data_timeout_sec = 15.0
        self._fail_streak = 0

    def _drain_stderr(self, proc: subprocess.Popen):
        """Читает stderr, чтобы PIPE не забивался и падение можно было залогировать."""
        err = proc.stderr
        if not err:
            return
        lines: list[str] = []
        try:
            for raw in iter(err.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                lines.append(line)
                if len(lines) > 20:
                    lines.pop(0)
        except Exception:
            pass
        if lines:
            self._last_ffmpeg_err = lines[-1]
            if config.DEBUG:
                for line in lines[-5:]:
                    log(f"⚠️ ffmpeg: {line}")

    def _stop_ffmpeg(self):
        if self.proc is None:
            return
        try:
            self.proc.kill()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2.0)
        except Exception:
            pass
        self.proc = None

    def _start_ffmpeg(self):
        self._stop_ffmpeg()
        self._last_ffmpeg_err = ""

        src = config.AUDIO_URL if config.AUDIO_URL else str(config.VIDEO_URL)
        is_rtsp = src.lower().startswith("rtsp://")

        # Debian ffmpeg 5.x: нет -stimeout (из‑за него был мгновенный exit 1).
        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error"]
        if is_rtsp:
            # Без -stimeout/-rw_timeout: в Debian ffmpeg 5.1 их нет → мгновенный exit 1
            cmd.extend(
                [
                    "-rtsp_transport",
                    "tcp",
                    "-rtsp_flags",
                    "prefer_tcp",
                ]
            )
        else:
            cmd.extend(
                [
                    "-reconnect",
                    "1",
                    "-reconnect_streamed",
                    "1",
                    "-reconnect_on_network_error",
                    "1",
                    "-reconnect_delay_max",
                    "5",
                ]
            )

        cmd.extend(
            [
                "-fflags",
                "+genpts+discardcorrupt",
                "-err_detect",
                "ignore_err",
                "-probesize",
                "131072",
                "-analyzeduration",
                "500000",
                "-i",
                src,
                "-vn",
                "-map",
                "0:a:0?",
                "-ac",
                "1",
                "-ar",
                str(config.AUDIO_SAMPLE_RATE),
                "-f",
                "s16le",
                "pipe:1",
            ]
        )

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr,
                args=(self.proc,),
                daemon=True,
                name="ffmpeg-stderr",
            )
            self._stderr_thread.start()
            time.sleep(1.5)
            if self.proc.poll() is not None:
                err = self._last_ffmpeg_err or f"exit {self.proc.returncode}"
                log(f"❌ ffmpeg завершился с кодом {self.proc.returncode}: {err}")
                self._stop_ffmpeg()
        except Exception as e:
            log(f"❌ Ошибка запуска ffmpeg: {e}")
            self._stop_ffmpeg()

    def _classify(self, audio_data: np.ndarray) -> tuple[str | None, float]:
        if audio_data.size < self.yamnet_window_size:
            return (None, 0.0)
        pcm = audio_data.astype(np.int16).tobytes()
        try:
            sounds = self.gpu.audio(pcm)
        except Exception as e:
            if config.DEBUG:
                log(f"⚠️ GPU audio: {e}")
            return (None, 0.0)
        if not sounds:
            return (None, 0.0)
        top = sounds[0]
        return (top.get("name"), float(top.get("confidence") or 0.0))

    def _process_chunk(self, chunk: bytes):
        if not chunk:
            return
        pcm = np.frombuffer(chunk, dtype=np.int16)
        if pcm.size == 0:
            return
        self.audio_buffer.extend(pcm)

        if len(self.audio_buffer) >= self.yamnet_window_size:
            audio_array = np.array(
                list(self.audio_buffer)[-self.yamnet_window_size :], dtype=np.int16
            )
            detected_sound, confidence = self._classify(audio_array)
            if detected_sound and self._enabled:
                now = time.time()
                if (now - self._last_event_ts) > self.min_interval_sec:
                    self._last_event_ts = now
                    self._last_detected_sound = detected_sound
                    frame_info = (
                        f" (кадр {self._current_frame})"
                        if self._current_frame > 0
                        else ""
                    )
                    log(
                        f"🔊 Обнаружен звук: {detected_sound} "
                        f"(confidence={confidence:.3f}){frame_info}"
                    )
                    stats.record_sound_detected(detected_sound)
                    send_sound_detected(detected_sound, frame=self._current_frame)
                    tracker = get_tracker()
                    if tracker:
                        tracker.on_door_sound(detected_sound)

    def _next_backoff(self) -> float:
        self._fail_streak += 1
        delay = min(
            self._reconnect_delay_sec * (1.5 ** (self._fail_streak - 1)),
            self._reconnect_delay_max_sec,
        )
        return delay

    def audio_loop(self):
        chunk_size = 4096
        while not self._stop:
            self._start_ffmpeg()
            if not self.proc or not self.proc.stdout:
                delay = self._next_backoff()
                log(
                    "❌ Не удалось запустить ffmpeg для аудио, "
                    f"переподключение через {delay:.0f} сек"
                )
                time.sleep(delay)
                continue

            audio_src = config.AUDIO_URL if config.AUDIO_URL else str(config.VIDEO_URL)
            log(f"🔊 Аудиопоток подключён: {audio_src[:80]}...")
            last_data_ts = time.time()
            got_data = False
            stdout_fd = self.proc.stdout.fileno()

            while not self._stop:
                try:
                    if self.proc.poll() is not None:
                        err = self._last_ffmpeg_err
                        suffix = f": {err}" if err else ""
                        delay = self._next_backoff()
                        log(
                            f"❌ ffmpeg завершился с кодом {self.proc.returncode}"
                            f"{suffix}, переподключение через {delay:.0f} сек"
                        )
                        break

                    ready, _, _ = select.select([stdout_fd], [], [], 1.0)
                    if not ready:
                        if (time.time() - last_data_ts) > self._no_data_timeout_sec:
                            delay = self._next_backoff()
                            log(
                                f"❌ Нет данных от ffmpeg {self._no_data_timeout_sec:.0f} сек, "
                                f"переподключение через {delay:.0f} сек"
                            )
                            break
                        continue

                    data = os.read(stdout_fd, chunk_size)
                    if not data:
                        delay = self._next_backoff()
                        log(
                            "❌ ffmpeg закрыл stdout, "
                            f"переподключение через {delay:.0f} сек"
                        )
                        break

                    last_data_ts = time.time()
                    if not got_data:
                        got_data = True
                        self._fail_streak = 0
                    self._process_chunk(data)
                except Exception as e:
                    delay = self._next_backoff()
                    log(
                        f"❌ Ошибка в аудиопотоке: {e}, "
                        f"переподключение через {delay:.0f} сек"
                    )
                    break

            self._stop_ffmpeg()
            if not self._stop:
                time.sleep(
                    self._reconnect_delay_sec
                    if self._fail_streak == 0
                    else min(
                        self._reconnect_delay_sec * (1.5 ** (self._fail_streak - 1)),
                        self._reconnect_delay_max_sec,
                    )
                )

    def start(self):
        t = threading.Thread(target=self.audio_loop, daemon=True, name="AudioDetector")
        t.start()

    def enable(self):
        self._enabled = True

    def set_frame(self, frame_num: int):
        self._current_frame = frame_num

    def stop(self):
        self._stop = True
        self._stop_ffmpeg()
