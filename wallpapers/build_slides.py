#!/usr/bin/env python3
"""Сборка 3 фонов выступления «Страж дома» (1920×1080) из фото в ~/Downloads."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

# Настройки разрешения Full HD
W, H = 1920, 1080
BG_COLOR = (13, 17, 23)  # Тёмный графит (#0D1117)
CARD_BG = (22, 27, 34)  # Фон карточек (#161B22)
ACCENT_CYAN = (0, 240, 255)  # Неоновый голубой
ACCENT_GREEN = (46, 213, 115)  # Неоновый зелёный
ACCENT_ORANGE = (255, 159, 67)  # Оранжевый акцент
TEXT_WHITE = (240, 246, 252)
TEXT_MUTED = (139, 148, 158)

ROOT = Path(__file__).resolve().parent
SRC_DIR = Path(os.environ.get("SLIDES_SRC", Path.home() / "Downloads"))
OUT_DIR = Path(os.environ.get("SLIDES_OUT", ROOT / "out"))

# Имена исходных файлов
FILE_NAMES = {
    "dark_spk": "2026-10-23 01.32.21.jpg",
    "dog": "2026-10-23 01.32.16.jpg",
    "lit_spk": "2026-10-23 01.32.11.jpg",
    "immich": "2026-10-23 01.32.07.jpg",
    "webcam": "2026-10-23 01.32.03.jpg",
    "shelf": "2026-10-23 01.31.58.jpg",
    "tg": "2026-10-23 01.31.53.jpg",
    "rpi": "2026-10-23 01.31.49.jpg",
    "hands": "2026-10-23 01.31.43.jpg",
}

FILES = {k: str(SRC_DIR / v) for k, v in FILE_NAMES.items()}


def get_font(size, bold=False):
    font_paths = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
        (
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/TTF/DejaVuSans.ttf"
        ),
        (
            "C:/Windows/Fonts/arialbd.ttf"
            if bold
            else "C:/Windows/Fonts/arial.ttf"
        ),
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        (
            "/Library/Fonts/Arial Bold.ttf"
            if bold
            else "/Library/Fonts/Arial.ttf"
        ),
        (
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
        ),
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def paste_rounded_image(
    canvas,
    img_path,
    box,
    radius=20,
    border_color=None,
    border_width=3,
    contain=False,
):
    x, y, w, h = box
    if not os.path.exists(img_path):
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=radius,
            fill=CARD_BG,
            outline=border_color or TEXT_MUTED,
            width=2,
        )
        draw.text(
            (x + 20, y + h // 2),
            f"Файл не найден:\n{img_path}",
            fill=TEXT_WHITE,
            font=get_font(20),
        )
        return

    img = Image.open(img_path).convert("RGBA")
    if contain:
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        bg = Image.new("RGBA", (w, h), CARD_BG + (255,))
        bg.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
        img = bg
    else:
        img = ImageOps.fit(img, (w, h), Image.Resampling.LANCZOS)

    mask = Image.new("L", (w, h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, w, h], radius=radius, fill=255)

    canvas.paste(img, (x, y), mask)

    if border_color:
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            radius=radius,
            outline=border_color,
            width=border_width,
        )


def build_slide_0():
    """Фон 0: Титульный арт «Страж дома» + подпись автора."""
    base_path = ROOT / "strazh_wallpaper_base.jpg"
    if base_path.exists():
        canvas = (
            Image.open(base_path)
            .convert("RGB")
            .resize((W, H), Image.Resampling.LANCZOS)
        )
    else:
        canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas, "RGBA")

    text = "Жижин Максим, лицей 185"
    font = get_font(28, True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    pad_x, pad_y = 28, 16
    bw = tw + pad_x * 2
    bh = th + pad_y * 2
    bx = W - bw - 56
    by = H - bh - 44

    draw.rounded_rectangle(
        [bx, by, bx + bw, by + bh],
        radius=14,
        fill=(6, 16, 26, 220),
        outline=(0, 240, 200, 210),
        width=2,
    )
    draw.text((bx + pad_x, by + pad_y - 3), text, font=font, fill=(225, 250, 245))

    out = OUT_DIR / "bg_00_title.jpg"
    canvas.save(out, quality=95)
    return out


def build_slide_1():
    """Фон 1: Железо своими руками (0:00 - 0:45)"""
    canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Шапка
    draw.text(
        (70, 45),
        "СТРАЖ ДОМА · ЛОКАЛЬНЫЙ ИИ СВОИМИ РУКАМИ",
        fill=ACCENT_CYAN,
        font=get_font(40, True),
    )
    draw.text(
        (70, 100),
        "Собран из доступных компонентов с Авито — без облаков и абонентской платы",
        fill=TEXT_MUTED,
        font=get_font(24),
    )

    # Плашка с ценой справа вверху
    draw.rounded_rectangle(
        [1400, 40, 1850, 125],
        radius=16,
        fill=CARD_BG,
        outline=ACCENT_GREEN,
        width=3,
    )
    draw.text(
        (1435, 62),
        "БЮДЖЕТ: ~32 474 ₽",
        fill=ACCENT_GREEN,
        font=get_font(34, True),
    )

    # Крупно слева: полка в интерьере и колонки с подсветкой
    paste_rounded_image(
        canvas, FILES["shelf"], (70, 160, 540, 780), border_color=ACCENT_CYAN
    )
    paste_rounded_image(
        canvas, FILES["lit_spk"], (640, 160, 540, 780), border_color=ACCENT_GREEN
    )

    # 3 карточки справа: Raspberry Pi, Камера, Сборка руками
    paste_rounded_image(
        canvas, FILES["rpi"], (1210, 160, 640, 240), border_color=TEXT_MUTED
    )
    paste_rounded_image(
        canvas, FILES["webcam"], (1210, 430, 640, 240), border_color=TEXT_MUTED
    )
    paste_rounded_image(
        canvas, FILES["hands"], (1210, 700, 640, 240), border_color=TEXT_MUTED
    )

    # Подписи внизу
    draw.text(
        (70, 965),
        "📦 Raspberry Pi (c go2rtc)   |   📷 Камера A4Tech 1080p   |   "
        "🔊 Акустика DEXP   |   🖥 Домашний ПК с GPU",
        fill=TEXT_WHITE,
        font=get_font(24, True),
    )
    out = OUT_DIR / "bg_01_hardware.jpg"
    canvas.save(out, quality=95)
    return out


def build_slide_2():
    """Фон 2: Архитектура и VPN (0:45 - 2:28)"""
    canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.text(
        (70, 50),
        "АРХИТЕКТУРА СИСТЕМЫ · РАБОТА ЧЕРЕЗ ЗАЩИЩЁННЫЙ VPN",
        fill=ACCENT_CYAN,
        font=get_font(38, True),
    )
    draw.text(
        (70, 105),
        "Тяжёлые нейросети работают на домашней видеокарте, "
        "а на входе — компактный микрокомпьютер",
        fill=TEXT_MUTED,
        font=get_font(24),
    )

    # Слева — атмосферное фото в темноте
    paste_rounded_image(
        canvas, FILES["dark_spk"], (70, 170, 620, 840), border_color=ACCENT_GREEN
    )

    # Справа — 3 блока схемы
    blocks = [
        (
            "1. ЗАХВАТ В КОМНАТЕ (Raspberry Pi)",
            "Камера A4Tech + микрофон передают RTSP-поток через лёгкий сервер go2rtc",
            ACCENT_CYAN,
            170,
        ),
        (
            "2. ЗАЩИЩЁННЫЙ ТУННЕЛЬ (WireGuard VPN)",
            "Поток зашифрован: данные лежат только внутри домашней сети "
            "без сторонних серверов",
            ACCENT_ORANGE,
            460,
        ),
        (
            "3. ДОМАШНИЙ СЕРВЕР С GPU (3 НЕЙРОСЕТИ)",
            "• YOLOv8 — детекция объектов в кадре\n"
            "• YAMNet — классификация 521 типа звуков\n"
            "• InsightFace — распознавание лиц по базе Immich (2 ТБ)",
            ACCENT_GREEN,
            730,
        ),
    ]
    for title, desc, color, y in blocks:
        h = 280 if y == 730 else 220
        draw.rounded_rectangle(
            [740, y, 1850, y + h], radius=20, fill=CARD_BG, outline=color, width=3
        )
        draw.text((780, y + 30), title, fill=color, font=get_font(30, True))
        draw.text((780, y + 85), desc, fill=TEXT_WHITE, font=get_font(24))

    out = OUT_DIR / "bg_02_architecture.jpg"
    canvas.save(out, quality=95)
    return out


def build_slide_3():
    """Фон 3: Итоги, Собака + Телеграм, Immich и Приватность (2:28 - Конец + Вопросы)"""
    canvas = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    draw.text(
        (70, 40),
        "РЕАЛЬНАЯ РАБОТА ДОМА · 100% ЛОКАЛЬНАЯ ПРИВАТНОСТЬ",
        fill=ACCENT_GREEN,
        font=get_font(38, True),
    )
    draw.text(
        (70, 95),
        "Мультимодальность: зрение + слух + личный фотоархив семьи "
        "на 2 ТБ без утечек в облако",
        fill=TEXT_MUTED,
        font=get_font(24),
    )

    # Колонка 1: База лиц Immich
    draw.text(
        (70, 150),
        "1. БАЗА ЛИЦ СЕМЬИ (IMMICH · 638 ЛЮДЕЙ)",
        fill=ACCENT_CYAN,
        font=get_font(22, True),
    )
    paste_rounded_image(
        canvas,
        FILES["immich"],
        (70, 190, 680, 430),
        border_color=ACCENT_CYAN,
        contain=True,
    )
    paste_rounded_image(
        canvas, FILES["dark_spk"], (70, 650, 680, 360), border_color=TEXT_MUTED
    )

    # Колонка 2: Собака + Телеграм
    draw.text(
        (780, 150),
        "2. ДЕТЕКЦИЯ СОБЫТИЙ И СВЯЗЬ С УМНЫМ ДОМОМ",
        fill=ACCENT_ORANGE,
        font=get_font(22, True),
    )
    paste_rounded_image(
        canvas, FILES["dog"], (780, 190, 520, 620), border_color=ACCENT_ORANGE
    )
    paste_rounded_image(
        canvas,
        FILES["tg"],
        (780, 835, 520, 175),
        border_color=ACCENT_ORANGE,
        contain=True,
    )

    # Колонка 3: Выводы для жюри (на время вопросов)
    draw.rounded_rectangle(
        [1330, 190, 1850, 1010],
        radius=20,
        fill=CARD_BG,
        outline=ACCENT_GREEN,
        width=3,
    )
    draw.text(
        (1365, 230),
        "ПОЧЕМУ ЭТО ВАЖНО?",
        fill=ACCENT_GREEN,
        font=get_font(30, True),
    )

    points = [
        (
            "❌ Угроза облачных камер",
            "В 2024 году из-за сбоя облака Wyze\n"
            "видео из квартир 13 000 семей\n"
            "оказались в открытом доступе.",
        ),
        (
            "✅ Полная автономность",
            "«Страж дома» не отправляет видео\n"
            "и звук на чужие серверы.\n"
            "Все вычисления идут дома.",
        ),
        (
            "🧠 Три ИИ в одной связке",
            "• YOLO видит человека или питомца\n"
            "• YAMNet слышит лай, стук, стекло\n"
            "• InsightFace узнаёт своих (95%+)",
        ),
        (
            "💰 Доступность каждому",
            "Собрано школьником из б/у железа\n"
            "по цене одного бюджетного смартфона.",
        ),
    ]
    y_offset = 310
    for title, body in points:
        draw.text((1365, y_offset), title, fill=TEXT_WHITE, font=get_font(24, True))
        draw.text(
            (1365, y_offset + 38), body, fill=TEXT_MUTED, font=get_font(20)
        )
        y_offset += 170

    out = OUT_DIR / "bg_03_results_final.jpg"
    canvas.save(out, quality=95)
    return out


def main() -> None:
    missing = [p for p in FILES.values() if not os.path.exists(p)]
    if missing:
        raise SystemExit(
            "Нет исходных фото:\n  " + "\n  ".join(missing) + f"\nSRC_DIR={SRC_DIR}"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = [build_slide_0(), build_slide_1(), build_slide_2(), build_slide_3()]

    # Совместимые имена для switch-wallpaper / старых ярлыков
    aliases = {
        "bg_01_hardware.jpg": "01_start_hardware.jpg",
        "bg_02_architecture.jpg": "02_live_demo.jpg",
        "bg_03_results_final.jpg": "03_finale_privacy.jpg",
    }
    for src_name, alias in aliases.items():
        src = OUT_DIR / src_name
        dst = OUT_DIR / alias
        if src.exists():
            dst.write_bytes(src.read_bytes())

    print("✅ Все 4 слайда (1920x1080) успешно созданы:")
    for p in paths:
        print(f"   {p}  ({p.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
