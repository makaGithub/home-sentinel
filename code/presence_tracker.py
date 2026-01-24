# presence_tracker.py
"""
Трекер присутствия: определяет события "пришёл домой" / "ушёл из дома".

Логика:
- Звук двери → Лицо (в течение N секунд) = ПРИШЁЛ
- Лицо → Звук двери (в течение N секунд) = УШЁЛ

Отправляет события:
- person_arrived (человек пришёл)
- person_left (человек ушёл)
"""

import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable

import config
from utils import log


def _get_screenshot_url(filename: str) -> str:
    """Формирует URL скриншота для Home Assistant."""
    if config.SCREENSHOTS_WEB_URL:
        base_url = config.SCREENSHOTS_WEB_URL.rstrip("/")
        return f"{base_url}/screenshots/{filename}"
    # Если URL не задан, возвращаем локальный путь
    return os.path.join(config.SCREENSHOTS_DIR, filename)


@dataclass
class Event:
    """Событие с временной меткой."""
    timestamp: float
    name: Optional[str] = None  # Имя человека (для face events)
    sound: Optional[str] = None  # Тип звука (для door events)
    screenshot_path: Optional[str] = None  # Путь к скриншоту


# Тип для callback функций
PresenceCallback = Callable[[str, Optional[str]], None]  # (name, screenshot_path) -> None


class PresenceTracker:
    """Трекер присутствия на основе последовательности событий."""
    
    def __init__(self):
        self._lock = threading.Lock()
        
        # Последние события
        self._last_door_event: Optional[Event] = None
        self._last_face_events: dict[str, Event] = {}  # {name: Event}
        
        # Временное окно для корреляции событий (секунды)
        self.time_window = config.PRESENCE_TIME_WINDOW
        
        # Звуки, которые считаются "дверью"
        self.door_sounds = config.DOOR_SOUNDS
        
        # Callback для отправки событий
        self._on_arrived: Optional[PresenceCallback] = None
        self._on_left: Optional[PresenceCallback] = None
        
        log(f"🚪 Трекер присутствия: окно {self.time_window}с, звуки двери: {', '.join(self.door_sounds)}")
    
    def set_callbacks(self, on_arrived: PresenceCallback, on_left: PresenceCallback):
        """Устанавливает callbacks для событий прихода/ухода."""
        self._on_arrived = on_arrived
        self._on_left = on_left
    
    def on_door_sound(self, sound: str):
        """Вызывается при обнаружении звука двери."""
        if sound.lower() not in self.door_sounds:
            return
        
        now = time.time()
        
        with self._lock:
            # Проверяем: было ли лицо недавно? → УШЁЛ
            for name, face_event in list(self._last_face_events.items()):
                if (now - face_event.timestamp) <= self.time_window:
                    # Лицо было недавно, потом дверь → человек ушёл
                    self._emit_left(name, face_event.screenshot_path)
                    del self._last_face_events[name]
                    return
            
            # Иначе запоминаем событие двери
            self._last_door_event = Event(timestamp=now, sound=sound)
    
    def on_face_recognized(self, name: str, screenshot_path: Optional[str] = None):
        """Вызывается при распознавании лица."""
        now = time.time()
        
        with self._lock:
            # Проверяем: была ли дверь недавно? → ПРИШЁЛ
            if self._last_door_event:
                if (now - self._last_door_event.timestamp) <= self.time_window:
                    # Дверь была недавно, потом лицо → человек пришёл
                    self._emit_arrived(name, screenshot_path)
                    self._last_door_event = None
                    return
            
            # Иначе запоминаем событие лица
            self._last_face_events[name] = Event(
                timestamp=now, 
                name=name,
                screenshot_path=screenshot_path
            )
    
    def _emit_arrived(self, name: str, screenshot_path: Optional[str] = None):
        """Генерирует событие 'пришёл домой'."""
        log(f"🏠 {name} пришёл домой")
        # Формируем URL скриншота если он есть
        screenshot_url = self._get_screenshot_url_from_path(screenshot_path)
        if self._on_arrived:
            self._on_arrived(name, screenshot_url)
    
    def _emit_left(self, name: str, screenshot_path: Optional[str] = None):
        """Генерирует событие 'ушёл из дома'."""
        log(f"👋 {name} ушёл из дома")
        # Формируем URL скриншота если он есть
        screenshot_url = self._get_screenshot_url_from_path(screenshot_path)
        if self._on_left:
            self._on_left(name, screenshot_url)
    
    def _get_screenshot_url_from_path(self, screenshot_path: Optional[str]) -> Optional[str]:
        """Формирует URL скриншота из локального пути."""
        if not screenshot_path:
            return None
        
        # Извлекаем имя файла из пути
        filename = os.path.basename(screenshot_path)
        return _get_screenshot_url(filename)
    
    def cleanup_stale(self):
        """Очищает устаревшие события (вызывать периодически)."""
        now = time.time()
        stale_threshold = self.time_window * 2
        
        with self._lock:
            # Очищаем старые события лиц
            stale_names = [
                name for name, event in self._last_face_events.items()
                if (now - event.timestamp) > stale_threshold
            ]
            for name in stale_names:
                del self._last_face_events[name]
            
            # Очищаем старое событие двери
            if self._last_door_event and (now - self._last_door_event.timestamp) > stale_threshold:
                self._last_door_event = None


# Глобальный экземпляр трекера
_tracker: Optional[PresenceTracker] = None


def init_presence_tracker():
    """Инициализирует трекер присутствия."""
    global _tracker
    
    if not config.PRESENCE_TRACKING_ENABLED:
        return None
    
    _tracker = PresenceTracker()
    return _tracker


def get_tracker() -> Optional[PresenceTracker]:
    """Возвращает глобальный трекер."""
    return _tracker
