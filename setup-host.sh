#!/bin/bash

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Настройка хоста для ha-ai-stack на Ubuntu 24.04.3...${NC}"
echo ""

# Проверка, что скрипт запущен от root или с sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}⚠️  Скрипт требует прав root. Используйте: sudo ./setup-host.sh${NC}"
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
    pciutils \
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

# Проверка и установка NVIDIA драйверов (если нужно)
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${BLUE}🎮 Проверка наличия NVIDIA GPU...${NC}"
    
    # Проверяем, есть ли NVIDIA GPU в системе
    if lspci | grep -i nvidia &> /dev/null; then
        echo -e "${YELLOW}📦 Обнаружена NVIDIA GPU, но драйверы не установлены${NC}"
        echo -e "${YELLOW}📦 Установка NVIDIA драйверов...${NC}"
        
        # Установка утилиты для работы с драйверами
        apt-get install -y -qq ubuntu-drivers-common > /dev/null
        
        # Определение рекомендуемого драйвера
        RECOMMENDED_DRIVER=$(ubuntu-drivers devices 2>/dev/null | grep -i "recommended" | head -n1 | awk '{print $3}' || echo "")
        
        if [ -n "$RECOMMENDED_DRIVER" ]; then
            echo -e "${BLUE}   Рекомендуемый драйвер: $RECOMMENDED_DRIVER${NC}"
            echo -e "${YELLOW}   Установка драйвера (это может занять несколько минут)...${NC}"
            
            # Установка рекомендуемого драйвера
            DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$RECOMMENDED_DRIVER" > /dev/null 2>&1
            
            echo -e "${GREEN}✅ NVIDIA драйвер установлен${NC}"
            echo -e "${YELLOW}⚠️  Требуется перезагрузка системы для активации драйвера${NC}"
            echo -e "${YELLOW}   После перезагрузки запустите скрипт снова для настройки nvidia-container-toolkit${NC}"
        else
            # Попытка автоматической установки
            echo -e "${YELLOW}   Автоматическая установка рекомендуемого драйвера...${NC}"
            DEBIAN_FRONTEND=noninteractive ubuntu-drivers autoinstall -y > /dev/null 2>&1
            
            if command -v nvidia-smi &> /dev/null; then
                echo -e "${GREEN}✅ NVIDIA драйвер установлен${NC}"
            else
                echo -e "${YELLOW}⚠️  Драйвер установлен, но требуется перезагрузка${NC}"
                echo -e "${YELLOW}   После перезагрузки запустите скрипт снова${NC}"
            fi
        fi
        
        # Проверяем, установился ли драйвер (без перезагрузки nvidia-smi может не работать)
        if command -v nvidia-smi &> /dev/null; then
            echo -e "${GREEN}✅ NVIDIA драйвер готов к использованию${NC}"
        else
            echo -e "${YELLOW}⚠️  Драйвер установлен, но требуется перезагрузка системы${NC}"
            echo -e "${YELLOW}   Выполните: sudo reboot${NC}"
            echo -e "${YELLOW}   После перезагрузки запустите скрипт снова${NC}"
            # Продолжаем выполнение, но пропускаем настройку nvidia-container-toolkit
        fi
    else
        echo -e "${YELLOW}ℹ️  NVIDIA GPU не обнаружена в системе${NC}"
        echo -e "${YELLOW}   Продолжаем без GPU поддержки${NC}"
    fi
fi

# Проверка и установка nvidia-container-toolkit (для GPU)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${BLUE}🎮 Обнаружена NVIDIA GPU (nvidia-smi доступен)${NC}"
    
    GPU_NEEDS_SETUP=false
    
    if ! command -v nvidia-container-runtime &> /dev/null; then
        echo -e "${YELLOW}📦 Установка NVIDIA Container Toolkit...${NC}"
        
        # Проверяем и исправляем существующий файл репозитория
        if [ -f /etc/apt/sources.list.d/nvidia-container-toolkit.list ]; then
            # Проверяем на HTML, неверный формат или ubuntu24.04
            if grep -qiE "(<html|<!DOCTYPE|404|Not Found)" /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null || \
               ! grep -q "^deb" /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null || \
               grep -q "ubuntu24.04" /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null; then
                echo -e "${YELLOW}⚠️  Обнаружен поврежденный файл репозитория (содержит HTML, неверный формат или ubuntu24.04). Исправляем...${NC}"
                rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list
            fi
        fi
        
        # Добавление репозитория NVIDIA
        # Определяем distribution правильно для Ubuntu
        # Для Ubuntu 24.04 используем репозиторий Ubuntu 22.04 (совместим, так как для 24.04 нет официального репозитория)
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            if [ "$ID" = "ubuntu" ]; then
                # Для Ubuntu 24.04 и новее используем репозиторий 22.04
                if [ "$VERSION_ID" = "24.04" ] || [ "$VERSION_ID" = "24.10" ]; then
                    DISTRIBUTION="ubuntu22.04"
                    echo -e "${BLUE}   Ubuntu ${VERSION_ID} обнаружена, используем репозиторий Ubuntu 22.04 для совместимости${NC}"
                else
                    DISTRIBUTION="ubuntu${VERSION_ID}"
                fi
            else
                DISTRIBUTION="${ID}${VERSION_ID}"
            fi
        else
            DISTRIBUTION="ubuntu22.04"  # Fallback для Ubuntu 24.04
        fi
        
        echo -e "${BLUE}   Используем distribution: $DISTRIBUTION${NC}"
        
        # Установка GPG ключа
        echo -e "${BLUE}   Добавление GPG ключа...${NC}"
        # Удаляем существующий ключ, если есть, чтобы избежать интерактивного запроса
        rm -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        
        # Получение списка репозиториев с проверкой
        echo -e "${BLUE}   Получение списка репозиториев...${NC}"
        REPO_URL="https://nvidia.github.io/libnvidia-container/$DISTRIBUTION/libnvidia-container.list"
        
        # Пробуем получить список репозиториев с таймаутом
        # Временно отключаем set -e для обработки ошибок curl
        set +e
        REPO_CONTENT=$(curl -fsSL --max-time 10 "$REPO_URL" 2>&1)
        CURL_EXIT_CODE=$?
        set -e
        
        # Проверяем результат curl
        if [ $CURL_EXIT_CODE -ne 0 ] || [ -z "$REPO_CONTENT" ]; then
            echo -e "${YELLOW}⚠️  Не удалось получить список репозиториев для $DISTRIBUTION (код ошибки: $CURL_EXIT_CODE)${NC}"
            echo -e "${YELLOW}   Используем альтернативный метод...${NC}"
            REPO_CONTENT=""
        fi
        
        # Для Ubuntu 24.04 всегда используем репозиторий Ubuntu 22.04
        if [ "$DISTRIBUTION" = "ubuntu22.04" ] && [ -f /etc/os-release ]; then
            . /etc/os-release
            if [ "$VERSION_ID" = "24.04" ] || [ "$VERSION_ID" = "24.10" ]; then
                echo -e "${BLUE}   Для Ubuntu ${VERSION_ID} принудительно используем репозиторий Ubuntu 22.04${NC}"
                REPO_CONTENT=""  # Принудительно используем альтернативный метод
            fi
        fi
        
        # Проверяем, что получили правильный формат (не HTML)
        if [ -z "$REPO_CONTENT" ] || echo "$REPO_CONTENT" | grep -qiE "(<html|<!DOCTYPE|404|Not Found|error)" 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Используем репозиторий Ubuntu 22.04 (совместим с Ubuntu 24.04)${NC}"
            
            # Альтернативный метод: используем репозиторий для Ubuntu 22.04 (совместим с 24.04)
            ARCH=$(dpkg --print-architecture)
            cat > /etc/apt/sources.list.d/nvidia-container-toolkit.list <<EOF
deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/ubuntu22.04/${ARCH} /
EOF
            echo -e "${GREEN}✅ Список репозиториев создан (используем Ubuntu 22.04 репозиторий для совместимости)${NC}"
        else
            # Проверяем, что полученный контент действительно содержит правильный URL (не ubuntu24.04)
            if echo "$REPO_CONTENT" | grep -q "ubuntu24.04" 2>/dev/null; then
                echo -e "${YELLOW}⚠️  Обнаружен URL для ubuntu24.04, заменяем на ubuntu22.04${NC}"
                REPO_CONTENT=$(echo "$REPO_CONTENT" | sed 's/ubuntu24\.04/ubuntu22.04/g')
            fi
            
            # Записываем полученный контент с добавлением signed-by
            echo "$REPO_CONTENT" | \
                sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
            
            # Проверяем, что файл содержит правильный формат и не содержит ubuntu24.04
            if ! grep -q "^deb" /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null || \
               grep -q "ubuntu24.04" /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null; then
                echo -e "${YELLOW}⚠️  Файл репозитория содержит неверный формат или ubuntu24.04, исправляем...${NC}"
                rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list
                ARCH=$(dpkg --print-architecture)
                cat > /etc/apt/sources.list.d/nvidia-container-toolkit.list <<EOF
deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/ubuntu22.04/${ARCH} /
EOF
                echo -e "${GREEN}✅ Список репозиториев создан (используем Ubuntu 22.04 репозиторий для совместимости)${NC}"
            else
                echo -e "${GREEN}✅ Список репозиториев получен и сохранен${NC}"
            fi
        fi
        
        # Обновление списка пакетов
        echo -e "${BLUE}   Обновление списка пакетов...${NC}"
        apt-get update -qq
        
        # Установка nvidia-container-toolkit
        echo -e "${BLUE}   Установка nvidia-container-toolkit...${NC}"
        if apt-get install -y -qq nvidia-container-toolkit > /dev/null 2>&1; then
            GPU_NEEDS_SETUP=true
            echo -e "${GREEN}✅ NVIDIA Container Toolkit установлен${NC}"
        else
            echo -e "${RED}❌ Ошибка при установке nvidia-container-toolkit${NC}"
            echo -e "${YELLOW}   Проверьте содержимое файла: /etc/apt/sources.list.d/nvidia-container-toolkit.list${NC}"
            echo -e "${YELLOW}   Убедитесь, что distribution правильный: $DISTRIBUTION${NC}"
        fi
    else
        echo -e "${GREEN}✅ NVIDIA Container Toolkit уже установлен${NC}"
        
        # Проверяем, настроен ли Docker daemon для работы с nvidia
        if [ ! -f /etc/docker/daemon.json ] || ! grep -q "nvidia" /etc/docker/daemon.json 2>/dev/null; then
            echo -e "${YELLOW}⚠️  Docker daemon не настроен для NVIDIA. Настраиваем...${NC}"
            GPU_NEEDS_SETUP=true
        fi
    fi
    
    # Настройка runtime если нужно
    if [ "$GPU_NEEDS_SETUP" = "true" ]; then
        echo -e "${BLUE}🔧 Настройка Docker для работы с NVIDIA GPU...${NC}"
        
        # Настройка runtime через nvidia-ctk
        nvidia-ctk runtime configure --runtime=docker
        
        # Проверяем и исправляем конфигурацию Docker daemon
        if [ -f /etc/docker/daemon.json ]; then
            # Создаем резервную копию
            cp /etc/docker/daemon.json /etc/docker/daemon.json.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
            
            # Проверяем, что в daemon.json есть правильная конфигурация
            if ! grep -q '"default-runtime"' /etc/docker/daemon.json 2>/dev/null; then
                # Используем Python для безопасного редактирования JSON (если доступен)
                if command -v python3 &> /dev/null; then
                    python3 << 'PYTHON_SCRIPT'
import json
import sys

try:
    with open('/etc/docker/daemon.json', 'r') as f:
        daemon_config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    daemon_config = {}

# Убеждаемся, что есть правильная конфигурация runtime
if 'runtimes' not in daemon_config:
    daemon_config['runtimes'] = {}

if 'nvidia' not in daemon_config['runtimes']:
    daemon_config['runtimes']['nvidia'] = {
        "path": "nvidia-container-runtime",
        "runtimeArgs": []
    }

# НЕ устанавливаем default-runtime автоматически, это может вызвать проблемы
# Пользователь может установить его вручную если нужно

with open('/etc/docker/daemon.json', 'w') as f:
    json.dump(daemon_config, f, indent=2)
PYTHON_SCRIPT
                else
                    # Fallback: простое добавление через sed (менее надежно)
                    if ! grep -q "nvidia" /etc/docker/daemon.json 2>/dev/null; then
                        # Это упрощенный вариант, лучше использовать nvidia-ctk
                        echo -e "${YELLOW}   Используем nvidia-ctk для настройки...${NC}"
                    fi
                fi
            fi
        fi
        
        # Перезапускаем Docker
        echo -e "${BLUE}🔄 Перезапуск Docker...${NC}"
        systemctl restart docker
        
        # Ждем немного, чтобы Docker запустился
        sleep 2
        
        # Проверяем, что Docker запустился
        if systemctl is-active --quiet docker; then
            echo -e "${GREEN}✅ Docker перезапущен${NC}"
        else
            echo -e "${RED}❌ Ошибка при перезапуске Docker${NC}"
            echo -e "${YELLOW}   Проверьте: systemctl status docker${NC}"
        fi
        
        echo -e "${GREEN}✅ Docker настроен для работы с NVIDIA GPU${NC}"
    fi
    
    # Финальная проверка конфигурации
    echo -e "${BLUE}🧪 Проверка конфигурации NVIDIA в Docker...${NC}"
    if [ -f /etc/docker/daemon.json ] && grep -q "nvidia" /etc/docker/daemon.json 2>/dev/null; then
        echo -e "${GREEN}✅ Конфигурация NVIDIA найдена в /etc/docker/daemon.json${NC}"
    else
        echo -e "${YELLOW}⚠️  Конфигурация NVIDIA не найдена в daemon.json${NC}"
        echo -e "${YELLOW}   Попробуйте выполнить вручную: nvidia-ctk runtime configure --runtime=docker${NC}"
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
if [ -f "docker-compose.yml" ] || [ -f "setup-host.sh" ]; then
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
    
    # Ждем немного, чтобы Docker точно запустился
    sleep 1
    
    # Пробуем запустить тестовый контейнер с GPU
    if docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo -e "${GREEN}✅ GPU доступна в Docker${NC}"
    else
        echo -e "${RED}❌ GPU не доступна в Docker${NC}"
        echo -e "${YELLOW}🔧 Попытка исправления...${NC}"
        
        # Проверяем конфигурацию daemon.json
        if [ ! -f /etc/docker/daemon.json ]; then
            echo -e "${YELLOW}   Создаем /etc/docker/daemon.json...${NC}"
            mkdir -p /etc/docker
            echo '{}' > /etc/docker/daemon.json
        fi
        
        # Принудительно настраиваем через nvidia-ctk
        if command -v nvidia-ctk &> /dev/null; then
            echo -e "${YELLOW}   Выполняем: nvidia-ctk runtime configure --runtime=docker${NC}"
            nvidia-ctk runtime configure --runtime=docker
            
            echo -e "${YELLOW}   Перезапускаем Docker...${NC}"
            systemctl restart docker
            sleep 3
            
            # Повторная проверка
            if docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi &> /dev/null; then
                echo -e "${GREEN}✅ GPU теперь доступна в Docker${NC}"
            else
                echo -e "${RED}❌ Проблема сохраняется${NC}"
                echo -e "${YELLOW}   Проверьте вручную:${NC}"
                echo -e "${YELLOW}   1. sudo nvidia-ctk runtime configure --runtime=docker${NC}"
                echo -e "${YELLOW}   2. sudo systemctl restart docker${NC}"
                echo -e "${YELLOW}   3. docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi${NC}"
            fi
        else
            echo -e "${RED}❌ nvidia-ctk не найден. Установите nvidia-container-toolkit${NC}"
        fi
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

