#!/usr/bin/env python3
"""
wallpaper-daemon.py — Живые обои LXQt/Openbox (PyQt5).

Слой: выше pcmanfm-desktop, ниже lxqt-panel.
Иначе либо не видно смены, либо панель ловит клики со второго раза.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QTimer
from PyQt5.QtGui import QMovie, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel

WALL_DIR = Path("/home/a.zhizhin/Pictures/wallpapers")
STATE_FILE = Path("/tmp/maka_wallpaper_idx")
PID_FILE = Path("/tmp/maka_wallpaper_daemon.pid")

SLIDE_BASES = [
    "bg_00_title",
    "bg_01_hardware",
    "bg_02_smart_home",
    "bg_03_results_final",
]


def resolve_slide_path(idx: int) -> Path:
    idx = idx % len(SLIDE_BASES)
    base = SLIDE_BASES[idx]
    for ext in (".gif", ".jpg", ".png"):
        cand = WALL_DIR / f"{base}{ext}"
        if cand.exists():
            return cand
    return WALL_DIR / f"{base}.jpg"


def _warm_page_cache() -> None:
    for i in range(len(SLIDE_BASES)):
        path = resolve_slide_path(i)
        try:
            with open(path, "rb") as fh:
                while fh.read(4 * 1024 * 1024):
                    pass
        except Exception:
            pass


def _xdotool_ids(klass: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["xdotool", "search", "--class", klass],
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [x for x in out.decode().split() if x]


def restack() -> None:
    """wallpaper над рабочим столом, панель над wallpaper."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    try:
        for wid in _xdotool_ids("wallpaper-daemon.py"):
            subprocess.call(
                ["wmctrl", "-i", "-r", wid, "-b", "remove,below"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
            subprocess.call(
                ["xdotool", "windowraise", wid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        for wid in _xdotool_ids("lxqt-panel"):
            subprocess.call(
                ["xdotool", "windowraise", wid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
    except Exception:
        pass


class DesktopWallpaper(QLabel):
    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        super().__init__()
        self.w = width
        self.h = height
        self._current_path: Path | None = None
        self._current_mtime: float = 0.0
        self._active_movie: QMovie | None = None
        self._movies: dict[str, QMovie] = {}
        self._pixmaps: dict[str, QPixmap] = {}

        self.setWindowTitle("maka-wallpaper")
        self.setAttribute(Qt.WA_X11NetWmWindowTypeDesktop, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setGeometry(0, 0, self.w, self.h)
        self.setScaledContents(True)
        self.setStyleSheet("background-color: #0D1117;")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_state)
        self._timer.start(40)
        self._restack_timer = QTimer(self)
        self._restack_timer.timeout.connect(restack)
        self._restack_timer.start(1500)
        self.check_state()
        QTimer.singleShot(200, restack)

        threading.Thread(target=_warm_page_cache, daemon=True).start()

    def read_idx(self) -> int:
        try:
            raw = STATE_FILE.read_text().strip()
            return int(raw) if raw.isdigit() else 0
        except Exception:
            return 0

    def _mtime(self, path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0

    def check_state(self) -> None:
        target = resolve_slide_path(self.read_idx())
        mtime = self._mtime(target)
        if target == self._current_path and mtime == self._current_mtime:
            if (
                self._active_movie is not None
                and self._active_movie.state() != QMovie.Running
            ):
                self._active_movie.start()
                self._active_movie.setPaused(False)
            return
        self.show_slide(target)

    def _gif(self, path: Path) -> QMovie:
        key = str(path)
        movie = self._movies.get(key)
        if movie is None:
            movie = QMovie(key)
            movie.setCacheMode(QMovie.CacheNone)
            movie.setScaledSize(QSize(self.w, self.h))
            self._movies[key] = movie
        return movie

    def show_slide(self, path: Path) -> None:
        if not path.exists():
            return

        old = self._active_movie

        if path.suffix.lower() == ".gif":
            movie = self._gif(path)
            self.setPixmap(QPixmap())
            self.setMovie(movie)
            movie.start()
            movie.setPaused(False)
            if old is not None and old is not movie:
                old.stop()
            self._active_movie = movie
        else:
            key = str(path)
            pix = self._pixmaps.get(key)
            if pix is None:
                raw = QPixmap(key)
                if raw.isNull():
                    return
                pix = raw.scaled(
                    self.w,
                    self.h,
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation,
                )
                self._pixmaps[key] = pix
            self.setMovie(None)
            self.setPixmap(pix)
            if old is not None:
                old.stop()
            self._active_movie = None

        self._current_path = path
        self._current_mtime = self._mtime(path)
        restack()


def main() -> None:
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass

    app = QApplication(sys.argv)
    screen = app.primaryScreen()
    size = screen.size() if screen else QSize(1920, 1080)
    w = DesktopWallpaper(size.width(), size.height())
    w.show()
    restack()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
