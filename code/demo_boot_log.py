# demo_boot_log.py
"""Проигрывание сохранённого boot-лога Immich (только для демонстрации)."""

from __future__ import annotations

import os
import time

from utils import log

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "demo", "immich_faces_boot.log")


def replay_immich_faces_boot(
    path: str | None = None,
    *,
    line_delay_sec: float | None = None,
    progress_delay_sec: float | None = None,
    faces_delay_sec: float | None = None,
) -> None:
    """Печатает заранее снятый лог загрузки лиц, как будто идёт реальный прогон."""
    log_path = path or os.getenv("DEMO_IMMICH_BOOT_LOG", _DEFAULT_PATH)
    if not os.path.isfile(log_path):
        log(f"⚠️ Демо-лог Immich не найден: {log_path}")
        return

    # ~8–12 сек на весь блок; DEMO_IMMICH_BOOT_SCALE=2 → в 2 раза медленнее
    scale = float(os.getenv("DEMO_IMMICH_BOOT_SCALE", "1"))
    line_delay = (line_delay_sec if line_delay_sec is not None else 0.28) * scale
    progress_delay = (
        progress_delay_sec if progress_delay_sec is not None else 0.45
    ) * scale
    faces_delay = (faces_delay_sec if faces_delay_sec is not None else 0.18) * scale

    with open(log_path, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]

    for line in lines:
        log(line)
        if "Обработано" in line:
            time.sleep(progress_delay)
        elif line.lstrip().startswith("👥"):
            time.sleep(faces_delay)
        else:
            time.sleep(line_delay)
