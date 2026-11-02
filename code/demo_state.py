"""
demo_state.py — Управление состоянием демо-режима между main.py и интерактивной консолью demo.py.

Этапы (stage):
- "normal"  — штатный режим (обрабатывается и видео, и аудио, и лица)
- "idle"    — демо-пауза после инициализации: НИЧЕГО не отправляется в GPU, ждём пользователя
- "objects" — Этап 1: только детекция объектов (без лиц и без звуков)
- "sounds"  — Этап 2: только распознавание звуков (без видео/объектов/лиц)
- "faces"   — Этап 3: только люди и распознавание лиц (без звуков и прочих предметов)
- "finale"  — Заключение: GPU снова на паузе, выход или возврат к этапам
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

STATE_PATH = "/tmp/hs_demo_state.json"
EVENTS_PATH = "/tmp/hs_demo_events.jsonl"


def init_demo_state(demo_mode: bool, faces_count: int = 85) -> str:
    """Инициализирует состояние при старте main.py."""
    stage = "idle" if demo_mode else "normal"
    state = {
        "stage": stage,
        "demo_mode": bool(demo_mode),
        "faces_count": int(faces_count or 85),
        "updated_at": time.time(),
    }
    _write_atomic(STATE_PATH, state)
    try:
        with open(EVENTS_PATH, "w", encoding="utf-8"):
            pass
    except Exception:
        pass
    return stage


def _write_atomic(path: str, data: dict[str, Any]) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def get_demo_state() -> dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"stage": "normal", "demo_mode": False, "faces_count": 85}


def get_demo_stage(default: str = "normal") -> str:
    return str(get_demo_state().get("stage") or default)


def set_demo_stage(stage: str) -> None:
    cur = get_demo_state()
    cur["stage"] = stage
    cur["updated_at"] = time.time()
    _write_atomic(STATE_PATH, cur)


def emit_demo_event(stage: str, text: str, kind: str = "info") -> None:
    """Пишет отформатированную строку события для подписчиков demo.py."""
    rec = {
        "ts": time.time(),
        "stage": stage,
        "kind": kind,
        "text": text,
    }
    try:
        with open(EVENTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Антиспам алертов на проектор (ключ → последний ts)
_alert_last_ts: dict[str, float] = {}


def emit_demo_alert(
    text: str,
    *,
    kind: str = "warn",
    stage: str | None = None,
    key: str | None = None,
    min_interval: float = 8.0,
) -> bool:
    """
    Критичный статус для демо-консоли (камера / GPU / аудио).
    stage=None → текущий этап; stage='*' → показать на любом этапе.
    Возвращает True, если событие реально записали (не отрезали антиспамом).
    """
    now = time.time()
    alert_key = key or f"{kind}:{text[:48]}"
    last = _alert_last_ts.get(alert_key, 0.0)
    if min_interval > 0 and (now - last) < min_interval:
        return False
    _alert_last_ts[alert_key] = now

    if stage is None:
        default = "idle" if bool(get_demo_state().get("demo_mode")) else "normal"
        stage = get_demo_stage(default)
    emit_demo_event(stage, text, kind=kind)
    return True


def clear_demo_alert_key(key: str) -> None:
    """Сброс антиспама (после успешного восстановления)."""
    _alert_last_ts.pop(key, None)
