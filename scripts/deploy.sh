#!/bin/bash

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Загрузка конфигурации
CONFIG_FILE=".env"
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Файл конфигурации $CONFIG_FILE не найден!${NC}"
    echo "Создайте его на основе .env.example"
    exit 1
fi

source "$CONFIG_FILE"

# Проверка обязательных переменных
if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_USER" ] || [ -z "$REMOTE_PATH" ]; then
    echo -e "${RED}❌ Не все обязательные переменные заданы в $CONFIG_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Деплой home-sentinel на удаленный хост${NC}"
echo "Хост: $REMOTE_USER@$REMOTE_HOST"
echo "Путь: $REMOTE_PATH"
echo ""

# Параметры команды
DEPLOY_METHOD="${DEPLOY_METHOD:-git}"  # git или rsync
BUILD_REMOTE="${BUILD_REMOTE:-false}"  # собирать на удаленном хосте
RESTART_SERVICES="${RESTART_SERVICES:-true}"  # перезапускать сервисы

# SSH опции из конфига (если заданы)
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=no}"

# Функция для выполнения команд на удаленном хосте
remote_exec() {
    ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST" "$@"
}

# Функция для создания необходимых директорий на удаленном хосте
ensure_data_dirs() {
    echo -e "${YELLOW}📁 Создание необходимых директорий...${NC}"
    
    # Создаем необходимые директории в data/ (они должны существовать ДО запуска контейнера)
    remote_exec "mkdir -p $REMOTE_PATH/data/cache"
    remote_exec "mkdir -p $REMOTE_PATH/data/models"
    remote_exec "mkdir -p $REMOTE_PATH/data/.buildx-cache"
    
    echo -e "${GREEN}✅ Директории созданы${NC}"
}

# Функция для проверки и создания buildx builder для пользователя
ensure_buildx_builder() {
    echo -e "${YELLOW}🔧 Проверка buildx builder...${NC}"
    
    # Проверяем, существует ли builder sane-builder для пользователя
    if remote_exec "docker buildx ls 2>/dev/null | grep -q 'sane-builder'" 2>/dev/null; then
        # Если существует, используем его
        remote_exec "docker buildx use sane-builder" 2>/dev/null || true
        echo -e "${GREEN}✅ Builder sane-builder найден и активирован${NC}"
    else
        # Если не существует, создаем новый
        echo -e "${YELLOW}   Создание buildx builder sane-builder...${NC}"
        remote_exec "docker buildx create --name sane-builder --driver docker-container --use" 2>/dev/null || {
            echo -e "${YELLOW}   Builder уже существует, активируем...${NC}"
            remote_exec "docker buildx use sane-builder" 2>/dev/null || true
        }
        remote_exec "docker buildx inspect sane-builder --bootstrap" 2>/dev/null || true
        echo -e "${GREEN}✅ Builder sane-builder создан и активирован${NC}"
    fi
}

# Функция для синхронизации через rsync
sync_rsync() {
    echo -e "${YELLOW}📦 Синхронизация через rsync...${NC}"
    
    # Создаем временный файл с исключениями
    EXCLUDE_FILE=$(mktemp)
    
    # Добавляем стандартные исключения
    cat > "$EXCLUDE_FILE" <<EOF
.git
data/
.buildx-cache
*.log
.DS_Store
.env
EOF
    
    # Добавляем исключения из .gitignore если он существует
    if [ -f ".gitignore" ]; then
        # Фильтруем комментарии и пустые строки из .gitignore
        grep -v '^#' .gitignore | grep -v '^$' >> "$EXCLUDE_FILE" || true
    fi
    
    # Синхронизация
    rsync -avz --delete \
        --exclude-from="$EXCLUDE_FILE" \
        -e "ssh $SSH_OPTS" \
        ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"
    
    # Удаляем временный файл
    rm -f "$EXCLUDE_FILE"
    
    echo -e "${GREEN}✅ Синхронизация завершена${NC}"
}

# Функция для синхронизации через git
sync_git() {
    echo -e "${YELLOW}📦 Синхронизация через git...${NC}"
    
    # Проверяем, есть ли незакоммиченные изменения
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}⚠️  Есть незакоммиченные изменения${NC}"
        read -p "Закоммитить и запушить? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git add .
            git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')" || true
            git push origin main || git push origin master
        fi
    fi
    
    # Обновляем код на удаленном хосте
    echo "Обновление кода на удаленном хосте..."
    remote_exec "cd $REMOTE_PATH && git pull origin main || git pull origin master"
    
    echo -e "${GREEN}✅ Синхронизация завершена${NC}"
}

# Основной процесс деплоя
main() {
    # Сначала создаем необходимые директории на удаленном хосте
    ensure_data_dirs
    
    # Выбор метода синхронизации
    case "$DEPLOY_METHOD" in
        rsync)
            sync_rsync
            ;;
        git)
            sync_git
            ;;
        *)
            echo -e "${RED}❌ Неизвестный метод деплоя: $DEPLOY_METHOD${NC}"
            exit 1
            ;;
    esac
    
    # Копирование .env файла если нужно
    if [ -f ".env" ] && [ "${COPY_ENV:-true}" = "true" ]; then
        echo -e "${YELLOW}📋 Копирование .env файла...${NC}"
        scp $SSH_OPTS .env "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/.env"
    fi
    
    # Настройка Docker на удаленном хосте (если нужно)
    if [ "${SETUP_DOCKER:-false}" = "true" ]; then
        echo -e "${YELLOW}🔧 Настройка Docker на удаленном хосте...${NC}"
        remote_exec "mkdir -p $REMOTE_PATH/scripts"
        scp $SSH_OPTS scripts/setup-host.sh "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/scripts/"
        remote_exec "cd $REMOTE_PATH && chmod +x scripts/setup-host.sh && sudo scripts/setup-host.sh"
    fi
    
    # Сборка и запуск на удаленном хосте
    if [ "${BUILD_REMOTE:-false}" = "true" ]; then
        ensure_buildx_builder
        echo -e "${YELLOW}🔨 Сборка Docker образов на удаленном хосте с использованием кэша...${NC}"
        remote_exec "cd $REMOTE_PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_DOCKER_CLI_BUILD=1 && docker compose build --progress=plain"
    fi
    
    # Убеждаемся, что директории созданы и исправлены перед запуском
    ensure_data_dirs
    
    # Перезапуск сервисов
    if [ "${RESTART_SERVICES:-true}" = "true" ]; then
        echo -e "${YELLOW}🔄 Остановка контейнеров...${NC}"
        remote_exec "cd $REMOTE_PATH && docker compose down" || true
        
        echo -e "${YELLOW}🔄 Запуск сервисов...${NC}"
        remote_exec "cd $REMOTE_PATH && docker compose up -d"
        echo -e "${GREEN}✅ Сервисы перезапущены${NC}"
    fi
    
    # Показ статуса
    echo ""
    echo -e "${GREEN}📊 Статус сервисов:${NC}"
    remote_exec "cd $REMOTE_PATH && docker compose ps"
    
    echo ""
    echo -e "${GREEN}✅ Деплой завершен!${NC}"
    echo ""
    echo "Для просмотра логов:"
    echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_PATH && docker compose logs -f'"
}

# Обработка аргументов командной строки
case "${1:-}" in
    sync)
        if [ "$DEPLOY_METHOD" = "rsync" ]; then
            sync_rsync
        else
            sync_git
        fi
        ;;
    build)
        ensure_buildx_builder
        echo -e "${YELLOW}🔨 Сборка Docker образов с использованием кэша...${NC}"
        remote_exec "cd $REMOTE_PATH && export DOCKER_BUILDKIT=1 && export COMPOSE_DOCKER_CLI_BUILD=1 && docker compose build --progress=plain"
        ;;
    restart)
        remote_exec "cd $REMOTE_PATH && docker compose restart"
        ;;
    logs)
        remote_exec "cd $REMOTE_PATH && docker compose logs -f ${2:-}"
        ;;
    status)
        remote_exec "cd $REMOTE_PATH && docker compose ps"
        ;;
    ssh)
        ssh $SSH_OPTS "$REMOTE_USER@$REMOTE_HOST"
        ;;
    *)
        main
        ;;
esac

