# Фоны выступления «Страж дома»

В git **не хранятся** картинки и GIF (~150 MB). Их нужно положить локально или на asus-note в `~/Pictures/wallpapers/`.

## Google Drive

1. Скачай архив с фонами из Google Drive (ссылку добавь сюда после загрузки):
   - **TODO:** `https://drive.google.com/...`
2. Распакуй содержимое в эту папку `wallpapers/` (или сразу в `~/Pictures/wallpapers` на ноутбуке).

## Ожидаемые файлы

Каталог `out/` (используют `run_wallpapers.sh` и `wallpaper-daemon.py`):

| Файл | Назначение |
|------|------------|
| `bg_00_title.jpg` | Титул |
| `bg_01_hardware.gif` / `.jpg` | Железо |
| `bg_02_smart_home.gif` / `.jpg` | Умный дом (слайд 3) |
| `bg_03_results_final.gif` / `.jpg` | Финал |

Дополнительно для **пересборки** слайдов:

- `strazh_wallpaper_base.jpg` — база для `build_slides.py` / `build_gif_slide2.py`
- Исходные фото — в `~/Downloads` (имена в `build_slides.py`, переменная `SLIDES_SRC`)

## Деплой на asus-note

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' \
  wallpapers/ a.zhizhin@192.168.34.59:~/Pictures/wallpapers/
cp scripts/wallpaper-daemon.py a.zhizhin@192.168.34.59:~/.local/bin/
cp scripts/switch-wallpaper a.zhizhin@192.168.34.59:~/.local/bin/
```

## Сборка из исходников

```bash
cd wallpapers
python3 -m venv .venv && .venv/bin/pip install pillow imageio
.venv/bin/python build_slides.py
.venv/bin/python build_gif_slide2.py
```
