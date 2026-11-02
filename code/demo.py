#!/usr/bin/env python3
"""
demo.py — Интерактивная шоу-консоль «Страж дома» для выступления (запуск: docker exec -it home-sentinel python3 demo.py).

Управление:
  [→] / [Пробел] / [Enter] — следующий этап (с паузой «Enter · продолжить»)
  [←] / [Backspace]        — предыдущий этап
  [1] Объекты  [2] Звуки  [3] Лица  [4] Заключение
  [R] Заставка старта (пауза GPU)   [C] Очистить экран   [Q] Выход
"""

from __future__ import annotations

import json
import os
import select
import sys
import termios
import time
import tty

import config
from demo_state import EVENTS_PATH, get_demo_state, set_demo_stage
from utils import (
    C_BG_CYAN,
    C_BG_GREEN,
    C_BG_MAGENTA,
    C_BOLD,
    C_CYAN,
    C_DIM,
    C_GREEN,
    C_MAGENTA,
    C_RESET,
    C_WHITE,
    C_YELLOW,
)

STAGES = ["idle", "objects", "sounds", "faces", "finale"]


def _clear() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _print(line: str = "") -> None:
    sys.stdout.write(line + "\r\n")
    sys.stdout.flush()


def play_boot_sequence(faces_count: int, animate: bool = True) -> None:
    """Короткая эффектная демонстрация старта программы (компактные строки для проектора)."""
    _clear()
    _print(f"{C_CYAN}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{C_RESET}")
    _print(
        f"{C_CYAN}┃{C_RESET}  🛡️  {C_BOLD}{C_GREEN}СТРАЖ ДОМА · LIVE DEMO{C_RESET}                {C_CYAN}┃{C_RESET}"
    )
    _print(f"{C_CYAN}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{C_RESET}")

    steps = [
        (
            0.35,
            f"⚡ {C_CYAN}GPU-сервер{C_RESET} .... {C_GREEN}ОК{C_RESET} "
            f"{C_DIM}(кулеры на взлёт 🚀){C_RESET}",
        ),
        (
            0.35,
            f"🎥 {C_CYAN}Камера Pi{C_RESET} ..... {C_GREEN}поток + звук активны{C_RESET}",
        ),
        (
            0.35,
            f"🧠 {C_CYAN}Нейросети{C_RESET} ..... {C_YELLOW}YOLO · YAMNet · InsightFace{C_RESET}",
        ),
        (
            0.40,
            f"👨‍👩‍👦 {C_CYAN}Архив Immich{C_RESET} .. {C_GREEN}{faces_count} лиц в памяти{C_RESET} "
            f"{C_DIM}(кот в пролёте 🐱){C_RESET}",
        ),
    ]

    for delay, text in steps:
        if animate:
            time.sleep(delay)
        _print(text)

    if animate:
        time.sleep(0.25)
    _print("")
    _print(
        f"{C_BG_GREEN} ГОТОВО {C_RESET} {C_WHITE}Система ждёт команду (GPU на паузе){C_RESET}"
    )
    _print(
        f"{C_DIM}──────────────────────────────────────────────{C_RESET}"
    )
    _print(
        f"Нажмите {C_BOLD}{C_YELLOW}[→]{C_RESET} или {C_BOLD}{C_YELLOW}[Enter]{C_RESET} "
        f"→ {C_CYAN}Этап 1: Объекты{C_RESET}"
    )
    _print(
        f"{C_DIM}Клавиши: [←/→] этапы · [1·2·3·4] выбор · [Q] выход{C_RESET}"
    )


STAGE_TITLES = {
    "idle": "Старт · GPU на паузе",
    "objects": "Этап 1/3 · Объекты",
    "sounds": "Этап 2/3 · Звуки",
    "faces": "Этап 3/3 · Люди и лица",
    "finale": "Заключение",
}


def render_stage_header(stage: str) -> None:
    """Рисует компактную шапку текущего этапа с подсказками навигации."""
    _clear()
    if stage == "objects":
        _print(f"{C_CYAN}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{C_RESET}")
        _print(
            f"{C_CYAN}┃{C_RESET} 📦 {C_BOLD}{C_CYAN}ЭТАП 1/3 · ОБЪЕКТЫ В КАДРЕ (YOLO){C_RESET}      {C_CYAN}┃{C_RESET}"
        )
        _print(f"{C_CYAN}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{C_RESET}")
        _print(
            f" {C_DIM}[←] Старт{C_RESET}   "
            f"{C_BOLD}{C_YELLOW}[→] Далее: 2. Звуки{C_RESET}   "
            f"{C_DIM}[1·2·3]{C_RESET}"
        )
        _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
        _print(f"👀 {C_WHITE}Покажите предмет камере{C_RESET}\r\n")

    elif stage == "sounds":
        _print(f"{C_MAGENTA}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{C_RESET}")
        _print(
            f"{C_MAGENTA}┃{C_RESET} 🎧 {C_BOLD}{C_MAGENTA}ЭТАП 2/3 · РАСПОЗНАВАНИЕ ЗВУКОВ{C_RESET}        {C_MAGENTA}┃{C_RESET}"
        )
        _print(f"{C_MAGENTA}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{C_RESET}")
        _print(
            f" {C_BOLD}{C_YELLOW}[←] 1. Объекты{C_RESET}   "
            f"{C_BOLD}{C_YELLOW}[→] Далее: 3. Лица{C_RESET}   "
            f"{C_DIM}[1·2·3]{C_RESET}"
        )
        _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
        _print(f"🎙 {C_WHITE}Слушаю эфир (постучите или хлопните)...{C_RESET}\r\n")

    elif stage == "faces":
        _print(f"{C_GREEN}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{C_RESET}")
        _print(
            f"{C_GREEN}┃{C_RESET} 👤 {C_BOLD}{C_GREEN}ЭТАП 3/3 · ЛЮДИ И ЛИЦА (Immich){C_RESET}       {C_GREEN}┃{C_RESET}"
        )
        _print(f"{C_GREEN}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{C_RESET}")
        _print(
            f" {C_BOLD}{C_YELLOW}[←] 2. Звуки{C_RESET}   "
            f"{C_BOLD}{C_YELLOW}[→] Заключение{C_RESET}   "
            f"{C_DIM}[1·2·3·4]{C_RESET}"
        )
        _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
        _print(f"🔍 {C_WHITE}Посмотрите в камеру для узнавания лица...{C_RESET}\r\n")

    elif stage == "finale":
        _print(f"{C_YELLOW}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓{C_RESET}")
        _print(
            f"{C_YELLOW}┃{C_RESET} ✨ {C_BOLD}{C_YELLOW}ЗАКЛЮЧЕНИЕ · ПРИВАТНОСТЬ ДОМА{C_RESET}         {C_YELLOW}┃{C_RESET}"
        )
        _print(f"{C_YELLOW}┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{C_RESET}")
        _print(
            f" {C_BOLD}{C_YELLOW}[←] 3. Лица{C_RESET}   "
            f"{C_DIM}[1·2·3] назад   [R] Старт{C_RESET}   "
            f"{C_BOLD}{C_GREEN}[Q] Закрыть{C_RESET}"
        )
        _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
        _print(f"🏠 {C_WHITE}Всё считается дома — видео не уходит в облако{C_RESET}")
        _print(
            f"💡 {C_DIM}GPU снова на паузе. Можно вернуться к этапам или завершить.{C_RESET}\r\n"
        )


def _await_continue(fd: int, next_stage: str) -> str:
    """Пауза между этапами: ждёт Enter/Пробел. Возвращает 'ok' | 'cancel' | 'quit'."""
    title = STAGE_TITLES.get(next_stage, next_stage)
    _clear()
    _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
    _print(f"  ▸  {C_BOLD}{C_WHITE}{title}{C_RESET}")
    _print(f"{C_DIM}──────────────────────────────────────────────{C_RESET}")
    _print("")
    _print(
        f"   {C_BG_CYAN}{C_BOLD} Enter {C_RESET}  {C_WHITE}продолжить{C_RESET}"
        f"   {C_DIM}·  Esc — отмена{C_RESET}"
    )
    _print("")

    while True:
        key = _read_key(fd)
        if key is None:
            continue
        if key in ("right", "n", "d"):  # Enter / Space / → тоже ок
            return "ok"
        if key in ("esc", "left", "b", "a"):
            return "cancel"
        if key == "q":
            return "quit"


def _read_key(fd: int) -> str | None:
    """Читает нажатие клавиши (включая стрелки ← / →)."""
    r, _, _ = select.select([fd], [], [], 0.08)
    if not r:
        return None
    ch = os.read(fd, 1)
    if not ch:
        return "q"
    if ch == b"\x03":  # Ctrl+C
        return "q"
    if ch == b"\x1b":
        # Escape sequence (стрелки)
        r2, _, _ = select.select([fd], [], [], 0.03)
        if r2:
            seq = os.read(fd, 2)
            if seq == b"[C":
                return "right"
            if seq == b"[D":
                return "left"
            if seq == b"[A":
                return "left"
            if seq == b"[B":
                return "right"
        return "esc"
    if ch in (b"\r", b"\n", b" "):
        return "right"
    if ch in (b"\x7f", b"\x08"):
        return "left"
    try:
        return ch.decode("utf-8", errors="ignore").lower()
    except Exception:
        return None


def main() -> None:
    if not sys.stdin.isatty():
        print("Запустите интерактивно: docker exec -it home-sentinel python3 demo.py")
        sys.exit(1)

    state = get_demo_state()
    faces_count = int(state.get("faces_count") or 85)

    # Переводим в idle и открываем хвост файла событий
    set_demo_stage("idle")
    idx = 0

    try:
        with open(EVENTS_PATH, "a+", encoding="utf-8") as ef:
            ef.seek(0, os.SEEK_END)
            fd = sys.stdin.fileno()
            old_term = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                play_boot_sequence(faces_count, animate=True)

                while True:
                    key = _read_key(fd)
                    new_idx = idx

                    if key == "q":
                        break
                    elif key == "right" or key == "n" or key == "d":
                        if idx < len(STAGES) - 1:
                            new_idx = idx + 1
                    elif key == "left" or key == "b" or key == "a":
                        if idx > 0:
                            new_idx = idx - 1
                    elif key == "1":
                        new_idx = 1
                    elif key == "2":
                        new_idx = 2
                    elif key == "3":
                        new_idx = 3
                    elif key == "4":
                        new_idx = 4
                    elif key in ("0", "r", "p"):
                        new_idx = 0
                    elif key == "c":
                        if STAGES[idx] == "idle":
                            play_boot_sequence(faces_count, animate=False)
                        else:
                            render_stage_header(STAGES[idx])

                    if new_idx != idx:
                        decision = _await_continue(fd, STAGES[new_idx])
                        if decision == "quit":
                            break
                        if decision == "cancel":
                            # Вернуть шапку текущего этапа без смены
                            if STAGES[idx] == "idle":
                                play_boot_sequence(faces_count, animate=False)
                            else:
                                render_stage_header(STAGES[idx])
                            continue
                        idx = new_idx
                        stage = STAGES[idx]
                        set_demo_stage(stage)
                        # Пропускаем старые события при смене этапа
                        ef.seek(0, os.SEEK_END)
                        if stage == "idle":
                            play_boot_sequence(faces_count, animate=False)
                        else:
                            render_stage_header(stage)

                    # Читаем новые события: этап совпал, либо глобальный алерт (* / warn / error)
                    while True:
                        line = ef.readline()
                        if not line:
                            break
                        try:
                            ev = json.loads(line)
                            text = ev.get("text")
                            if not text:
                                continue
                            ev_stage = ev.get("stage")
                            kind = ev.get("kind") or "info"
                            show = (
                                ev_stage == STAGES[idx]
                                or ev_stage == "*"
                                or kind in ("warn", "error")
                            )
                            if show:
                                _print(text)
                        except Exception:
                            pass
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
    finally:
        # При выходе возвращаем в idle (если DEMO_MODE) или normal
        fallback = "idle" if config.DEMO_MODE else "normal"
        set_demo_stage(fallback)
        print(f"\n{C_CYAN}👋 Демо-консоль закрыта (режим: {fallback}){C_RESET}")


if __name__ == "__main__":
    main()
