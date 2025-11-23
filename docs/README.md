# Documentation

Документация проекта home-sentinel.

## Структура

```
docs/
├── source/              # Исходные markdown файлы (версионируются в git)
│   ├── project.md       # Документация проекта
│   └── presentation.md  # Презентация проекта
├── _build/              # Сгенерированные файлы (не в git)
│   └── html/            # HTML для GitHub Pages
└── static/              # Статические ресурсы (CSS, изображения)
```

## Генерация документации

### Локально

```bash
# Генерация всех форматов
python contrib/generate_doc.py              # DOCX -> build/
python contrib/generate_pptx.py             # PPTX -> build/
python contrib/generate_html_presentation.py # HTML -> docs/_build/html/

# Создание GitHub Release с DOCX/PPTX
python contrib/generate_doc.py --release --version 1.0.0
python contrib/generate_pptx.py --release --version 1.0.0
```

### Автоматически (GitHub Actions)

При push в `main/master` с изменениями в `docs/source/`:
- ✅ HTML автоматически публикуется в GitHub Pages
- ✅ DOCX/PPTX сохраняются как артефакты (30 дней)

Ручной запуск через GitHub Actions:
1. Перейдите в Actions → "Publish Documentation"
2. Нажмите "Run workflow"
3. Выберите какие форматы генерировать
4. При необходимости создайте Release

## GitHub Pages

HTML документация автоматически публикуется по адресу:
`https://<username>.github.io/<repository-name>/`

## GitHub Releases

Для публикации DOCX/PPTX в GitHub Releases:

1. **Через GitHub Actions** (рекомендуется):
   - Запустите workflow "Publish Documentation"
   - Установите "Create GitHub Release" = true
   - Укажите версию (опционально)

2. **Локально**:
   ```bash
   python contrib/generate_doc.py --release --version 1.0.0
   python contrib/generate_pptx.py --release --version 1.0.0
   ```
   Требуется установленный и авторизованный GitHub CLI (`gh`).

## Настройка

Пути и шаблоны имен файлов настраиваются в `.env`:

```env
BUILD_DIR=build                          # Временные артефакты (DOCX, PPTX)
DOCS_BUILD_DIR=docs/_build/html          # HTML для GitHub Pages
DOCS_SOURCE_DIR=docs/source              # Исходные markdown файлы
DOC_NAME_TEMPLATE={source_name}_{timestamp}  # Шаблон имени файла
GITHUB_RELEASE_TAG_PREFIX=docs-v         # Префикс тегов Release
```

## Форматы документации

- **DOCX** — для печати и офлайн использования
- **PPTX** — для презентаций
- **HTML** — для онлайн просмотра (GitHub Pages)

