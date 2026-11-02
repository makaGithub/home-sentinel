# utils.py
"""
Утилиты: компактное цветное логирование (без даты/времени), перевод классов, директории, предобработка лиц.
"""

import os
import re
import shutil
import unicodedata

import cv2
import numpy as np

import config

# ANSI-палитра для крупного экрана / проектора
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_GREEN = "\033[1;92m"
C_CYAN = "\033[1;96m"
C_YELLOW = "\033[1;93m"
C_MAGENTA = "\033[1;95m"
C_RED = "\033[1;91m"
C_WHITE = "\033[1;97m"
C_GRAY = "\033[38;5;244m"
C_BG_GREEN = "\033[1;97;42m"
C_BG_CYAN = "\033[1;30;46m"
C_BG_MAGENTA = "\033[1;97;45m"
C_BG_YELLOW = "\033[1;30;43m"

# Ширина внутренних рамок демо-консоли (между ┃). Все шапки рисуются одинаково.
BOX_INNER = 44
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def visible_width(text: str) -> int:
    """Колонки терминала: без ANSI, эмодзи = 2, combining/VS = 0."""
    w = 0
    for ch in _ANSI_RE.sub("", text):
        o = ord(ch)
        if unicodedata.combining(ch) or ch in "\u200d\ufe0f\ufe0e\u20e3":
            continue
        ea = unicodedata.east_asian_width(ch)
        if ea in ("F", "W"):
            w += 2
        elif (
            0x1F000 <= o <= 0x1FAFF
            or 0x2600 <= o <= 0x27BF
            or 0x2300 <= o <= 0x23FF
            or 0x2B00 <= o <= 0x2BFF
        ):
            w += 2
        else:
            w += 1
    return w


def pad_visible(text: str, width: int) -> str:
    """Добивает пробелами до width видимых колонок."""
    pad = max(0, width - visible_width(text))
    return text + (" " * pad)


def format_box(title: str, color: str, inner: int = BOX_INNER) -> list[str]:
    """Три строки рамки: верх / заголовок / низ. title может содержать ANSI."""
    inner_text = pad_visible(title, inner)
    return [
        f"{color}┏{'━' * inner}┓{C_RESET}",
        f"{color}┃{C_RESET}{inner_text}{color}┃{C_RESET}",
        f"{color}┗{'━' * inner}┛{C_RESET}",
    ]


def format_rule(inner: int = BOX_INNER) -> str:
    """Горизонтальный разделитель той же ширины, что и рамка."""
    return f"{C_DIM}{'─' * (inner + 2)}{C_RESET}"

OBJECT_RU: dict[str, tuple[str, str]] = {
    "person": ("👤", "Человек"),
    "dog": ("🐕", "Собака"),
    "cat": ("🐱", "Кот"),
    "cell phone": ("📱", "Телефон"),
    "laptop": ("💻", "Ноутбук"),
    "tv": ("📺", "Экран"),
    "cup": ("☕", "Кружка"),
    "bottle": ("🍼", "Бутылка"),
    "book": ("📖", "Книга"),
    "chair": ("🪑", "Стул"),
    "couch": ("🛋️", "Диван"),
    "dining table": ("🍽️", "Стол"),
    "keyboard": ("⌨️", "Клавиатура"),
    "mouse": ("🖱️", "Мышь"),
    "remote": ("🎮", "Пульт"),
    "backpack": ("🎒", "Рюкзак"),
    "handbag": ("👜", "Сумка"),
    "clock": ("🕒", "Часы"),
    "scissors": ("✂️", "Ножницы"),
    "glasses": ("👓", "Очки"),
    "vase": ("🏺", "Ваза"),
    "potted plant": ("🪴", "Цветок"),
    "apple": ("🍎", "Яблоко"),
    "banana": ("🍌", "Банан"),
    "orange": ("🍊", "Апельсин"),
    "bowl": ("🥣", "Миска"),
    "spoon": ("🥄", "Ложка"),
    "fork": ("🍴", "Вилка"),
    "knife": ("🔪", "Нож"),
    "wine glass": ("🍷", "Бокал"),
    "microwave": ("📦", "Микроволновка"),
    "oven": ("📦", "Духовка"),
}

SOUND_RU: dict[str, tuple[str, str]] = {
    "speech": ("🗣", "Речь"),
    "child speech, kid speaking": ("🗣", "Детская речь"),
    "dog": ("🐕", "Собака"),
    "bark": ("🐕", "Лай собаки"),
    "howl": ("🐺", "Вой"),
    "knock": ("🚪", "Стук"),
    "tap": ("🚪", "Стук"),
    "door": ("🚪", "Дверь"),
    "doorbell": ("🔔", "Звонок"),
    "ding-dong": ("🔔", "Звонок"),
    "sliding door": ("🚪", "Дверь"),
    "slam": ("🚪", "Стук"),
    "clapping": ("👏", "Хлопок"),
    "applause": ("👏", "Хлопки"),
    "hands": ("👏", "Хлопок"),
    "finger snapping": ("👏", "Щелчок"),
    "slap, smack": ("👏", "Хлопок"),
    "whistling": ("🎵", "Свист"),
    "whistle": ("🎵", "Свист"),
    "laughter": ("😄", "Смех"),
    "glass": ("💥", "Звон стекла"),
    "shatter": ("💥", "Разбитое стекло"),
    "squeal": ("🔊", "Резкий звук"),
    "music": ("🎸", "Музыка"),
    "musical instrument": ("🎸", "Музыка"),
    "singing": ("🎤", "Музыка"),
    "guitar": ("🎸", "Музыка"),
    "song": ("🎸", "Музыка"),
    "drum": ("🥁", "Музыка"),
    "piano": ("🎹", "Музыка"),
}


def sound_demo_group(sound: str) -> str | None:
    """Группа демо-звука: knock | clap | music | None."""
    n = (sound or "").lower().strip()
    if n in {
        "knock",
        "tap",
        "door",
        "doorbell",
        "ding-dong",
        "slam",
        "sliding door",
    }:
        return "knock"
    if n in {
        "clapping",
        "applause",
        "hands",
        "finger snapping",
        "slap, smack",
    }:
        return "clap"
    if (
        n in {"music", "musical instrument", "singing", "guitar", "song", "drum", "piano"}
        or "music" in n
        or n.endswith(" guitar")
    ):
        return "music"
    return None


def is_demo_priority_sound(sound: str) -> bool:
    """True если звук в демо-приоритете (стук / хлопки / музыка)."""
    n = (sound or "").lower().strip()
    if n in config.DEMO_PRIORITY_SOUNDS:
        return True
    return sound_demo_group(n) is not None


def format_object_short(label: str, confidence: float | None = None) -> str:
    """Короткая яркая подпись объекта для экрана."""
    if label.startswith("person(") and label.endswith(")"):
        name = label[7:-1]
        pct = f" {C_YELLOW}{int(round(confidence * 100))}%{C_RESET}" if confidence else ""
        return f"👤 {C_GREEN}{name}{C_RESET}{pct}"
    emoji, ru_name = OBJECT_RU.get(label.lower(), ("📦", label))
    pct = f" {C_YELLOW}{int(round(confidence * 100))}%{C_RESET}" if confidence else ""
    return f"{emoji} {C_CYAN}{ru_name}{C_RESET}{pct}"


def format_sound_short(sound: str, confidence: float | None = None) -> str:
    """Короткая яркая подпись звука для экрана."""
    emoji, ru_name = SOUND_RU.get(sound.lower(), ("🔊", sound))
    pct = f" {C_YELLOW}{int(round(confidence * 100))}%{C_RESET}" if confidence else ""
    return f"{emoji} {C_MAGENTA}{ru_name}{C_RESET}{pct}"


def log(msg: str):
    """Компактный логгер без даты и времени (для крупного шрифта на экране)."""
    print(msg, flush=True)


def fix_insightface_model_structure():
    """Исправляет вложенную папку antelopev2/antelopev2 при необходимости."""
    model_name = config.INSIGHTFACE_MODEL
    model_path = os.path.join(config.MODEL_DIR, model_name)
    nested_path = os.path.join(model_path, model_name)

    if not os.path.exists(nested_path) or not os.path.isdir(nested_path):
        return

    try:
        correct_files = [f for f in os.listdir(model_path) if f != model_name]
        nested_files = os.listdir(nested_path)

        if correct_files:
            shutil.rmtree(nested_path)
            return

        for item in nested_files:
            src = os.path.join(nested_path, item)
            dst = os.path.join(model_path, item)
            if os.path.exists(dst):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                else:
                    os.remove(dst)
            shutil.move(src, dst)

        try:
            os.rmdir(nested_path)
        except OSError:
            shutil.rmtree(nested_path)
    except Exception as e:
        log(f"⚠️ Ошибка структуры модели: {e}")


def ensure_dirs():
    """Создаёт необходимые директории и настраивает INSIGHTFACE_ROOT."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.MODEL_DIR, exist_ok=True)
    os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)

    insight_root = os.path.dirname(config.MODEL_DIR) or "/app"
    if insight_root.endswith("/models"):
        insight_root = os.path.dirname(insight_root)
    os.environ["INSIGHTFACE_ROOT"] = insight_root

    fix_insightface_model_structure()


def _l2_normalize(v: np.ndarray, eps: float = 1e-9) -> np.ndarray:
    """L2-нормализация вектора/массивов по последней оси."""
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def preprocess_face_crop(crop: np.ndarray) -> np.ndarray:
    """Предобработка изображения лица: CLAHE для улучшения контраста."""
    if crop.size == 0:
        return crop
    try:
        lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return crop


def adaptive_threshold(face_size: int, base_threshold: float) -> float:
    """Адаптивный порог сходства в зависимости от размера лица (в пикселях)."""
    if face_size < 100:
        return max(0.5, base_threshold - 0.03)
    elif face_size > 200:
        return min(0.6, base_threshold + 0.02)
    return base_threshold
