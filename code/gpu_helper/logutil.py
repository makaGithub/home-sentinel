"""Minimal English counters for hs-gpu-helper."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RequestStats:
    received: int = 0
    processed: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _last_log_ts: float = field(default=0.0, repr=False)
    log_every_sec: float = 30.0

    def mark_received(self) -> None:
        with self._lock:
            self.received += 1

    def mark_processed(self) -> None:
        with self._lock:
            self.processed += 1
            self._maybe_log_unlocked()

    def mark_error(self) -> None:
        with self._lock:
            self.errors += 1
            self._maybe_log_unlocked()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "received": self.received,
                "processed": self.processed,
                "errors": self.errors,
            }

    def _maybe_log_unlocked(self) -> None:
        now = time.time()
        if now - self._last_log_ts < self.log_every_sec:
            return
        self._last_log_ts = now
        print(
            f"[stats] received={self.received} processed={self.processed} errors={self.errors}",
            flush=True,
        )


vision_stats = RequestStats()
audio_stats = RequestStats()
