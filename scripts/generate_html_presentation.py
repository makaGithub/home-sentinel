#!/usr/bin/env python3
"""
Генерация HTML презентации проекта home-sentinel из presentation.md

Использование:
    python3 scripts/generate_html_presentation.py

Скрипт читает docs/presentation.md и генерирует docs/presentation.html
"""

import os
import re
import html
import sys
import argparse

# Импортируем вспомогательный модуль для конфигурации
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from config_helper import (
        load_env_file, get_project_root, generate_output_filename,
        get_build_dir, get_docs_build_dir, publish_to_gh_pages
    )
except ImportError as e:
    print(f"⚠️  Предупреждение: не удалось импортировать config_helper: {e}")
    print("   Используются значения по умолчанию")

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
            'content': []
        }
        
        current_block = []
        in_code_block = False
        in_mermaid_block = False
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                # В Mermaid блоках пустые строки сохраняем (они могут быть частью синтаксиса)
                if in_mermaid_block:
                    current_block.append('')  # Сохраняем пустую строку в Mermaid блоке
                elif current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                continue
            
            # Mermaid блоки (```mermaid)
            if line_stripped.startswith('```mermaid'):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                in_mermaid_block = True
                continue
            elif line_stripped.startswith('```') and in_mermaid_block:
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), False, True))  # (content, is_code, is_mermaid)
                    current_block = []
                in_mermaid_block = False
                continue
            
            # Код блоки (```)
            if line_stripped.startswith('```'):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                in_code_block = not in_code_block
                continue
            
            if in_mermaid_block:
                # Внутри Mermaid блока сохраняем все строки, включая пустые
                current_block.append(line)
                continue
            
            # Изображения ![alt](path) - обрабатываем до заголовков
            image_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', line_stripped)
            if image_match:
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                alt_text = image_match.group(1)
                image_path = image_match.group(2)
                slide_data['content'].append(('__IMAGE__', image_path, alt_text))
                continue
            
            # Заголовки (только вне Mermaid блоков)
            if line_stripped.startswith('# '):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                slide_data['title'] = line_stripped[2:].strip()
            elif line_stripped.startswith('## '):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
                    current_block = []
                slide_data['subtitle'] = line_stripped[3:].strip()
            else:
                # Сохраняем оригинальные отступы для списков и кода
                current_block.append(line)
        
        if current_block:
            if in_mermaid_block:
                slide_data['content'].append(('\n'.join(current_block), False, True))
            else:
                slide_data['content'].append(('\n'.join(current_block), in_code_block, False))
        
        if slide_data['title'] or slide_data['content']:
            slides.append(slide_data)
    
    return slides

def markdown_to_html(text, is_code=False):
    """Конвертирует markdown текст в HTML"""
    if is_code:
        # Для блоков кода - просто экранируем и оборачиваем в <pre>
        return f'<pre class="code-block">{html.escape(text)}</pre>'
    
    # Сначала обрабатываем markdown синтаксис, потом экранируем
    html_text = text
    
    # Ссылки [text](url) - обрабатываем до экранирования
    html_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'__LINK_START__\1__LINK_URL__\2__LINK_END__', html_text)
    
    # Код `code` - обрабатываем до экранирования
    html_text = re.sub(r'`([^`]+)`', r'__CODE_START__\1__CODE_END__', html_text)
    
    # Жирный текст **text** - обрабатываем до экранирования
    html_text = re.sub(r'\*\*([^*]+)\*\*', r'__BOLD_START__\1__BOLD_END__', html_text)
    
    # Курсив *text* - обрабатываем до экранирования
    html_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'__ITALIC_START__\1__ITALIC_END__', html_text)
    
    # Экранируем HTML
    html_text = html.escape(html_text)
    
    # Восстанавливаем markdown элементы
    html_text = html_text.replace('__BOLD_START__', '<strong>').replace('__BOLD_END__', '</strong>')
    html_text = html_text.replace('__ITALIC_START__', '<em>').replace('__ITALIC_END__', '</em>')
    html_text = html_text.replace('__CODE_START__', '<code style="background: rgba(102, 126, 234, 0.1); padding: 2px 6px; border-radius: 4px; color: #667eea; font-family: monospace;">').replace('__CODE_END__', '</code>')
    
    # Восстанавливаем ссылки
    def replace_link(match):
        text_part = match.group(1)
        url_part = match.group(2)
        return f'<a href="{url_part}" style="color: #667eea; text-decoration: none; border-bottom: 2px solid rgba(102, 126, 234, 0.3); transition: all 0.2s;" target="_blank">{text_part}</a>'
    
    html_text = re.sub(r'__LINK_START__([^_]+)__LINK_URL__([^_]+)__LINK_END__', replace_link, html_text)
    
    # Списки
    lines = html_text.split('\n')
    result_lines = []
    in_list = False
    
    for line in lines:
        # Маркеры списка
        if re.match(r'^\s*[-•]\s+', line):
            if not in_list:
                result_lines.append('<ul>')
                in_list = True
            # Определяем уровень вложенности
            indent = len(line) - len(line.lstrip())
            level = indent // 2
            content = re.sub(r'^\s*[-•]\s+', '', line)
            list_class = f'level-{level}' if level > 0 else ''
            result_lines.append(f'<li class="{list_class}">{content}</li>')
        elif line.strip() == '':
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            result_lines.append('')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            # Пропускаем пустые строки
            if line.strip():
                result_lines.append(f'<p>{line}</p>')
    
    if in_list:
        result_lines.append('</ul>')
    
    return '\n'.join(result_lines)

def generate_html_presentation(md_file, output_file):
    """Генерирует HTML презентацию из markdown файла"""
    print(f"📄 Чтение {md_file}...")
    
    # Загружаем переменные из .env для подстановки
    try:
        from config_helper import load_env_file
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
        try:
            slides = parse_markdown(md_file)
            print(f"   Найдено слайдов: {len(slides)}")
        except Exception as parse_error:
            print(f"❌ Ошибка при парсинге markdown: {parse_error}")
            import traceback
            traceback.print_exc()
            return
        return
    
    print("📝 Генерация HTML презентации...")
    
    # Генерируем HTML
    html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>home-sentinel - Презентация проекта</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        :root {{
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            --accent-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            --success-gradient: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            --warning-gradient: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
            --dark-gradient: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
        }}
        
        body {{
            font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--primary-gradient);
            background-size: 400% 400%;
            animation: gradientShift 15s ease infinite;
            color: #333;
            overflow: hidden;
            position: relative;
        }}
        
        body::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: 
                radial-gradient(circle at 20% 50%, rgba(102, 126, 234, 0.3) 0%, transparent 50%),
                radial-gradient(circle at 80% 80%, rgba(118, 75, 162, 0.3) 0%, transparent 50%),
                radial-gradient(circle at 40% 20%, rgba(79, 172, 254, 0.2) 0%, transparent 50%);
            animation: pulse 20s ease-in-out infinite;
            pointer-events: none;
        }}
        
        @keyframes gradientShift {{
            0% {{ background-position: 0% 50%; }}
            50% {{ background-position: 100% 50%; }}
            100% {{ background-position: 0% 50%; }}
        }}
        
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.8; }}
        }}
        
        .presentation-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            z-index: 1;
        }}
        
        .slide {{
            display: none;
            width: 92%;
            max-width: 1400px;
            background: linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%);
            border-radius: 30px;
            padding: 80px;
            box-shadow: 
                0 30px 80px rgba(0,0,0,0.2),
                0 0 0 1px rgba(255,255,255,0.5) inset,
                0 0 100px rgba(102, 126, 234, 0.1);
            animation: slideIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
            position: relative;
            overflow: hidden;
        }}
        
        .slide::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: var(--primary-gradient);
            transform: scaleX(0);
            animation: slideInBar 0.6s ease-out 0.3s forwards;
        }}
        
        @keyframes slideInBar {{
            to {{ transform: scaleX(1); }}
        }}
        
        .slide.active {{
            display: block;
        }}
        
        @keyframes slideIn {{
            from {{
                opacity: 0;
                transform: translateY(30px) scale(0.95);
            }}
            to {{
                opacity: 1;
                transform: translateY(0) scale(1);
            }}
        }}
        
        .slide-title {{
            font-size: 3.5em;
            font-weight: 800;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 30px;
            text-align: center;
            line-height: 1.2;
            letter-spacing: -0.02em;
            position: relative;
            animation: titleFadeIn 0.8s ease-out;
        }}
        
        @keyframes titleFadeIn {{
            from {{
                opacity: 0;
                transform: translateY(-20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .slide-subtitle {{
            font-size: 2em;
            background: var(--secondary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 40px;
            text-align: center;
            font-weight: 600;
            letter-spacing: -0.01em;
            animation: subtitleFadeIn 0.8s ease-out 0.2s both;
        }}
        
        @keyframes subtitleFadeIn {{
            from {{
                opacity: 0;
                transform: translateY(-15px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .slide-content {{
            font-size: 1.4em;
            line-height: 1.9;
            color: #2c3e50;
            animation: contentFadeIn 0.8s ease-out 0.4s both;
            max-height: calc(100vh - 300px);
            overflow-y: auto;
            overflow-x: hidden;
            padding-right: 10px;
        }}
        
        .slide-content::-webkit-scrollbar {{
            width: 8px;
        }}
        
        .slide-content::-webkit-scrollbar-track {{
            background: rgba(0,0,0,0.1);
            border-radius: 4px;
        }}
        
        .slide-content::-webkit-scrollbar-thumb {{
            background: rgba(102, 126, 234, 0.5);
            border-radius: 4px;
        }}
        
        .slide-content::-webkit-scrollbar-thumb:hover {{
            background: rgba(102, 126, 234, 0.7);
        }}
        
        @keyframes contentFadeIn {{
            from {{
                opacity: 0;
                transform: translateY(10px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .slide-content p {{
            margin-bottom: 20px;
            color: #34495e;
        }}
        
        .slide-content ul {{
            margin: 25px 0;
            padding-left: 0;
            list-style: none;
        }}
        
        .slide-content li {{
            margin-bottom: 15px;
            padding-left: 35px;
            position: relative;
            color: #2c3e50;
            transition: transform 0.2s;
        }}
        
        .slide-content li::before {{
            content: '▸';
            position: absolute;
            left: 0;
            color: #667eea;
            font-size: 1.2em;
            font-weight: bold;
        }}
        
        .slide-content li:hover {{
            transform: translateX(5px);
            color: #667eea;
        }}
        
        .slide-content li.level-1 {{
            padding-left: 55px;
            font-size: 0.95em;
        }}
        
        .slide-content li.level-1::before {{
            content: '▹';
            color: #764ba2;
        }}
        
        .slide-content li.level-2 {{
            padding-left: 75px;
            font-size: 0.9em;
        }}
        
        .slide-content li.level-2::before {{
            content: '▸';
            color: #f5576c;
        }}
        
        .slide-content strong {{
            background: linear-gradient(120deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            font-weight: 700;
            padding: 0 2px;
        }}
        
        .code-block {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #e8f4f8;
            border-radius: 15px;
            padding: 30px;
            font-family: 'Courier New', 'Monaco', 'Consolas', monospace;
            font-size: 0.95em;
            overflow-x: auto;
            white-space: pre;
            margin: 30px 0;
            box-shadow: 
                0 10px 30px rgba(0,0,0,0.3),
                inset 0 1px 0 rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.1);
            line-height: 1.6;
            position: relative;
        }}
        
        .code-block::before {{
            content: 'CODE';
            position: absolute;
            top: 10px;
            right: 15px;
            font-size: 0.7em;
            opacity: 0.5;
            letter-spacing: 2px;
        }}
        
        .navigation {{
            position: fixed;
            bottom: 40px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 20px;
            z-index: 1000;
        }}
        
        .nav-button {{
            background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.9) 100%);
            backdrop-filter: blur(10px);
            border: 2px solid rgba(102, 126, 234, 0.3);
            padding: 15px 35px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 1.1em;
            font-weight: 600;
            color: #667eea;
            box-shadow: 
                0 8px 25px rgba(102, 126, 234, 0.3),
                0 0 0 0 rgba(102, 126, 234, 0.5);
            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
            position: relative;
            overflow: hidden;
        }}
        
        .nav-button::before {{
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(102, 126, 234, 0.2);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }}
        
        .nav-button:hover {{
            background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
            transform: translateY(-3px) scale(1.05);
            box-shadow: 
                0 12px 35px rgba(102, 126, 234, 0.4),
                0 0 0 4px rgba(102, 126, 234, 0.1);
            border-color: rgba(102, 126, 234, 0.5);
        }}
        
        .nav-button:hover::before {{
            width: 300px;
            height: 300px;
        }}
        
        .nav-button:active {{
            transform: translateY(-1px) scale(1.02);
        }}
        
        .slide-indicator {{
            position: fixed;
            top: 40px;
            right: 40px;
            background: linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(255,255,255,0.9) 100%);
            backdrop-filter: blur(10px);
            padding: 15px 25px;
            border-radius: 50px;
            font-weight: 700;
            color: #667eea;
            box-shadow: 
                0 8px 25px rgba(102, 126, 234, 0.3),
                inset 0 1px 0 rgba(255,255,255,0.5);
            border: 2px solid rgba(102, 126, 234, 0.2);
            z-index: 1000;
        }}
        
        .slide-number {{
            font-size: 1.5em;
            background: var(--primary-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .slide-total {{
            font-size: 1em;
            opacity: 0.6;
            color: #764ba2;
        }}
        
        /* Mermaid диаграммы */
        .mermaid {{
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin: 30px 0;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
            overflow-x: auto;
            overflow-y: auto;
            max-height: 70vh;
            min-height: 300px;
        }}
        
        .mermaid svg {{
            max-width: 100%;
            height: auto;
        }}
        
        /* Адаптивность */
        @media (max-width: 768px) {{
            .slide {{
                padding: 40px 30px;
                width: 95%;
            }}
            
            .slide-title {{
                font-size: 2em;
            }}
            
            .slide-subtitle {{
                font-size: 1.4em;
            }}
            
            .slide-content {{
                font-size: 1.1em;
            }}
            
            .nav-button {{
                padding: 12px 25px;
                font-size: 0.9em;
            }}
            
            .mermaid {{
                padding: 15px;
                font-size: 0.8em;
            }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head>
<body>
    <div class="presentation-container">
'''
    
    # Генерируем слайды
    for i, slide_data in enumerate(slides):
        html_content += f'        <div class="slide" id="slide-{i}" {"data-active" if i == 0 else ""}>\n'
        
        if slide_data['title']:
            html_content += f'            <h1 class="slide-title">{html.escape(slide_data["title"])}</h1>\n'
        
        if slide_data['subtitle']:
            html_content += f'            <h2 class="slide-subtitle">{html.escape(slide_data["subtitle"])}</h2>\n'
        
        if slide_data['content']:
            html_content += '            <div class="slide-content">\n'
            
            # Сначала собираем все Mermaid блоки в один
            mermaid_parts = []
            other_content = []
            
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
                    # Для HTML используем относительный путь от HTML файла
                    html_image_path = os.path.relpath(full_path, os.path.dirname(output_file)) if os.path.exists(full_path) else image_path
                    other_content.append(('__IMAGE__', html_image_path, alt_text))
                elif is_mermaid:
                    mermaid_parts.append(content)
                else:
                    other_content.append((content, is_code))
            
            # Если есть Mermaid части - объединяем их в одну диаграмму
            if mermaid_parts:
                combined_mermaid = '\n'.join(mermaid_parts).strip()
                # Очищаем от возможных лишних символов и нормализуем переносы строк
                combined_mermaid = '\n'.join(line.rstrip() for line in combined_mermaid.split('\n'))
                # Вставляем код напрямую в div с классом mermaid
                # Используем <pre> для сохранения форматирования, но скрываем его
                html_content += f'            <div class="mermaid">\n'
                # Вставляем код как текст - браузер обработает его правильно
                # Не экранируем, так как это код для Mermaid
                html_content += combined_mermaid
                html_content += '\n            </div>\n'
            
            # Добавляем остальной контент
            for content_item in other_content:
                if isinstance(content_item, tuple) and len(content_item) == 3 and content_item[0] == '__IMAGE__':
                    # Это изображение
                    _, image_path, alt_text = content_item
                    html_content += f'<div style="text-align: center; margin: 20px 0;"><img src="{html.escape(image_path)}" alt="{html.escape(alt_text)}" style="max-width: 90%; height: auto; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);" /></div>'
                else:
                    content, is_code = content_item if isinstance(content_item, tuple) else (content_item, False)
                    html_content += markdown_to_html(content, is_code)
                html_content += '\n'
            
            html_content += '            </div>\n'
        
        html_content += '        </div>\n'
    
    # Добавляем навигацию и скрипты
    html_content += f'''    </div>
    
    <div class="slide-indicator">
        <span class="slide-number" id="current-slide">1</span>
        <span class="slide-total"> / {len(slides)}</span>
    </div>
    
    <div class="navigation">
        <button class="nav-button" onclick="previousSlide()">← Назад</button>
        <button class="nav-button" onclick="nextSlide()">Вперед →</button>
    </div>
    
    <script>
        let currentSlide = 0;
        const slides = document.querySelectorAll('.slide');
        const totalSlides = slides.length;
        
        function showSlide(n) {{
            if (n >= totalSlides) n = 0;
            if (n < 0) n = totalSlides - 1;
            
            slides.forEach(slide => slide.classList.remove('active'));
            slides[n].classList.add('active');
            currentSlide = n;
            
            document.getElementById('current-slide').textContent = n + 1;
        }}
        
        function nextSlide() {{
            showSlide(currentSlide + 1);
        }}
        
        function previousSlide() {{
            showSlide(currentSlide - 1);
        }}
        
        // Навигация клавиатурой
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === ' ') {{
                e.preventDefault();
                nextSlide();
            }} else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {{
                e.preventDefault();
                previousSlide();
            }} else if (e.key === 'Home') {{
                e.preventDefault();
                showSlide(0);
            }} else if (e.key === 'End') {{
                e.preventDefault();
                showSlide(totalSlides - 1);
            }}
        }});
        
        // Инициализация Mermaid
        mermaid.initialize({{
            startOnLoad: true,  // Включаем автоинициализацию для элементов, которые уже в DOM
            theme: 'default',
            themeVariables: {{
                primaryColor: '#2196f3',
                primaryTextColor: '#333',
                primaryBorderColor: '#1976d2',
                lineColor: '#2196f3',
                secondaryColor: '#e3f2fd',
                tertiaryColor: '#fff3e0'
            }},
            securityLevel: 'loose'  // Разрешаем HTML в labels
        }});
        
        // Функция для рендеринга Mermaid диаграмм на текущем слайде
        function renderMermaidDiagrams() {{
            const currentSlide = document.querySelector('.slide.active');
            if (!currentSlide) return;
            
            const mermaidElements = currentSlide.querySelectorAll('.mermaid:not([data-processed])');
            if (mermaidElements.length === 0) return;
            
            mermaidElements.forEach((element) => {{
                try {{
                    // Получаем код напрямую из textContent элемента
                    let mermaidCode = element.textContent || element.innerText || '';
                    mermaidCode = mermaidCode.trim();
                    
                    // Очищаем от возможных проблемных символов
                    // Убираем лишние пробелы в начале строк
                    mermaidCode = mermaidCode.split('\\n').map(line => line.trimStart()).join('\\n');
                    
                    if (!mermaidCode) {{
                        console.warn('⚠️ Пустой Mermaid код в элементе');
                        element.setAttribute('data-processed', 'true');
                        return;
                    }}
                    
                    console.log('📝 Найден Mermaid код, длина:', mermaidCode.length, 'символов');
                    console.log('Первые 150 символов:', mermaidCode.substring(0, 150));
                    
                    // Помечаем как обработанный
                    element.setAttribute('data-processed', 'true');
                    
                    // Сохраняем оригинальный код на случай ошибки
                    const originalCode = mermaidCode;
                    
                    // Очищаем элемент полностью
                    element.innerHTML = '';
                    
                    // Вставляем код как текстовый узел
                    element.textContent = mermaidCode;
                    
                    // Используем mermaid.run() для явного рендеринга
                    mermaid.run({{
                        nodes: [element],
                        suppressErrors: false
                    }}).then(() => {{
                        console.log('✅ Mermaid диаграмма успешно отрендерена');
                        // Проверяем результат через небольшую задержку
                        setTimeout(() => {{
                            if (element.querySelector('svg')) {{
                                console.log('✅ SVG создан успешно');
                            }} else {{
                                console.warn('⚠️ SVG не найден после рендеринга');
                                console.warn('Содержимое элемента:', element.innerHTML.substring(0, 300));
                            }}
                        }}, 200);
                    }}).catch((error) => {{
                        console.error('❌ Ошибка рендеринга Mermaid:', error);
                        console.error('Код (первые 300 символов):', originalCode.substring(0, 300));
                        console.error('Полный код:', originalCode);
                        // Показываем ошибку пользователю
                        element.innerHTML = '<div style="color: #d32f2f; padding: 20px; background: #ffebee; border-radius: 8px; border-left: 4px solid #d32f2f;"><strong>Ошибка рендеринга:</strong> ' + error.message + '<br/><br/><details><summary style="cursor: pointer;">Исходный код</summary><pre style="background: #f5f5f5; padding: 15px; margin-top: 10px; overflow-x: auto; font-size: 0.9em;">' + originalCode + '</pre></details></div>';
                    }});
                }} catch (error) {{
                    console.error('❌ Критическая ошибка:', error);
                    element.innerHTML = '<div style="color: #d32f2f; padding: 20px; background: #ffebee; border-radius: 8px;"><strong>Ошибка:</strong> ' + error.message + '</div>';
                    element.setAttribute('data-processed', 'true');
                }}
            }});
        }}
        
        // Инициализация
        showSlide(0);
        
        // Рендерим диаграммы после загрузки страницы
        window.addEventListener('load', () => {{
            setTimeout(() => {{
                renderMermaidDiagrams();
            }}, 300);
        }});
        
        // Также пробуем рендерить после небольшой задержки (на случай если load уже прошел)
        setTimeout(() => {{
            renderMermaidDiagrams();
        }}, 500);
        
        // Перерисовываем Mermaid диаграммы при смене слайдов
        const originalShowSlide = showSlide;
        showSlide = function(n) {{
            originalShowSlide(n);
            // Даем время на отображение слайда, затем рендерим Mermaid
            setTimeout(() => {{
                renderMermaidDiagrams();
            }}, 300);
        }};
    </script>
</body>
</html>'''
    
    # Сохраняем HTML
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ HTML презентация создана: {output_file}")
    print(f"   Размер: {os.path.getsize(output_file) / 1024:.1f} KB")
    print(f"   Количество слайдов: {len(slides)}")
    print(f"\n📖 Откройте файл в браузере для просмотра")
    print(f"   Навигация: стрелки ← → или пробел для следующего слайда")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Генерация HTML презентации проекта home-sentinel из presentation.md'
    )
    parser.add_argument(
        '--publish',
        action='store_true',
        help='Опубликовать сгенерированную HTML презентацию в GitHub Pages'
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
        print(f"❌ Файл не найден: {md_file}", file=sys.stderr)
        print(f"   Текущая директория: {os.getcwd()}", file=sys.stderr)
        print(f"   Project root: {project_root}", file=sys.stderr)
        sys.exit(1)
    
    # Путь к выходному файлу
    if args.output:
        output_file = args.output
    else:
        # Для HTML публикуем в docs/_build/html/
        filename, _ = generate_output_filename(str(md_file), env_vars=env_vars, output_ext='.html')
        docs_build_dir = get_docs_build_dir(env_vars)
        output_file = docs_build_dir / f"{filename}.html"
    
    # Создаем директорию для выходного файла если нужно
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Генерируем HTML презентацию
    generate_html_presentation(str(md_file), str(output_file))
    
    # Подготавливаем для GitHub Pages если нужно (HTML автоматически идет в docs/_build/html/)
    if args.publish:
        publish_to_gh_pages(str(output_file), env_vars)

