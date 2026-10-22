"""HTTP client for hs-gpu-helper (GPU inference in k8s)."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import requests

import config
from utils import log


class GpuHelperClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or config.GPU_HELPER_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    def wait_ready(self, retries: int = 60, delay: float = 5.0) -> bool:
        log("🎮 Инициализация CUDA / загрузка моделей на GPU...")
        for attempt in range(1, retries + 1):
            try:
                r = self._session.get(f"{self.base_url}/health", timeout=5)
                if r.status_code == 200 and r.json().get("ready"):
                    log("✅ GPU готова (CUDA)")
                    return True
                if r.status_code == 200:
                    log(f"   загрузка моделей на GPU... ({attempt}/{retries})")
            except Exception:
                log(f"   ожидание GPU... ({attempt}/{retries})")
            time.sleep(delay)
        log("❌ GPU недоступна")
        return False

    def vision(self, img: np.ndarray) -> list[dict[str, Any]]:
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return []
        r = self._session.post(
            f"{self.base_url}/v1/vision",
            data=buf.tobytes(),
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return list(r.json().get("objects") or [])

    def audio(self, pcm_s16le: bytes) -> list[dict[str, Any]]:
        r = self._session.post(
            f"{self.base_url}/v1/audio",
            data=pcm_s16le,
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return list(r.json().get("sounds") or [])
