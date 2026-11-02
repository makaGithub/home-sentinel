# audio_detector.py
"""
Аудиодетектор: ffmpeg → PCM, классификация через hs-gpu-helper (/v1/audio).
В демо-режиме отправляет аудио в GPU только на этапе "sounds".
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
from demo_state import (
    clear_demo_alert_key,
    emit_demo_alert,
    emit_demo_event,
    get_demo_stage,
)
from gpu_client import GpuHelperClient
from mqtt_client import send_sound_detected
from presence_tracker import get_tracker
from utils import (
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RED,
    C_RESET,
    C_YELLOW,
    format_sound_short,
    is_demo_priority_sound,
    log,
    sound_demo_group,
)


class AudioDetector:
    def __init__(self, gpu: GpuHelperClient | None = None):
        classes = ", ".join(config.YAMNET_CLASSES) if config.YAMNET_CLASSES else "все"
        log(f"🎧 {C_CYAN}Слух (YAMNet):{C_RESET} {classes}")

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
        self.demo_min_interval_sec = 1.2
        self._last_event_ts = 0.0
        self._last_detected_sound = None
        self._last_announced_group: str | None = None
        self._last_announce_stage: str | None = None

        self._reconnect_delay_sec = 5.0
        self._reconnect_delay_max_sec = 60.0
        self._no_data_timeout_sec = 15.0
        self._fail_streak = 0

    def _drain_stderr(self, proc: subprocess.Popen):
        """Читает stderr, чтобы PIPE не забивался."""
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

        cmd = ["ffmpeg", "-nostdin", "-loglevel", "error"]
        if is_rtsp:
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
                log(f"❌ {C_RED}ffmpeg exit {self.proc.returncode}:{C_RESET} {err}")
                self._demo_audio_down(
                    f"⚠️ {C_YELLOW}Аудио:{C_RESET} ffmpeg оборвался"
                )
                self._stop_ffmpeg()
        except Exception as e:
            log(f"❌ {C_RED}Ошибка запуска ffmpeg:{C_RESET} {e}")
            self._demo_audio_down(
                f"⚠️ {C_YELLOW}Аудио:{C_RESET} не удалось запустить ffmpeg"
            )
            self._stop_ffmpeg()

    def _demo_audio_down(self, text: str) -> None:
        """Показать алерт только если сейчас этап sounds (или * при DEMO)."""
        stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
        if stage == "sounds" or (config.DEMO_MODE and stage in ("idle", "sounds")):
            emit_demo_alert(
                text,
                kind="warn",
                stage="sounds" if stage == "sounds" else "*",
                key="audio_down",
                min_interval=10.0,
            )

    def _pick_demo_sound(self, sounds: list) -> tuple[str | None, float]:
        """На этапе sounds предпочитаем стук / хлопки / музыку."""
        if not sounds:
            return (None, 0.0)
        priority = [
            s
            for s in sounds
            if is_demo_priority_sound(str(s.get("name") or ""))
        ]
        pool = priority if priority else sounds
        pool.sort(key=lambda x: float(x.get("confidence") or 0.0), reverse=True)
        top = pool[0]
        return (top.get("name"), float(top.get("confidence") or 0.0))

    def _classify(self, audio_data: np.ndarray) -> tuple[str | None, float]:
        if audio_data.size < self.yamnet_window_size:
            return (None, 0.0)
        pcm = audio_data.astype(np.int16).tobytes()
        try:
            sounds = self.gpu.audio(pcm)
            clear_demo_alert_key("gpu_audio")
        except Exception as e:
            if config.DEBUG:
                log(f"⚠️ GPU audio: {e}")
            stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
            if stage == "sounds":
                emit_demo_alert(
                    f"⚠️ {C_YELLOW}GPU:{C_RESET} audio недоступен, жду…",
                    kind="warn",
                    stage="sounds",
                    key="gpu_audio",
                    min_interval=8.0,
                )
            return (None, 0.0)
        if not sounds:
            return (None, 0.0)
        stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
        if stage == "sounds":
            return self._pick_demo_sound(sounds)
        top = sounds[0]
        return (top.get("name"), float(top.get("confidence") or 0.0))

    def _process_chunk(self, chunk: bytes):
        if not chunk:
            return
        pcm = np.frombuffer(chunk, dtype=np.int16)
        if pcm.size == 0:
            return
        self.audio_buffer.extend(pcm)

        if not self._enabled or len(self.audio_buffer) < self.yamnet_window_size:
            return

        stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
        # В демо-режиме звук только на этапе "sounds" (idle/objects/faces/finale — без GPU)
        if stage not in ("normal", "sounds"):
            return

        audio_array = np.array(
            list(self.audio_buffer)[-self.yamnet_window_size :], dtype=np.int16
        )
        detected_sound, confidence = self._classify(audio_array)
        if not detected_sound:
            return

        # На демо-этапе sounds показываем только стук / хлопки / музыку
        if stage == "sounds" and config.DEMO_PRIORITY_SOUNDS:
            if not is_demo_priority_sound(detected_sound):
                return

        now = time.time()
        group = sound_demo_group(detected_sound) or (detected_sound or "").lower()

        if stage == "sounds":
            if self._last_announce_stage != "sounds":
                self._last_announced_group = None
            self._last_announce_stage = "sounds"
            # Одна строка на тип (стук / хлопки / музыка), пока не сменится
            if group and group == self._last_announced_group:
                return
        else:
            self._last_announced_group = None
            self._last_announce_stage = stage
            interval = self.min_interval_sec
            if (now - self._last_event_ts) <= interval:
                return

        self._last_event_ts = now
        self._last_detected_sound = detected_sound
        self._last_announced_group = group
        snd_text = format_sound_short(detected_sound, confidence)

        if stage == "sounds":
            if group == "knock":
                ha = "🏠 Умный дом: внимание, стук!"
            elif group == "clap":
                ha = "🏠 Умный дом: хлопки!"
            elif group == "music":
                ha = "🏠 Умный дом: музыка в эфире!"
            else:
                ha = "🏠 Умный дом"
            msg = f"🔊 {snd_text}  {C_DIM}→ {ha}{C_RESET}"
            log(msg)
            emit_demo_event("sounds", msg, kind="sound")
        else:
            log(f"🔊 Звук: {snd_text}")

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
                log(f"❌ {C_RED}Аудио недоступно, повтор через {delay:.0f}с{C_RESET}")
                self._demo_audio_down(
                    f"⚠️ {C_YELLOW}Аудио:{C_RESET} нет потока, повтор через {delay:.0f}с"
                )
                time.sleep(delay)
                continue

            log(f"🔊 {C_GREEN}Аудиопоток подключён{C_RESET}")
            stage = get_demo_stage("idle" if config.DEMO_MODE else "normal")
            if stage == "sounds":
                clear_demo_alert_key("audio_down")
                emit_demo_alert(
                    f"✅ {C_GREEN}Аудиопоток подключён{C_RESET}",
                    kind="info",
                    stage="sounds",
                    key="audio_ok",
                    min_interval=5.0,
                )
            last_data_ts = time.time()
            got_data = False
            stdout_fd = self.proc.stdout.fileno()

            while not self._stop:
                try:
                    if self.proc.poll() is not None:
                        delay = self._next_backoff()
                        self._demo_audio_down(
                            f"⚠️ {C_YELLOW}Аудио:{C_RESET} поток оборвался"
                        )
                        break

                    ready, _, _ = select.select([stdout_fd], [], [], 1.0)
                    if not ready:
                        if (time.time() - last_data_ts) > self._no_data_timeout_sec:
                            self._next_backoff()
                            self._demo_audio_down(
                                f"⚠️ {C_YELLOW}Аудио:{C_RESET} тишина/нет данных от ffmpeg"
                            )
                            break
                        continue

                    data = os.read(stdout_fd, chunk_size)
                    if not data:
                        self._next_backoff()
                        break

                    last_data_ts = time.time()
                    if not got_data:
                        got_data = True
                        self._fail_streak = 0
                    self._process_chunk(data)
                except Exception:
                    self._next_backoff()
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
