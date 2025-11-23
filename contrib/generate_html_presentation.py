#!/usr/bin/env python3
"""
Генерация HTML презентации проекта home-sentinel из presentation.md

Использование:
    python3 contrib/generate_html_presentation.py

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
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block))
                    current_block = []
                continue
            
            # Код блоки (```)
            if line_stripped.startswith('```'):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block))
                    current_block = []
                in_code_block = not in_code_block
                continue
            
            # Заголовки
            if line_stripped.startswith('# '):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block))
                    current_block = []
                slide_data['title'] = line_stripped[2:].strip()
            elif line_stripped.startswith('## '):
                if current_block:
                    slide_data['content'].append(('\n'.join(current_block), in_code_block))
                    current_block = []
                slide_data['subtitle'] = line_stripped[3:].strip()
            else:
                # Сохраняем оригинальные отступы для списков и кода
                current_block.append(line)
        
        if current_block:
            slide_data['content'].append(('\n'.join(current_block), in_code_block))
        
        if slide_data['title'] or slide_data['content']:
            slides.append(slide_data)
    
    return slides

def markdown_to_html(text, is_code=False):
    """Конвертирует markdown текст в HTML"""
    if is_code:
        # Для блоков кода - просто экранируем и оборачиваем в <pre>
        return f'<pre class="code-block">{html.escape(text)}</pre>'
    
    html_text = html.escape(text)
    
    # Жирный текст **text**
    html_text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html_text)
    
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
            result_lines.append(f'<p>{line}</p>')
    
    if in_list:
        result_lines.append('</ul>')
    
    return '\n'.join(result_lines)

def generate_html_presentation(md_file, output_file):
    """Генерирует HTML презентацию из markdown файла"""
    print(f"📄 Чтение {md_file}...")
    try:
        slides = parse_markdown(md_file)
        print(f"   Найдено слайдов: {len(slides)}")
    except Exception as e:
        print(f"❌ Ошибка при парсинге markdown: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("📝 Генерация HTML презентации...")
    
    # Генерируем HTML
    html_content = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>home-sentinel - Презентация проекта</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            overflow: hidden;
        }}
        
        .presentation-container {{
            width: 100vw;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}
        
        .slide {{
            display: none;
            width: 90%;
            max-width: 1200px;
            background: white;
            border-radius: 20px;
            padding: 60px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideIn 0.5s ease-out;
        }}
        
        .slide.active {{
            display: block;
        }}
        
        @keyframes slideIn {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}
        
        .slide-title {{
            font-size: 3em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 20px;
            text-align: center;
        }}
        
        .slide-subtitle {{
            font-size: 1.8em;
            color: #764ba2;
            margin-bottom: 30px;
            text-align: center;
            font-weight: 600;
        }}
        
        .slide-content {{
            font-size: 1.3em;
            line-height: 1.8;
            color: #333;
        }}
        
        .slide-content p {{
            margin-bottom: 15px;
        }}
        
        .slide-content ul {{
            margin: 20px 0;
            padding-left: 40px;
        }}
        
        .slide-content li {{
            margin-bottom: 10px;
        }}
        
        .slide-content li.level-1 {{
            padding-left: 20px;
        }}
        
        .slide-content li.level-2 {{
            padding-left: 40px;
        }}
        
        .slide-content strong {{
            color: #667eea;
            font-weight: 600;
        }}
        
        .code-block {{
            background: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 20px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            overflow-x: auto;
            white-space: pre;
            margin: 20px 0;
        }}
        
        .navigation {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 15px;
            z-index: 1000;
        }}
        
        .nav-button {{
            background: rgba(255, 255, 255, 0.9);
            border: none;
            padding: 12px 24px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            color: #667eea;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            transition: all 0.3s;
        }}
        
        .nav-button:hover {{
            background: white;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.3);
        }}
        
        .nav-button:active {{
            transform: translateY(0);
        }}
        
        .slide-indicator {{
            position: fixed;
            top: 30px;
            right: 30px;
            background: rgba(255, 255, 255, 0.9);
            padding: 10px 20px;
            border-radius: 20px;
            font-weight: 600;
            color: #667eea;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }}
        
        .slide-number {{
            font-size: 1.2em;
        }}
        
        .slide-total {{
            font-size: 0.9em;
            opacity: 0.7;
        }}
    </style>
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
            for content, is_code in slide_data['content']:
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
        
        // Инициализация
        showSlide(0);
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

