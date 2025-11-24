#!/bin/bash

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Настройка Docker окружения для ha-ai-stack на Ubuntu 24.04.3...${NC}"
echo ""

# Проверка, что скрипт запущен от root или с sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}⚠️  Скрипт требует прав root. Используйте: sudo ./scripts/setup-docker.sh${NC}"
    exit 1
fi

# Определение версии Ubuntu
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo -e "${GREEN}✅ Обнаружена система: $PRETTY_NAME${NC}"
else
    echo -e "${YELLOW}⚠️  Не удалось определить версию ОС${NC}"
fi

# Обновление списка пакетов
echo -e "${BLUE}📦 Обновление списка пакетов...${NC}"
apt-get update -qq

# Установка необходимых зависимостей
echo -e "${BLUE}📦 Установка необходимых зависимостей...${NC}"
apt-get install -y -qq \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    > /dev/null

# Проверка и установка Docker
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}📦 Установка Docker...${NC}"
    
    # Добавление официального GPG ключа Docker
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # Добавление репозитория Docker
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Установка Docker
    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-compose-plugin \
        > /dev/null
    
    # Попытка установить buildx plugin (может быть недоступен в некоторых версиях)
    if apt-cache show docker-buildx-plugin &> /dev/null; then
        apt-get install -y -qq docker-buildx-plugin > /dev/null 2>&1 || true
    fi
    
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo -e "${GREEN}✅ Docker уже установлен: $(docker --version)${NC}"
fi

# Проверка и установка Docker Compose
if ! command -v docker compose &> /dev/null; then
    echo -e "${YELLOW}📦 Установка Docker Compose...${NC}"
    apt-get install -y -qq docker-compose-plugin > /dev/null
    echo -e "${GREEN}✅ Docker Compose установлен${NC}"
else
    echo -e "${GREEN}✅ Docker Compose найден: $(docker compose version)${NC}"
fi

# Проверка buildx (обычно уже включен в Docker 20.10+)
if ! docker buildx version &> /dev/null; then
    echo -e "${YELLOW}📦 Установка Docker Buildx...${NC}"
    
    # Попытка установить через apt
    if apt-cache show docker-buildx-plugin &> /dev/null; then
        apt-get install -y -qq docker-buildx-plugin > /dev/null 2>&1
    fi
    
    # Если все еще не работает, пробуем установить вручную
    if ! docker buildx version &> /dev/null; then
        echo -e "${YELLOW}   Установка buildx вручную...${NC}"
        
        # Создаем директорию для плагинов
        mkdir -p /usr/local/lib/docker/cli-plugins
        
        # Определяем архитектуру
        ARCH=$(uname -m)
        case "$ARCH" in
            x86_64) BUILDX_ARCH="amd64" ;;
            aarch64|arm64) BUILDX_ARCH="arm64" ;;
            armv7l) BUILDX_ARCH="arm-v7" ;;
            *) BUILDX_ARCH="amd64" ;;  # Fallback
        esac
        
        # Получаем последнюю версию buildx
        BUILDX_VERSION=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest | grep '"tag_name"' | cut -d '"' -f 4 || echo "v0.12.1")
        
        # Скачиваем buildx
        BUILDX_URL="https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${BUILDX_ARCH}"
        
        if curl -fsSL "$BUILDX_URL" -o /usr/local/lib/docker/cli-plugins/docker-buildx; then
            chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx
            echo -e "${GREEN}✅ Docker Buildx установлен вручную (версия ${BUILDX_VERSION})${NC}"
        else
            echo -e "${YELLOW}⚠️  Не удалось скачать buildx. Продолжаем без него.${NC}"
            echo -e "${YELLOW}   Buildx может быть уже встроен в docker-ce-cli${NC}"
        fi
    else
        echo -e "${GREEN}✅ Docker Buildx установлен${NC}"
    fi
else
    echo -e "${GREEN}✅ Docker buildx найден: $(docker buildx version)${NC}"
fi

# Проверка и установка nvidia-container-toolkit (для GPU)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${BLUE}🎮 Обнаружена NVIDIA GPU${NC}"
    
    if ! command -v nvidia-container-runtime &> /dev/null; then
        echo -e "${YELLOW}📦 Установка NVIDIA Container Toolkit...${NC}"
        
        # Добавление репозитория NVIDIA
        distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        
        apt-get update -qq
        apt-get install -y -qq nvidia-container-toolkit > /dev/null
        
        # Настройка runtime
        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
        
        echo -e "${GREEN}✅ NVIDIA Container Toolkit установлен и настроен${NC}"
    else
        echo -e "${GREEN}✅ NVIDIA Container Toolkit уже установлен${NC}"
    fi
else
    echo -e "${YELLOW}ℹ️  NVIDIA GPU не обнаружена (nvidia-smi не найден)${NC}"
    echo -e "${YELLOW}   Продолжаем без GPU поддержки${NC}"
fi

# Добавление текущего пользователя в группу docker (если не root)
if [ -n "$SUDO_USER" ]; then
    echo -e "${BLUE}👤 Добавление пользователя $SUDO_USER в группу docker...${NC}"
    usermod -aG docker "$SUDO_USER" 2>/dev/null || true
    echo -e "${GREEN}✅ Пользователь добавлен в группу docker${NC}"
    echo -e "${YELLOW}⚠️  Выйдите и войдите снова, чтобы изменения вступили в силу${NC}"
fi

# Создание builder с поддержкой cache (docker-container драйвер)
BUILDER_NAME="ha-ai-stack-builder"

echo -e "${BLUE}🔨 Проверка builder '$BUILDER_NAME'...${NC}"

if docker buildx ls 2>/dev/null | grep -q "$BUILDER_NAME"; then
    echo -e "${GREEN}✅ Builder '$BUILDER_NAME' уже существует${NC}"
    docker buildx use "$BUILDER_NAME" 2>/dev/null || true
else
    echo -e "${BLUE}📦 Создание нового builder '$BUILDER_NAME'...${NC}"
    
    # Пробуем создать builder с docker-container драйвером
    if docker buildx create --name "$BUILDER_NAME" --driver docker-container --use 2>/dev/null; then
        echo -e "${GREEN}✅ Builder '$BUILDER_NAME' создан и активирован (docker-container драйвер)${NC}"
    else
        # Если не получилось, используем default драйвер
        echo -e "${YELLOW}⚠️  Не удалось создать builder с docker-container драйвером${NC}"
        echo -e "${YELLOW}   Используется default builder${NC}"
    fi
fi

# Проверка текущего builder
CURRENT_BUILDER=$(docker buildx ls 2>/dev/null | grep '*' | awk '{print $1}' || echo "default")
echo -e "${GREEN}✅ Текущий builder: $CURRENT_BUILDER${NC}"

# Настройка переменных окружения
echo ""
echo -e "${BLUE}📝 Настройка переменных окружения...${NC}"

# Определяем shell config файл для пользователя (если не root)
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
    SHELL_CONFIG="$USER_HOME/.bashrc"
else
    SHELL_CONFIG="$HOME/.bashrc"
fi

# Добавление переменных в shell config
if [ -f "$SHELL_CONFIG" ]; then
    if ! grep -q "DOCKER_BUILDKIT=1" "$SHELL_CONFIG"; then
        echo "" >> "$SHELL_CONFIG"
        echo "# Docker BuildKit для ha-ai-stack" >> "$SHELL_CONFIG"
        echo "export DOCKER_BUILDKIT=1" >> "$SHELL_CONFIG"
        echo "export COMPOSE_DOCKER_CLI_BUILD=1" >> "$SHELL_CONFIG"
        echo -e "${GREEN}✅ Переменные окружения добавлены в $SHELL_CONFIG${NC}"
    else
        echo -e "${GREEN}✅ Переменные окружения уже настроены в $SHELL_CONFIG${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Файл $SHELL_CONFIG не найден. Создаю новый...${NC}"
    mkdir -p "$(dirname "$SHELL_CONFIG")"
    echo "# Docker BuildKit для ha-ai-stack" > "$SHELL_CONFIG"
    echo "export DOCKER_BUILDKIT=1" >> "$SHELL_CONFIG"
    echo "export COMPOSE_DOCKER_CLI_BUILD=1" >> "$SHELL_CONFIG"
    echo -e "${GREEN}✅ Файл $SHELL_CONFIG создан с переменными окружения${NC}"
fi

# Настройка переменных для systemd (если нужно)
if [ ! -d /etc/systemd/system/docker.service.d ]; then
    mkdir -p /etc/systemd/system/docker.service.d
fi
if [ ! -f /etc/systemd/system/docker.service.d/buildkit.conf ]; then
    cat > /etc/systemd/system/docker.service.d/buildkit.conf <<EOF
[Service]
Environment="DOCKER_BUILDKIT=1"
EOF
    systemctl daemon-reload
    echo -e "${GREEN}✅ Переменные окружения настроены для systemd${NC}"
fi

echo -e "${GREEN}✅ Переменные окружения настроены${NC}"

# Создание директории для кэша (если мы в директории проекта)
if [ -f "docker-compose.yml" ] || [ -f "setup-docker.sh" ]; then
    echo -e "${BLUE}📁 Создание директории для кэша...${NC}"
    mkdir -p .buildx-cache
    chmod 755 .buildx-cache
    echo -e "${GREEN}✅ Директория .buildx-cache создана${NC}"
else
    echo -e "${YELLOW}ℹ️  Директория .buildx-cache будет создана при первом запуске docker compose${NC}"
fi

# Проверка работы Docker
echo ""
echo -e "${BLUE}🧪 Проверка работы Docker...${NC}"
if docker info &> /dev/null; then
    echo -e "${GREEN}✅ Docker работает корректно${NC}"
else
    echo -e "${RED}❌ Проблема с Docker. Проверьте статус: systemctl status docker${NC}"
fi

# Проверка buildx
if docker buildx version &> /dev/null; then
    BUILDX_VER=$(docker buildx version 2>/dev/null | head -n1 || echo "unknown")
    echo -e "${GREEN}✅ Buildx работает корректно: $BUILDX_VER${NC}"
    
    # Проверяем, можем ли мы использовать buildx для сборки
    if docker buildx inspect &> /dev/null; then
        echo -e "${GREEN}✅ Buildx готов к использованию${NC}"
    else
        echo -e "${YELLOW}ℹ️  Buildx доступен, но builder не настроен (это нормально)${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Buildx не доступен, но это может быть нормально${NC}"
    echo -e "${YELLOW}   В современных версиях Docker buildx встроен в docker-ce-cli${NC}"
    echo -e "${YELLOW}   Попробуйте перезапустить Docker: systemctl restart docker${NC}"
fi

# Проверка GPU (если доступна)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${BLUE}🎮 Проверка GPU поддержки в Docker...${NC}"
    if docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo -e "${GREEN}✅ GPU доступна в Docker${NC}"
    else
        echo -e "${YELLOW}⚠️  GPU не доступна в Docker. Проверьте настройку nvidia-container-toolkit${NC}"
    fi
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Настройка завершена!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}📋 Следующие шаги:${NC}"
echo ""
if [ -n "$SUDO_USER" ]; then
    echo -e "${YELLOW}1. Выйдите и войдите снова, чтобы изменения в группе docker вступили в силу${NC}"
    echo -e "${YELLOW}   Или выполните: newgrp docker${NC}"
    echo ""
fi
echo -e "${BLUE}2. Перейдите в директорию проекта:${NC}"
echo "   cd $(pwd)"
echo ""
echo -e "${BLUE}3. Запустите сервисы:${NC}"
echo "   docker compose up --build -d"
echo ""
echo -e "${BLUE}4. Проверьте статус:${NC}"
echo "   docker compose ps"
echo ""
echo -e "${BLUE}5. Просмотр логов:${NC}"
echo "   docker compose logs -f"
echo ""

