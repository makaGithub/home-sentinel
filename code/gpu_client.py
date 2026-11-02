"""HTTP client for hs-gpu-helper (GPU inference in k8s)."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np
import requests

import config
from embeddings import faces_to_pickle_blob, load_faces_db_or_cache
from utils import C_CYAN, C_GREEN, C_RED, C_RESET, C_YELLOW, log


class GpuHelperClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or config.GPU_HELPER_URL).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self.remote_faces: int = 0

    def get_faces_count(self) -> int:
        """Возвращает число лиц, уже загруженных в память hs-gpu-helper."""
        try:
            r = self._session.get(f"{self.base_url}/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                self.remote_faces = int(data.get("faces") or 0)
                return self.remote_faces
        except Exception:
            pass
        return self.remote_faces

    def wait_ready(self, retries: int = 60, delay: float = 5.0) -> bool:
        log(f"🎮 {C_CYAN}Связь с GPU-сервером (CUDA)...{C_RESET}")
        for attempt in range(1, retries + 1):
            try:
                r = self._session.get(f"{self.base_url}/health", timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    self.remote_faces = int(data.get("faces") or 0)
                    if data.get("ready"):
                        log(f"✅ {C_GREEN}GPU готова к работе{C_RESET}")
                        return True
                    log(f"   прогрев моделей на GPU... ({attempt}/{retries})")
            except Exception:
                log(f"   ожидание GPU... ({attempt}/{retries})")
            time.sleep(delay)
        log(f"❌ {C_RED}GPU недоступна{C_RESET}")
        return False

    def sync_faces(self, force: bool = False) -> int:
        """
        Тянет лица из Immich (или кэша) и заливает в hs-gpu-helper.
        Если на gpu-helper лица уже загружены (> 0), пропускает повторную заливку.
        """
        if not force and not config.FORCE_SYNC_FACES:
            existing = self.get_faces_count()
            if existing > 0:
                log(
                    f"✅ {C_GREEN}База лиц уже на GPU:{C_RESET} "
                    f"{C_YELLOW}{existing} чел.{C_RESET} (пропуск загрузки)"
                )
                return existing

        (embs, names, ids, confs), source = load_faces_db_or_cache()
        blob = faces_to_pickle_blob(embs, names, ids, confs)
        log(
            f"📤 {C_CYAN}Загрузка лиц на GPU{C_RESET} "
            f"({len(names)} чел., {len(blob) / 1e6:.1f} MB, {source})..."
        )
        r = self._session.post(
            f"{self.base_url}/v1/faces",
            data=blob,
            headers={"Content-Type": "application/octet-stream"},
            timeout=max(self.timeout, 120.0),
        )
        r.raise_for_status()
        people = int(r.json().get("people") or len(names))
        self.remote_faces = people
        log(f"✅ {C_GREEN}Лица на GPU: {C_YELLOW}{people} чел.{C_RESET}")
        return people

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
