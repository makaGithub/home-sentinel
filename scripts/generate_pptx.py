#!/usr/bin/env python3
"""
Генерация презентации проекта home-sentinel из presentation.md

Использование:
    python3 scripts/generate_pptx.py

Скрипт читает docs/presentation.md и генерирует docs/presentation.pptx

Требования:
    - python-pptx: pip install python-pptx
    - mermaid-cli (для рендеринга Mermaid диаграмм): npm install -g @mermaid-js/mermaid-cli
      Если mermaid-cli не установлен, Mermaid диаграммы будут показаны как текст
"""

import os
import re
import sys
import argparse
import subprocess
import tempfile
import json
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.dml.color import RGBColor
    from pptx.dml.fill import FillFormat
    print("✅ Все необходимые модули импортированы успешно")
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    print("   Установите python-pptx: pip install python-pptx")
    sys.exit(1)

# Импортируем вспомогательный модуль для конфигурации
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from config_helper import (
        load_env_file, get_project_root, generate_output_filename,
        get_build_dir, publish_to_gh_pages, create_github_release
    )
except ImportError as e:
    print(f"⚠️  Предупреждение: не удалось импортировать config_helper: {e}")
    print("   Используются значения по умолчанию")

# Константы форматирования
FONT_NAME = 'Arial'  # Arial лучше работает в презентациях
TITLE_SIZE = 44
SUBTITLE_SIZE = 32
HEADING_SIZE = 28
BODY_SIZE = 20  # Увеличен для лучшей читаемости
CODE_SIZE = 14

# Цвета - обновленная палитра
TITLE_COLOR = RGBColor(15, 82, 186)  # Глубокий синий
TEXT_COLOR = RGBColor(24, 28, 36)  # Темный графит
ACCENT_COLOR = RGBColor(0, 168, 150)  # Бирюзовый акцент
SUBTITLE_COLOR = RGBColor(0, 150, 199)
CODE_BG_COLOR = RGBColor(245, 248, 252)
BULLET_COLOR = ACCENT_COLOR
DIAGRAM_BG_COLOR = RGBColor(255, 255, 255)

# Градиентные цвета для фона
GRADIENT_START = RGBColor(5, 33, 71)
GRADIENT_END = RGBColor(21, 101, 192)

def parse_markdown(md_file):
    """Парсит markdown файл и возвращает список слайдов"""
    with open(md_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Разделяем на слайды по ---
    slides_content = content.split('---')
    
    slides = []
    for slide_content in slides_content:
        slide_content = slide_content.strip()
        if not slide_content:
            continue
        
        lines = slide_content.split('\n')
        slide_data = {
            'title': None,
            'subtitle': None,
            'content': [],
            'is_code': False
        }
        
        current_block = []
        in_code_block = False
        in_mermaid_block = False
        
        for line in lines:
            original_line = line  # Сохраняем оригинальную строку для проверки пустоты
            line = line.strip()
            
            # Пустая строка - сохраняем как отдельный элемент контента
            if not line:
                if current_block and not in_mermaid_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                # Добавляем пустую строку как отдельный элемент
                if not in_mermaid_block and not in_code_block:
                    slide_data['content'].append(('', in_code_block, False))
                continue
            
            # Mermaid блоки (```mermaid)
            if line.startswith('```mermaid'):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                in_mermaid_block = True
                continue
            elif line.startswith('```') and in_mermaid_block:
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), False, True))  # (content, is_code, is_mermaid)
                    current_block = []
                in_mermaid_block = False
                continue
            
            # Код блоки (```)
            if line.startswith('```'):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                in_code_block = not in_code_block
                continue
            
            if in_mermaid_block:
                current_block.append(line)
                continue
            
            # Изображения ![alt](path) - обрабатываем до заголовков
            image_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', line)
            if image_match:
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                alt_text = image_match.group(1)
                image_path = image_match.group(2)
                slide_data['content'].append(('__IMAGE__', image_path, alt_text))
                continue
            
            # Заголовки
            if line.startswith('# '):
                if current_block:
                    if in_mermaid_block:
                        slide_data['content'].append(('\n'.join(current_block), False, True))
                    else:
                        slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                slide_data['title'] = line[2:].strip()
            elif line.startswith('## '):
                if current_block:
                    if in_mermaid_block:
                        slide_data['content'].append(('\n'.join(current_block), False, True))
                    else:
                        slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                slide_data['subtitle'] = line[3:].strip()
            else:
                if not in_mermaid_block:
                    current_block.append(line)
        
        if current_block:
            if in_mermaid_block:
                slide_data['content'].append(('\n'.join(current_block), False, True))
            else:
                slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
        
        if slide_data['title'] or slide_data['content']:
            slides.append(slide_data)
    
    return slides

def render_mermaid_to_image(mermaid_code, output_format='png'):
    """Конвертирует Mermaid код в изображение используя mermaid-cli"""
    try:
        # Создаем временный файл для Mermaid кода
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False, encoding='utf-8') as f:
            f.write(mermaid_code)
            mermaid_file = f.name
        
        # Создаем временный файл для вывода
        output_file = mermaid_file.replace('.mmd', f'.{output_format}')
        
        # Вызываем mmdc (mermaid-cli) с увеличенным разрешением для лучшего качества
        try:
            result = subprocess.run(
                ['mmdc', '-i', mermaid_file, '-o', output_file, '-b', 'white', '-w', '2400', '-H', '1800', '-s', '2.5'],
                capture_output=True,
                text=True,
                timeout=30
            )
        except FileNotFoundError:
            print("⚠️  mermaid-cli (mmdc) не установлен.")
            print("   Установите: npm install -g @mermaid-js/mermaid-cli")
            print("   Или используйте альтернативный метод рендеринга")
            # Удаляем временный файл
            Path(mermaid_file).unlink(missing_ok=True)
            return None
        
        if result.returncode == 0 and Path(output_file).exists():
            return output_file
        else:
            print(f"⚠️  Ошибка конвертации Mermaid: {result.stderr}")
            # Удаляем временные файлы
            Path(mermaid_file).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)
            return None
    except Exception as e:
        print(f"⚠️  Ошибка при конвертации Mermaid: {e}")
        # Удаляем временный файл
        Path(mermaid_file).unlink(missing_ok=True)
        return None

def calculate_font_size(text, max_width, max_height, initial_size, is_code=False):
    """Вычисляет оптимальный размер шрифта для текста"""
    # Подсчитываем количество строк
    lines = text.split('\n')
    lines_count = len([l for l in lines if l.strip()])  # Только непустые строки
    
    # Оцениваем количество символов
    total_chars = len(text)
    
    # Более точная оценка: для Arial 20pt примерно 6-7 символов на дюйм ширины
    # Учитываем ширину слайда (8.4 дюйма) и отступы
    effective_width = max_width - Inches(0.5)  # Учитываем отступы
    chars_per_line_estimate = max(1, int(effective_width / Inches(0.15)))  # ~6-7 символов на дюйм для 20pt
    estimated_lines = max(lines_count, total_chars / max(chars_per_line_estimate, 1))
    
    # Вычисляем необходимую высоту
    # Межстрочный интервал примерно 1.25 * размер_шрифта в пунктах (более компактный)
    line_height_pt = initial_size * 1.25
    line_height_inches = line_height_pt / 72.0  # Конвертируем в дюймы
    needed_height = estimated_lines * line_height_inches
    
    # Если текст не помещается, уменьшаем размер шрифта
    if needed_height > max_height:
        scale_factor = max_height / needed_height
        # Менее агрессивное уменьшение - используем 0.98 вместо 0.95
        new_size = int(initial_size * scale_factor * 0.98)
        # Минимум 16pt для читаемости (вместо 14pt) - более читаемый текст
        return max(new_size, 16)
    
    return initial_size

def add_text_to_shape(shape, text, font_size, bold=False, color=None, is_code=False, auto_fit=True):
    """Добавляет текст в shape с форматированием"""
    text_frame = shape.text_frame
    text_frame.clear()
    text_frame.word_wrap = True
    
    # Вычисляем оптимальный размер шрифта, если нужно
    if auto_fit and not is_code:
        # Получаем размеры shape
        max_width = shape.width
        max_height = shape.height
        font_size = calculate_font_size(text, max_width, max_height, font_size, is_code)
    
    # Если включен auto_fit, используем авторазмер (но только как запасной вариант)
    if auto_fit and not is_code:
        # Используем авторазмер для подгонки, но с ограничениями
        text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    else:
        text_frame.auto_size = None
    
    # Обработка списков и форматирования
    lines = text.split('\n')
    first_para = True
    
    for line in lines:
        if not line.strip() and not first_para:
            # Пустая строка - добавляем пустой параграф
            p = text_frame.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            continue
        
        if first_para:
            p = text_frame.paragraphs[0]
            first_para = False
        else:
            p = text_frame.add_paragraph()
        
        p.alignment = PP_ALIGN.LEFT
        
        # Определяем уровень списка
        list_level = 0
        if line.strip().startswith('- ') or line.strip().startswith('• '):
            line = line.replace('- ', '', 1).replace('• ', '', 1)
            list_level = 0
        elif line.strip().startswith('  - ') or line.strip().startswith('  • '):
            line = line.replace('  - ', '', 1).replace('  • ', '', 1)
            list_level = 1
        elif line.strip().startswith('    - ') or line.strip().startswith('    • '):
            line = line.replace('    - ', '', 1).replace('    • ', '', 1)
            list_level = 2
        
        p.level = list_level
        
        # Обработка жирного текста **text**
        parts = re.split(r'(\*\*[^*]+\*\*)', line)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run = p.add_run()
                run.text = part[2:-2]
                run.font.size = Pt(font_size)
                run.font.bold = True
                run.font.name = 'Courier New' if is_code else FONT_NAME
                # Жирный текст делаем цветным
                run.font.color.rgb = ACCENT_COLOR if not is_code else (color if color else TEXT_COLOR)
            elif part.strip():
                run = p.add_run()
                run.text = part
                run.font.size = Pt(font_size)
                run.font.bold = bold
                run.font.name = 'Courier New' if is_code else FONT_NAME
                if color:
                    run.font.color.rgb = color
                else:
                    run.font.color.rgb = TEXT_COLOR

def add_gradient_background(slide, prs):
    """Добавляет градиентный фон к слайду"""
    # Создаем прямоугольник на весь слайд для градиента
    left = Inches(0)
    top = Inches(0)
    width = prs.slide_width
    height = prs.slide_height
    
    # Добавляем прямоугольник
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, height
    )
    
    # Устанавливаем градиент
    fill = shape.fill
    fill.gradient()
    fill.gradient_angle = 135.0  # Диагональный градиент
    
    # Настраиваем градиентные остановки
    # В python-pptx градиент обычно создается с двумя остановками
    gradient_stops = fill.gradient_stops
    
    # Первая остановка (начало - синий)
    if len(gradient_stops) > 0:
        gradient_stops[0].color.rgb = GRADIENT_START
        gradient_stops[0].position = 0.0
    
    # Вторая остановка (конец - фиолетовый)
    if len(gradient_stops) > 1:
        gradient_stops[1].color.rgb = GRADIENT_END
        gradient_stops[1].position = 1.0
    elif len(gradient_stops) == 1:
        # Если только одна остановка, используем средний цвет для визуального эффекта
        # Создаем второй прямоугольник с другим цветом для имитации градиента
        shape2 = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, left, top, width, height
        )
        shape2.fill.solid()
        shape2.fill.fore_color.rgb = GRADIENT_END
        shape2.line.fill.background()
        # Делаем полупрозрачным
        shape2.fill.transparency = 0.5
        # Отправляем на задний план
        slide.shapes._spTree.remove(shape2._element)
        slide.shapes._spTree.insert(2, shape2._element)
    
    # Убираем контур
    shape.line.fill.background()
    
    # Отправляем на задний план
    slide.shapes._spTree.remove(shape._element)
    slide.shapes._spTree.insert(2, shape._element)

def create_slide(prs, slide_data, slide_index=0, env_vars=None):
    """Создает слайд из данных"""
    # Используем пустой макет, чтобы избежать placeholders
    slide_layout = prs.slide_layouts[6]  # Blank layout
    slide = prs.slides.add_slide(slide_layout)
    
    # Первый слайд считаем титульным
    is_title_slide = (slide_index == 0)
    
    # Добавляем градиентный фон
    add_gradient_background(slide, prs)
    
    # Добавляем карточку с легкой тенью
    shadow = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(0.25), Inches(0.3),
        Inches(9.6), Inches(7.1)
    )
    shadow.fill.solid()
    shadow.fill.fore_color.rgb = RGBColor(0, 0, 0)
    shadow.fill.transparency = 0.85
    shadow.line.fill.background()
    slide.shapes._spTree.remove(shadow._element)
    slide.shapes._spTree.insert(-1, shadow._element)
    
    content_bg = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(0.2), Inches(0.2),
        Inches(9.6), Inches(7.1)
    )
    content_bg.fill.solid()
    content_bg.fill.fore_color.rgb = RGBColor(252, 253, 255)
    # Современная рамка с акцентным цветом
    content_bg.line.color.rgb = ACCENT_COLOR
    content_bg.line.width = Pt(2)
    
    # Добавляем акцентную полоску сверху
    accent_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.2), Inches(0.2),
        Inches(9.6), Inches(0.15)
    )
    accent_bar.fill.solid()
    accent_bar.fill.fore_color.rgb = TITLE_COLOR
    accent_bar.line.fill.background()
    # Отправляем на передний план, но после контента
    slide.shapes._spTree.remove(accent_bar._element)
    slide.shapes._spTree.insert(-1, accent_bar._element)
    
    # Заголовок слайда
    if slide_data['title']:
        left = Inches(0.5)
        top = Inches(0.9) if is_title_slide else Inches(0.3)  # Уменьшено с 0.5
        width = Inches(9)
        height = Inches(1.7) if is_title_slide else Inches(1.0)  # Уменьшено с 1.2
        title_box = slide.shapes.add_textbox(left, top, width, height)
        title_frame = title_box.text_frame
        title_frame.clear()
        title_frame.word_wrap = True
        title_para = title_frame.paragraphs[0]
        # Для титульного слайда - выравнивание слева, для остальных - по центру
        title_para.alignment = PP_ALIGN.LEFT if is_title_slide else PP_ALIGN.CENTER
        title_run = title_para.add_run()
        title_run.text = slide_data['title']
        title_run.font.size = Pt(36) if is_title_slide else Pt(TITLE_SIZE)
        title_run.font.bold = True
        title_run.font.name = FONT_NAME
        title_run.font.color.rgb = TITLE_COLOR
    
    # Подзаголовок (если есть)
    # Для слайдов только с подзаголовком (без заголовка) - размещаем выше
    subtitle_top = Inches(1.4) if slide_data['title'] else Inches(0.3)  # Уменьшено: было 1.8/0.5
    if slide_data['subtitle']:
        left = Inches(0.5)
        top = subtitle_top
        width = Inches(9)
        height = Inches(0.5)  # Уменьшено с 0.6
        subtitle_box = slide.shapes.add_textbox(left, top, width, height)
        subtitle_frame = subtitle_box.text_frame
        subtitle_frame.clear()
        subtitle_para = subtitle_frame.paragraphs[0]
        subtitle_para.alignment = PP_ALIGN.CENTER
        subtitle_run = subtitle_para.add_run()
        subtitle_run.text = slide_data['subtitle']
        subtitle_run.font.size = Pt(SUBTITLE_SIZE)
        subtitle_run.font.bold = True
        subtitle_run.font.name = FONT_NAME
        subtitle_run.font.color.rgb = SUBTITLE_COLOR
    
    # Содержимое слайда
    if slide_data['content']:
        # Специальная обработка для титульного слайда
        if is_title_slide:
            # Титульный слайд - особое форматирование:
            # 1. Заголовок уже добавлен выше (слева)
            # 2. Автор и класс - слева, выше города/года на 2 строки
            # 3. Город и год - внизу по центру
            
            author_info_lines = []
            city_year_line = None
            
            # Собираем контент из markdown
            for content_item in slide_data['content']:
                if len(content_item) == 3:
                    content, is_code, is_mermaid = content_item
                else:
                    content, is_code = content_item
                if not is_mermaid:
                    # Разбиваем на строки
                    lines = content.split('\n')
                    for line in lines:
                        clean_line = line.strip()
                        # Проверяем, является ли это городом и годом
                        if re.match(r'^[А-Яа-я]+\s+\d{4}$', clean_line):
                            city_year_line = clean_line
                        elif clean_line:  # Непустая строка - добавляем в информацию об авторе
                            author_info_lines.append(clean_line)
            
            # Добавляем информацию об авторе (слева, выше города/года)
            if author_info_lines:
                author_left = Inches(1.0)
                author_width = Inches(8.0)
                # Позиция: выше города/года на 2 строки (примерно 0.5 дюйма)
                author_top = Inches(6.0) - Inches(0.5) - (len(author_info_lines) * Inches(0.25))
                
                author_box = slide.shapes.add_textbox(author_left, author_top, author_width, Inches(1.0))
                author_frame = author_box.text_frame
                author_frame.clear()
                author_frame.word_wrap = True
                
                for idx, line in enumerate(author_info_lines):
                    if idx > 0:
                        para = author_frame.add_paragraph()
                    else:
                        para = author_frame.paragraphs[0]
                    para.alignment = PP_ALIGN.LEFT  # Выравнивание слева
                    run = para.add_run()
                    run.text = line
                    run.font.name = FONT_NAME
                    run.font.size = Pt(18)
                    run.font.color.rgb = TEXT_COLOR
                    run.font.bold = False
                    para.space_after = Pt(4)
            
            # Город и год внизу по центру
            if city_year_line:
                city_year_box = slide.shapes.add_textbox(Inches(1.0), Inches(6.0), Inches(8.0), Inches(0.5))
                city_year_frame = city_year_box.text_frame
                city_year_frame.clear()
                city_year_para = city_year_frame.paragraphs[0]
                city_year_para.alignment = PP_ALIGN.CENTER  # Выравнивание по центру
                city_year_run = city_year_para.add_run()
                city_year_run.text = city_year_line
                city_year_run.font.name = FONT_NAME
                city_year_run.font.size = Pt(18)
                city_year_run.font.color.rgb = TEXT_COLOR
                city_year_run.font.bold = False
            
            return  # Пропускаем обычную обработку контента для титульного слайда
        
        # Вычисляем позицию и размер для контента
        # Минимизируем отступы сверху для всех типов слайдов
        if slide_data['subtitle']:
            # Если есть и заголовок и подзаголовок
            if slide_data['title']:
                content_top = Inches(1.9)  # Уменьшено с 2.4
            else:
                # Только подзаголовок (##) - контент начинается сразу после него
                content_top = Inches(0.9)  # Уменьшено с 1.3
        elif slide_data['title']:
            content_top = Inches(1.4)  # Уменьшено с 2.0
        else:
            content_top = Inches(0.5)  # Уменьшено с 1.0
        content_bottom = Inches(7.0)  # Увеличено для большего пространства для текста
        left = Inches(0.8)
        top = content_top
        width = Inches(8.4)
        height = content_bottom - content_top  # Динамическая высота
        
        # Обрабатываем контент (может быть текст, код, изображения или Mermaid диаграммы)
        all_content_parts = []
        mermaid_diagrams = []
        images_added = False
        
        for content_item in slide_data['content']:
            # Поддерживаем старый формат (content, is_code) и новый (content, is_code, is_mermaid)
            if len(content_item) == 3:
                content, is_code, is_mermaid = content_item
            else:
                content, is_code = content_item
                is_mermaid = False
            
            # Проверяем, является ли это изображением
            if isinstance(content, str) and content == '__IMAGE__':
                # Это изображение: (__IMAGE__, path, alt)
                image_path = is_code  # Второй элемент - путь
                alt_text = is_mermaid if isinstance(is_mermaid, str) else ''  # Третий элемент - alt
                # Определяем путь к изображению
                md_dir = os.path.dirname(md_file)
                if os.path.isabs(image_path):
                    full_path = image_path
                else:
                    full_path = os.path.join(md_dir, image_path)
                    if not os.path.exists(full_path):
                        from config_helper import get_project_root
                        project_root = get_project_root()
                        full_path = os.path.join(project_root, image_path)
                
                if os.path.exists(full_path):
                    # Добавляем изображение на слайд
                    try:
                        # Вычисляем размеры для изображения
                        img_left = Inches(0.5)
                        img_top = content_top
                        img_width = Inches(9.0)
                        # Вычисляем высоту с учетом пропорций изображения
                        from PIL import Image
                        with Image.open(full_path) as img:
                            img_ratio = img.width / img.height
                            img_height = min(img_width / img_ratio, content_bottom - content_top - Inches(0.5))
                        
                        slide.shapes.add_picture(full_path, img_left, img_top, img_width, img_height)
                        print(f"  📷 Изображение добавлено: {alt_text or os.path.basename(image_path)}")
                        images_added = True
                        # Обновляем content_top для следующего контента
                        content_top = img_top + img_height + Inches(0.3)
                    except ImportError:
                        # Если PIL не установлен, используем фиксированную высоту
                        img_height = min(Inches(4.5), content_bottom - content_top - Inches(0.5))
                        slide.shapes.add_picture(full_path, img_left, img_top, img_width, img_height)
                        print(f"  📷 Изображение добавлено: {alt_text or os.path.basename(image_path)}")
                        images_added = True
                        content_top = img_top + img_height + Inches(0.3)
                    except Exception as e:
                        print(f"  ⚠️  Ошибка при добавлении изображения: {e}")
                else:
                    print(f"  ⚠️  Изображение не найдено: {full_path}")
            elif is_mermaid:
                mermaid_diagrams.append(content)
            else:
                all_content_parts.append((content, is_code))
        
        # Если есть Mermaid диаграммы, обрабатываем их отдельно
        if mermaid_diagrams:
            # Используем максимально возможный размер - почти весь слайд
            # Уменьшаем отступы для заголовка, если есть
            if slide_data['title']:
                diagram_top = Inches(1.5)  # Начинаем ниже заголовка
            else:
                diagram_top = Inches(0.5)
            
            if slide_data['subtitle']:
                diagram_top = Inches(2.2)
            
            # Используем почти всю высоту слайда
            diagram_bottom = Inches(7.0)  # Почти до конца слайда
            available_height = diagram_bottom - diagram_top
            
            # Если только одна диаграмма - используем всю доступную высоту
            if len(mermaid_diagrams) == 1:
                diagram_height = available_height
            else:
                # Если несколько диаграмм - делим поровну с минимальным отступом
                diagram_height = (available_height - Inches(0.05 * (len(mermaid_diagrams) - 1))) / len(mermaid_diagrams)
            
            # Используем почти всю ширину слайда
            diagram_left = Inches(0.5)  # Минимальный отступ слева
            diagram_width = Inches(9.0)  # Почти вся ширина
            
            for i, mermaid_code in enumerate(mermaid_diagrams):
                print(f"  📊 Рендеринг Mermaid диаграммы {i+1}/{len(mermaid_diagrams)}...")
                image_path = render_mermaid_to_image(mermaid_code)
                
                if image_path and Path(image_path).exists():
                    try:
                        # Вычисляем позицию для текущей диаграммы
                        current_top = diagram_top + (i * (diagram_height + Inches(0.1)))
                        
                        # Вставляем изображение с увеличенным размером
                        slide.shapes.add_picture(
                            image_path,
                            diagram_left, current_top,
                            diagram_width, diagram_height
                        )
                        # Удаляем временный файл после использования
                        Path(image_path).unlink(missing_ok=True)
                        print(f"  ✅ Диаграмма {i+1} добавлена (размер: {diagram_width}x{diagram_height})")
                    except Exception as e:
                        print(f"  ⚠️  Ошибка при добавлении диаграммы: {e}")
                else:
                    # Если не удалось сгенерировать изображение, показываем текст
                    print(f"  ⚠️  Не удалось сгенерировать изображение, показываем текст")
                    current_top = diagram_top + (i * (diagram_height + Inches(0.1)))
                    text_box = slide.shapes.add_textbox(diagram_left, current_top, diagram_width, diagram_height)
                    add_text_to_shape(text_box, f"[Mermaid диаграмма]\n{mermaid_code}", CODE_SIZE, 
                                     is_code=True, color=TEXT_COLOR)
            
            # Если есть еще текстовый контент, добавляем его ниже диаграмм
            if all_content_parts:
                text_top = diagram_top + (len(mermaid_diagrams) * (diagram_height + Inches(0.1))) + Inches(0.2)
                text_height = content_bottom - text_top
                if text_height > Inches(0.5):  # Только если есть место
                    text_box = slide.shapes.add_textbox(left, text_top, width, text_height)
                    combined_text = '\n\n'.join([c[0] for c in all_content_parts])
                    has_code = any(c[1] for c in all_content_parts)
                    add_text_to_shape(text_box, combined_text, CODE_SIZE if has_code else BODY_SIZE, 
                                     is_code=has_code, color=TEXT_COLOR)
        else:
            # Обычная обработка текста/кода
            # Сохраняем структуру с пустыми строками
            combined_parts = []
            for content, is_code in all_content_parts:
                if content == '':
                    # Пустая строка - добавляем как отдельный элемент
                    combined_parts.append(('', is_code))
                else:
                    # Обычный контент - разбиваем на строки, сохраняя пустые
                    lines = content.split('\n')
                    for line in lines:
                        if line.strip() == '':
                            combined_parts.append(('', is_code))
                        else:
                            combined_parts.append((line, is_code))
            
            # Создаем textbox только если есть текстовый контент
            if all_content_parts:
                # Обновляем размеры textbox с учетом изображений
                if images_added:
                    # Если были добавлены изображения, создаем textbox ниже
                    content_box = slide.shapes.add_textbox(left, content_top, width, content_bottom - content_top)
                else:
                    content_box = slide.shapes.add_textbox(left, top, width, height)
                
                # Объединяем части, сохраняя пустые строки
                combined_text_parts = []
                for part_content, part_is_code in combined_parts:
                    if part_content == '':
                        combined_text_parts.append('')
                    else:
                        combined_text_parts.append(part_content)
                
                combined_text = '\n'.join(combined_text_parts)
                has_code = any(c[1] for c in all_content_parts)
                
                # Для блоков кода добавляем фон
                if has_code:
                    # Добавляем фон для кода
                    code_bg = slide.shapes.add_shape(
                        MSO_SHAPE.ROUNDED_RECTANGLE,
                        left - Inches(0.1), content_top - Inches(0.1),
                        width + Inches(0.2), (content_bottom - content_top) + Inches(0.2)
                    )
                    code_bg.fill.solid()
                    code_bg.fill.fore_color.rgb = CODE_BG_COLOR
                    code_bg.line.fill.background()
                    # Отправляем на задний план
                    slide.shapes._spTree.remove(code_bg._element)
                    slide.shapes._spTree.insert(-2, code_bg._element)
                
                add_text_to_shape(content_box, combined_text, CODE_SIZE if has_code else BODY_SIZE, 
                                 is_code=has_code, color=TEXT_COLOR)
    
    return slide

def generate_pptx_from_markdown(md_file, output_file):
    """Генерирует PPTX презентацию из markdown файла"""
    print(f"📄 Чтение {md_file}...")
    
    # Загружаем переменные из .env для подстановки
    env_vars = None
    try:
        env_vars = load_env_file()
        # Читаем файл и заменяем плейсхолдеры
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Заменяем плейсхолдеры на значения из .env
        for key, value in env_vars.items():
            if key.startswith('CONFERENCE_') or key.startswith('PROJECT_') or \
               key.startswith('AUTHOR_') or key.startswith('SUPERVISOR_'):
                placeholder = '{' + key + '}'
                if placeholder in content:
                    content = content.replace(placeholder, value or '')
        
        # Сохраняем во временный файл для парсинга
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_file = tmp.name
        
        try:
            slides = parse_markdown(tmp_file)
            print(f"   Найдено слайдов: {len(slides)}")
        finally:
            # Удаляем временный файл
            os.unlink(tmp_file)
    except Exception as e:
        print(f"⚠️  Предупреждение: не удалось загрузить данные из .env: {e}")
        print("   Используется исходный файл без подстановки переменных")
        env_vars = None
        slides = parse_markdown(md_file)
        print(f"   Найдено слайдов: {len(slides)}")
    
    # Создаем презентацию
    try:
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)
        
        print("📝 Генерация презентации...")
        
        for i, slide_data in enumerate(slides, 1):
            print(f"  Слайд {i}/{len(slides)}: {slide_data['title'] or 'Без заголовка'}")
            try:
                create_slide(prs, slide_data, slide_index=len(prs.slides), env_vars=env_vars)
            except Exception as e:
                print(f"  ❌ Ошибка при создании слайда {i}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Сохраняем презентацию
        prs.save(output_file)
        print(f"\n✅ Презентация создана: {output_file}")
        print(f"   Размер: {os.path.getsize(output_file) / 1024:.1f} KB")
        print(f"   Количество слайдов: {len(slides)}")
    except Exception as e:
        print(f"❌ Ошибка при создании презентации: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Генерация презентации проекта home-sentinel из presentation.md'
    )
    parser.add_argument(
        '--publish',
        action='store_true',
        help='Подготовить HTML для публикации в GitHub Pages (только для HTML генераторов)'
    )
    parser.add_argument(
        '--release',
        action='store_true',
        help='Создать GitHub Release с сгенерированной презентацией (DOCX/PPTX)'
    )
    parser.add_argument(
        '--version',
        type=str,
        help='Версия для GitHub Release (по умолчанию: timestamp)'
    )
    parser.add_argument(
        '--input',
        type=str,
        help='Путь к исходному markdown файлу (по умолчанию: docs/presentation.md)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Путь к выходному файлу (по умолчанию: используется BUILD_DIR и шаблон из .env)'
    )
    
    args = parser.parse_args()
    
    # Загружаем конфигурацию
    env_vars = load_env_file()
    
    # Определяем пути
    project_root = get_project_root()
    
    # Путь к исходному файлу
    if args.input:
        md_file = args.input
    else:
        md_file = project_root / env_vars.get('DOCS_PRESENTATION_MD', 'docs/presentation.md')
    
    if not os.path.exists(md_file):
        print(f"❌ Файл не найден: {md_file}")
        sys.exit(1)
    
    # Путь к выходному файлу
    if args.output:
        output_file = args.output
    else:
        # Генерируем имя файла по шаблону
        filename, ext = generate_output_filename(str(md_file), env_vars=env_vars, output_ext='.pptx')
        build_dir = get_build_dir(env_vars)
        output_file = build_dir / f"{filename}{ext}"
    
    # Создаем директорию для выходного файла если нужно
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Генерируем презентацию
    generate_pptx_from_markdown(str(md_file), str(output_file))
    
    # Создаем GitHub Release если нужно (для DOCX/PPTX)
    if args.release:
        create_github_release([str(output_file)], env_vars, args.version)

