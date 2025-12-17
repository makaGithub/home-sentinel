#!/usr/bin/env bash
#
# Удаление скриншотов за указанную дату
#
# Использование:
#   ./scripts/cleanup-screenshots.sh 20241216      # удалить за 16 декабря 2024
#   ./scripts/cleanup-screenshots.sh 2024          # удалить за весь 2024 год
#   ./scripts/cleanup-screenshots.sh               # показать справку
#
# Скриншоты хранятся в формате: frame_{номер}_{YYYYMMDD_HHMMSS}.jpg
#

set -eu

# Директория скриншотов (по умолчанию или из переменной окружения)
SCREENSHOTS_DIR="data/screenshots"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Использование: $0 <дата>"
    echo ""
    echo "Примеры:"
    echo "  $0 20241216     # удалить скриншоты за 16 декабря 2024"
    echo "  $0 202412       # удалить за декабрь 2024"
    echo "  $0 2024         # удалить за весь 2024 год"
    echo ""
    echo "Директория скриншотов: $SCREENSHOTS_DIR"
    exit 1
}

# Проверка аргументов
if [[ $# -lt 1 ]]; then
    usage
fi

DATE_PATTERN="$1"

# Проверка формата даты (только цифры, 4-8 символов)
if ! [[ "$DATE_PATTERN" =~ ^[0-9]{4,8}$ ]]; then
    echo -e "${RED}❌ Неверный формат даты: $DATE_PATTERN${NC}"
    echo "   Ожидается: YYYY, YYYYMM или YYYYMMDD"
    exit 1
fi

# Проверка существования директории
if [[ ! -d "$SCREENSHOTS_DIR" ]]; then
    echo -e "${YELLOW}⚠️  Директория не существует: $SCREENSHOTS_DIR${NC}"
    exit 0
fi

# Поиск файлов по паттерну
# Поддерживает оба формата:
#   старый: frame_{номер}_{YYYYMMDD_HHMMSS}.jpg
#   новый:  frame_{YYYYMMDD_HHMMSS}_{номер}.jpg
PATTERN="frame_*${DATE_PATTERN}*.jpg"

# Подсчёт файлов
FILE_COUNT=$(find "$SCREENSHOTS_DIR" -maxdepth 1 -name "$PATTERN" -type f 2>/dev/null | wc -l | tr -d ' ')

if [[ "$FILE_COUNT" -eq 0 ]]; then
    echo -e "${YELLOW}📁 Файлов за $DATE_PATTERN не найдено${NC}"
    exit 0
fi

# Показываем что будет удалено
echo -e "${YELLOW}🔍 Найдено файлов: $FILE_COUNT${NC}"
echo ""

# Показать первые 5 файлов
find "$SCREENSHOTS_DIR" -maxdepth 1 -name "$PATTERN" -type f 2>/dev/null | head -5 | while read -r f; do
    echo "   $(basename "$f")"
done

if [[ "$FILE_COUNT" -gt 5 ]]; then
    echo "   ... и ещё $((FILE_COUNT - 5)) файлов"
fi

echo ""

# Удаление без подтверждения (для автоматизации)
if [[ "${AUTO_CONFIRM:-}" == "1" ]]; then
    REPLY="y"
else
    printf "Удалить эти файлы? [y/N] "
    read -r REPLY
fi

if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    # Удаление
    DELETED=$(find "$SCREENSHOTS_DIR" -maxdepth 1 -name "$PATTERN" -type f -delete -print 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${GREEN}✅ Удалено файлов: $DELETED${NC}"
else
    echo -e "${YELLOW}⏭️  Отменено${NC}"
fi
