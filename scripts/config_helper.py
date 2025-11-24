#!/usr/bin/env python3
"""
Вспомогательный модуль для работы с конфигурацией из .env файла
"""

import os
import re
from datetime import datetime
from pathlib import Path

def load_env_file(env_file='.env'):
    """Загружает переменные из .env файла"""
    env_vars = {}
    
    # Определяем путь к .env файлу
    script_dir = Path(__file__).parent.parent
    env_path = script_dir / env_file
    
    if not env_path.exists():
        # Возвращаем значения по умолчанию
        return {
            'BUILD_DIR': 'build',
            'DOC_NAME_TEMPLATE': '{source_name}_{timestamp}',
            'TIMESTAMP_FORMAT': '%Y%m%d_%H%M%S',
            'DATE_FORMAT': '%Y%m%d',
            'TIME_FORMAT': '%H%M%S',
            'GH_PAGES_BRANCH': 'gh-pages',
            'GH_PAGES_AUTO_PUSH': 'true',
            'DOCS_SOURCE_DIR': 'docs/source',
            'DOCS_BUILD_DIR': 'docs/_build/html',
            'DOCS_PROJECT_MD': 'docs/source/project.md',
            'DOCS_PRESENTATION_MD': 'docs/source/presentation.md',
            'GITHUB_RELEASE_TAG_PREFIX': 'docs-v',
        }
    
    # Читаем .env файл
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Пропускаем комментарии и пустые строки
            if not line or line.startswith('#'):
                continue
            
            # Парсим KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Убираем кавычки если есть
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                env_vars[key] = value
    
    # Добавляем значения по умолчанию для отсутствующих ключей
    defaults = {
        'BUILD_DIR': 'build',
        'DOC_NAME_TEMPLATE': '{source_name}_{timestamp}',
        'TIMESTAMP_FORMAT': '%Y%m%d_%H%M%S',
        'DATE_FORMAT': '%Y%m%d',
        'TIME_FORMAT': '%H%M%S',
            'GH_PAGES_BRANCH': 'gh-pages',
            'GH_PAGES_AUTO_PUSH': 'true',
            'DOCS_SOURCE_DIR': 'docs/source',
            'DOCS_BUILD_DIR': 'docs/_build/html',
            'DOCS_PROJECT_MD': 'docs/source/project.md',
            'DOCS_PRESENTATION_MD': 'docs/source/presentation.md',
            'GITHUB_RELEASE_TAG_PREFIX': 'docs-v',
    }
    
    for key, default_value in defaults.items():
        if key not in env_vars:
            env_vars[key] = default_value
    
    return env_vars

def get_project_root():
    """Возвращает корневую директорию проекта"""
    script_dir = Path(__file__).parent
    return script_dir.parent

def generate_output_filename(source_file, template=None, env_vars=None, output_ext=None):
    """
    Генерирует имя выходного файла по шаблону
    
    Args:
        source_file: путь к исходному файлу (например, 'docs/project.md')
        template: шаблон имени файла (если None, берется из env_vars)
        env_vars: словарь с переменными окружения (если None, загружается из .env)
        output_ext: расширение выходного файла (если None, определяется автоматически)
    
    Returns:
        tuple: (имя файла без расширения, расширение выходного файла)
    """
    if env_vars is None:
        env_vars = load_env_file()
    
    if template is None:
        template = env_vars.get('DOC_NAME_TEMPLATE', '{source_name}_{timestamp}')
    
    # Получаем базовое имя исходного файла без расширения
    source_path = Path(source_file)
    source_name = source_path.stem
    
    # Определяем расширение выходного файла
    if output_ext is None:
        # Если не указано, определяем автоматически
        source_ext = source_path.suffix
        output_ext_map = {
            '.md': '.docx',  # По умолчанию
        }
        output_ext = output_ext_map.get(source_ext, source_ext)
    
    # Генерируем timestamp, date, time
    now = datetime.now()
    timestamp_format = env_vars.get('TIMESTAMP_FORMAT', '%Y%m%d_%H%M%S')
    date_format = env_vars.get('DATE_FORMAT', '%Y%m%d')
    time_format = env_vars.get('TIME_FORMAT', '%H%M%S')
    
    timestamp = now.strftime(timestamp_format)
    date = now.strftime(date_format)
    time = now.strftime(time_format)
    
    # Заменяем переменные в шаблоне
    filename = template.format(
        source_name=source_name,
        timestamp=timestamp,
        date=date,
        time=time
    )
    
    return filename, output_ext

def get_build_dir(env_vars=None):
    """Возвращает путь к директории для сгенерированных файлов"""
    if env_vars is None:
        env_vars = load_env_file()
    
    build_dir = env_vars.get('BUILD_DIR', 'build')
    project_root = get_project_root()
    build_path = project_root / build_dir
    build_path.mkdir(parents=True, exist_ok=True)
    return build_path

def get_docs_build_dir(env_vars=None):
    """Возвращает путь к директории для сгенерированного HTML (GitHub Pages)"""
    if env_vars is None:
        env_vars = load_env_file()
    
    docs_build_dir = env_vars.get('DOCS_BUILD_DIR', 'docs/_build/html')
    project_root = get_project_root()
    docs_build_path = project_root / docs_build_dir
    docs_build_path.mkdir(parents=True, exist_ok=True)
    return docs_build_path

def publish_to_gh_pages(output_file, env_vars=None):
    """Публикует HTML файл в docs/_build/html/ для GitHub Pages (через Actions)"""
    import shutil
    
    if env_vars is None:
        env_vars = load_env_file()
    
    project_root = get_project_root()
    docs_build_dir = get_docs_build_dir(env_vars)
    
    print(f"\n📤 Подготовка для GitHub Pages...")
    print(f"   Директория: {docs_build_dir}")
    
    # Копируем файл в docs/_build/html/
    dest_file = docs_build_dir / os.path.basename(output_file)
    shutil.copy2(output_file, dest_file)
    print(f"✅ Файл скопирован: {dest_file}")
    
    # Если это HTML презентация, создаем index.html
    if output_file.endswith('.html') and 'presentation' in os.path.basename(output_file):
        index_file = docs_build_dir / 'index.html'
        shutil.copy2(output_file, index_file)
        print(f"✅ Создан index.html")
    
    print(f"📝 Файл готов для публикации через GitHub Actions")
    print(f"   Для публикации выполните: git add docs/_build/html/ && git commit && git push")

def create_github_release(files, env_vars=None, version=None):
    """Создает GitHub Release с указанными файлами (DOCX, PPTX)"""
    import subprocess
    import json
    
    if env_vars is None:
        env_vars = load_env_file()
    
    project_root = get_project_root()
    tag_prefix = env_vars.get('GITHUB_RELEASE_TAG_PREFIX', 'docs-v')
    
    # Если версия не указана, используем timestamp
    if version is None:
        from datetime import datetime
        version = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    tag_name = f"{tag_prefix}{version}"
    release_name = f"Documentation {version}"
    
    print(f"\n📦 Создание GitHub Release...")
    print(f"   Tag: {tag_name}")
    print(f"   Release: {release_name}")
    print(f"   Файлы: {len(files)}")
    
    try:
        # Проверяем, что мы в git репозитории
        result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                               cwd=project_root, capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠️  Не в git репозитории, создание Release невозможно")
            return
        
        # Проверяем, есть ли gh CLI
        try:
            gh_result = subprocess.run(['gh', '--version'], 
                                      capture_output=True, text=True, 
                                      timeout=5)
            if gh_result.returncode != 0:
                raise FileNotFoundError("GitHub CLI не найден")
        except FileNotFoundError:
            print("⚠️  GitHub CLI (gh) не установлен")
            print("   Для создания GitHub Release локально установите GitHub CLI:")
            print("   - macOS: brew install gh")
            print("   - Linux: apt install gh (или следуйте инструкциям на https://cli.github.com/)")
            print("   - Windows: winget install GitHub.cli")
            print("")
            print("   После установки авторизуйтесь: gh auth login")
            print("")
            print("   Альтернатива: используйте GitHub Actions для автоматического создания Release")
            print("   Запустите workflow 'Publish Documentation' с опцией 'Create GitHub Release'")
            return
        except Exception as e:
            print(f"⚠️  Ошибка при проверке GitHub CLI: {e}")
            print("   Установите GitHub CLI: https://cli.github.com/")
            return
        
        # Создаем Release через gh CLI
        release_cmd = [
            'gh', 'release', 'create', tag_name,
            '--title', release_name,
            '--notes', f'Documentation release {version}\n\nGenerated from markdown sources.',
        ]
        
        # Добавляем файлы
        for file_path in files:
            if os.path.exists(file_path):
                release_cmd.append(str(file_path))
        
        result = subprocess.run(release_cmd, cwd=project_root, check=True)
        print(f"✅ Release создан: {tag_name}")
        print(f"   Просмотр: gh release view {tag_name}")
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Ошибка при создании Release: {e}")
        print("   Убедитесь, что:")
        print("   - GitHub CLI (gh) установлен и авторизован")
        print("   - У вас есть права на создание Release в репозитории")
        print("   - Или используйте GitHub Actions для автоматического создания")
    except Exception as e:
        print(f"⚠️  Ошибка: {e}")

