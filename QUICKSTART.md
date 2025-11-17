# Быстрый старт

## Первоначальная настройка (один раз)

### 1. На удаленном GPU хосте

```bash
# Клонируйте репозиторий
git clone <your-repo-url> /path/to/ha-ai-stack
cd /path/to/ha-ai-stack

# Настройте Docker
./setup-host.sh

# Создайте .env файл
cp .env.example .env  # или создайте вручную
nano .env
```

### 2. На локальном Mac

```bash
# Клонируйте репозиторий
git clone <your-repo-url> ~/projects/ha-ai-stack
cd ~/projects/ha-ai-stack

# Настройте конфигурацию
cp .env.example .env
nano .env  # укажите параметры приложения и удаленного хоста

# Настройте SSH ключи (если еще не настроено)
ssh-copy-id user@your-gpu-server.com
```

## Ежедневный workflow

### 1. Редактируйте код локально в Cursor IDE

### 2. Деплой на удаленный хост

```bash
./deploy.sh
```

Это автоматически:
- Синхронизирует код
- Соберет Docker образы
- Перезапустит сервисы

### 3. Просмотр логов

```bash
./deploy.sh logs          # все логи
./deploy.sh logs yolov8   # логи конкретного сервиса
```

## Полезные команды

```bash
# Только синхронизация (без сборки и перезапуска)
./deploy.sh sync

# Только сборка
./deploy.sh build

# Только перезапуск
./deploy.sh restart

# Статус сервисов
./deploy.sh status

# SSH подключение к хосту
./deploy.sh ssh
```

## Настройка .env

Минимальная конфигурация для деплоя:

```bash
# Конфигурация деплоя
REMOTE_HOST="your-gpu-server.com"
REMOTE_USER="user"
REMOTE_PATH="/path/to/ha-ai-stack"
DEPLOY_METHOD="rsync"  # или "git"

# Конфигурация базы данных
IMMICH_DB_HOST="immich_postgres"
IMMICH_DB_PASSWORD="your_password"
BUILD_REMOTE="true"
RESTART_SERVICES="true"
```

## Troubleshooting

### Проблемы с SSH
```bash
# Проверьте подключение
ssh user@your-gpu-server.com

# Если нужен другой порт или ключ
# В .env добавьте:
SSH_OPTS="-i ~/.ssh/id_rsa -p 2222"
```

### Проблемы с синхронизацией
- Для быстрой разработки используйте `DEPLOY_METHOD="rsync"`
- Для продакшена используйте `DEPLOY_METHOD="git"`

### Проблемы с Docker на удаленном хосте
```bash
# Зайдите на хост и проверьте
ssh user@your-gpu-server.com
cd /path/to/ha-ai-stack
docker compose ps
docker compose logs
```

