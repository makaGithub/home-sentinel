#!/usr/bin/env python3
"""
Сборка анимированного Слайда №2 (bg_01_hardware.gif, 1920x1080)
из 3 видео в ~/Downloads/слайды (video1, video2, video3)
поверх фона 1-го слайда (strazh_wallpaper_base.jpg).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1920, 1080
FPS = 10
DURATION_SEC = 6.0
TOTAL_FRAMES = int(FPS * DURATION_SEC)  # 60 кадров

ROOT = Path(__file__).resolve().parent
VID_DIR = Path.home() / "Downloads" / "слайды"
OUT_DIR = ROOT / "out"

ACCENT_CYAN = (0, 240, 255)
ACCENT_GREEN = (46, 213, 115)
ACCENT_ORANGE = (255, 159, 67)
CARD_BG = (10, 18, 28)
TEXT_WHITE = (240, 246, 252)
TEXT_MUTED = (175, 195, 210)


def get_font(size: int, bold: bool = False):
    paths = [
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def extract_video_frames(video_path: Path, count: int, target_size: tuple[int, int]) -> list[Image.Image]:
    """Извлекает count кадров из видео с помощью ffmpeg и приводит к target_size."""
    tw, th = target_size
    with tempfile.TemporaryDirectory() as tmpdir:
        pattern = os.path.join(tmpdir, "f_%03d.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-stream_loop",
            "-1",
            "-i",
            str(video_path),
            "-vf",
            f"fps={FPS},scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}",
            "-frames:v",
            str(count),
            "-q:v",
            "2",
            pattern,
        ]
        subprocess.run(cmd, check=True)
        files = sorted(Path(tmpdir).glob("f_*.jpg"))
        frames = [Image.open(f).convert("RGBA") for f in files]
    if not frames:
        raise RuntimeError(f"Не удалось извлечь кадры из {video_path}")
    while len(frames) < count:
        frames.append(frames[-1].copy())
    return frames[:count]


def build_base_Overlay() -> tuple[Image.Image, list[tuple[int, int, int, int, tuple[int, int, int]]]]:
    """
    Создаёт базовую подложку 1920x1080 на основе фона 1-го слайда (strazh_wallpaper_base.jpg)
    с шапкой, подписями карточками и бейджем автора.
    Возвращает (базовое изображение, список боксов для вставки видео).
    """
    base_path = ROOT / "strazh_wallpaper_base.jpg"
    bg = Image.open(base_path).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)

    # Слегка приглушаем и тонируем центральную часть фона, чтобы карточки и неоновые края 1-го слайда смотрелись цельно
    bg_dark = ImageEnhance.Brightness(bg).enhance(0.55)
    canvas = bg_dark.convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Верхняя шапка-плашка в стиле 1-го слайда
    draw.rounded_rectangle(
        [56, 28, 1864, 142],
        radius=18,
        fill=(6, 16, 26, 225),
        outline=(0, 240, 200, 200),
        width=2,
    )
    draw.text(
        (88, 42),
        "СТРАЖ ДОМА · ЖЕЛЕЗО СВОИМИ РУКАМИ",
        fill=ACCENT_CYAN,
        font=get_font(38, True),
    )
    draw.text(
        (88, 92),
        "Собран из доступных компонентов с Авито — без облаков и абонентской платы",
        fill=TEXT_MUTED,
        font=get_font(23, False),
    )

    # Плашка с бюджетом справа вверху
    draw.rounded_rectangle(
        [1420, 44, 1836, 126],
        radius=14,
        fill=(10, 36, 28, 240),
        outline=ACCENT_GREEN,
        width=3,
    )
    draw.text(
        (1450, 66),
        "БЮДЖЕТ: ~32 474 ₽",
        fill=ACCENT_GREEN,
        font=get_font(32, True),
    )

    # 3 карточки для видео (video1, video2, video3)
    cards_meta = [
        (
            "01 // МИНИ-КОМПЬЮТЕР",
            "Raspberry Pi (go2rtc + VPN)",
            ACCENT_CYAN,
        ),
        (
            "02 // ЗРЕНИЕ И СЛУХ",
            "USB-камера A4Tech 1080p",
            ACCENT_GREEN,
        ),
        (
            "03 // ПОЛНЫЙ КОМПЛЕКТ",
            "Сборка + акустика DEXP",
            ACCENT_ORANGE,
        ),
    ]

    card_w = 560
    card_h = 770
    gap = 64
    start_x = (W - (card_w * 3 + gap * 2)) // 2  # 56
    card_y = 166

    video_boxes = []
    for i, (tag, title, color) in enumerate(cards_meta):
        cx = start_x + i * (card_w + gap)
        # Подложка карточки
        draw.rounded_rectangle(
            [cx, card_y, cx + card_w, card_y + card_h],
            radius=22,
            fill=(8, 18, 30, 230),
            outline=color,
            width=3,
        )
        # Шапка карточки
        draw.rounded_rectangle(
            [cx + 18, card_y + 16, cx + card_w - 18, card_y + 56],
            radius=10,
            fill=(color[0], color[1], color[2], 38),
        )
        draw.text((cx + 32, card_y + 24), tag, fill=color, font=get_font(20, True))
        draw.text(
            (cx + 28, card_y + 68),
            title,
            fill=TEXT_WHITE,
            font=get_font(26, True),
        )

        # Область под видео внутри карточки
        vx = cx + 20
        vy = card_y + 112
        vw = card_w - 40  # 520
        vh = card_h - 132  # 638
        video_boxes.append((vx, vy, vw, vh, color))

    # Нижняя строка + бейдж автора справа внизу (как на 1-м слайде)
    draw.rounded_rectangle(
        [56, 964, 1390, 1036],
        radius=14,
        fill=(6, 16, 26, 220),
        outline=(0, 240, 200, 150),
        width=2,
    )
    draw.text(
        (82, 986),
        "▸ Raspberry Pi (go2rtc + VPN)     ▸ Камера A4Tech 1080p     ▸ Акустика DEXP     ▸ Домашний ПК с GPU",
        fill=TEXT_WHITE,
        font=get_font(22, True),
    )

    sig_text = "Жижин Максим, лицей 185"
    sig_font = get_font(28, True)
    bbox = draw.textbbox((0, 0), sig_text, font=sig_font)
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
    draw.text((bx + pad_x, by + pad_y - 3), sig_text, font=sig_font, fill=(225, 250, 245))

    return canvas, video_boxes


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_canvas, video_boxes = build_base_Overlay()

    v1_path = VID_DIR / "video1"
    v2_path = VID_DIR / "video2"
    v3_path = VID_DIR / "video3"

    vw, vh = video_boxes[0][2], video_boxes[0][3]
    print(f"Извлекаем по {TOTAL_FRAMES} кадров ({vw}x{vh}) из video1, video2, video3...")
    frames_v1 = extract_video_frames(v1_path, TOTAL_FRAMES, (vw, vh))
    frames_v2 = extract_video_frames(v2_path, TOTAL_FRAMES, (vw, vh))
    frames_v3 = extract_video_frames(v3_path, TOTAL_FRAMES, (vw, vh))

    # Скруглённая маска для видео-окон
    mask = Image.new("L", (vw, vh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, vw, vh], radius=16, fill=255)

    with tempfile.TemporaryDirectory() as tmpdir:
        print("Собираем кадры композиции 1920x1080...")
        for idx in range(TOTAL_FRAMES):
            frame_img = base_canvas.copy()
            f_draw = ImageDraw.Draw(frame_img, "RGBA")
            for v_frames, (vx, vy, bw, bh, color) in zip(
                (frames_v1, frames_v2, frames_v3), video_boxes
            ):
                frame_img.paste(v_frames[idx], (vx, vy), mask)
                f_draw.rounded_rectangle(
                    [vx, vy, vx + bw, vy + bh],
                    radius=16,
                    outline=color,
                    width=2,
                )

            out_frame = os.path.join(tmpdir, f"slide_{idx:03d}.jpg")
            frame_img.convert("RGB").save(out_frame, quality=92)
            if idx == 0:
                # Сохраним и статичный JPG-дубль для превью/фолбэка
                frame_img.convert("RGB").save(OUT_DIR / "bg_01_hardware.jpg", quality=95)

        out_gif = OUT_DIR / "bg_01_hardware.gif"
        print("Генерируем высококачественный GIF через ffmpeg palettegen/paletteuse...")
        palette = os.path.join(tmpdir, "palette.png")
        in_pattern = os.path.join(tmpdir, "slide_%03d.jpg")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                in_pattern,
                "-vf",
                "palettegen=stats_mode=diff",
                palette,
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                in_pattern,
                "-i",
                palette,
                "-lavfi",
                f"fps={FPS} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                "-loop",
                "0",
                str(out_gif),
            ],
            check=True,
        )

    size_mb = out_gif.stat().st_size / (1024 * 1024)
    print(f"✅ Готово: {out_gif} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
