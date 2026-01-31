#home-sentinel
Home assistant AI stack с поддержкой GPU

## Структура проекта

```
home-sentinel/
├── code/                   # Код сервиса детекции объектов и распознавания лиц
├── data/                   # Все данные отдельно от кода
│   ├── cache/              # Кэши векторных представлений
│   ├── models/             # Модели InsightFace и YOLO
│   └── .buildx-cache/      # Docker buildx кэш
├── docker-compose.yml      # Конфигурация Docker Compose
└── scripts/                # Вспомогательные скрипты
    ├── deploy.sh           # Скрипт деплоя
    └── setup-host.sh       # Скрипт настройки хоста
```

### Компоненты

- **code/** - сервис детекции объектов и распознавания лиц (YOLOv11 + InsightFace)
- **data/** - все данные (кэши, модели, конфигурации) отдельно от кода

### Реализованные функции

- ✅ Детекция объектов в реальном времени (YOLOv11)
- ✅ Распознавание лиц (InsightFace, интеграция с Immich)
- ✅ Анализ аудио потоков (YAMNet - классификация звуков)
- ✅ Статистика активности (запись в БД)
- ✅ Интеграция с Immich (использование базы лиц)
- ✅ Анти-дребезг для стабилизации детекции

## Требования

- **Локально**: Git, SSH доступ к удаленному хосту
- **Удаленный хост**: Ubuntu 24.04.3, NVIDIA GPU, Docker

## Локальное Python-окружение (опционально)

Если нужно запускать Python-код локально (без Docker), используйте venv в корне репозитория:

```bash
./scripts/venv.sh

# Запуск через короткий враппер (без "source .venv/bin/activate")
./scripts/py code/main.py
```

## Настройка и деплой на удаленный GPU хост

### Первоначальная настройка

#### 1. Настройка локального окружения

1. **Клонируйте репозиторий локально:**
   ```bash
   git clone <your-repo-url> ~/projects/home-sentinel
   cd ~/projects/home-sentinel
   ```

2. **Настройте SSH доступ к удаленному хосту:**
   ```bash
   ssh-copy-id user@your-gpu-server.com
   ```

3. **Настройте конфигурацию деплоя:**
   ```bash
   cp .env.example .env
   # Отредактируйте .env с вашими параметрами
   ```

#### 2. Настройка удаленного хоста (Ubuntu 24.04.3)

1. **Клонируйте репозиторий на удаленном хосте:**
   ```bash
   ssh user@your-gpu-server.com
   git clone <your-repo-url> /path/to/home-sentinel
   cd /path/to/home-sentinel
   ```

2. **Настройте Docker и окружение:**
   ```bash
   sudo ./scripts/setup-host.sh
   ```
   
   Скрипт автоматически:
   - Установит Docker и Docker Compose (если не установлены)
   - Настроит Docker Buildx
   - Установит и настроит NVIDIA Container Toolkit (если обнаружена GPU)
   - Добавит пользователя в группу docker

3. **Выйдите и войдите снова** (или выполните `newgrp docker`) для применения изменений группы

4. **Убедитесь, что директории созданы в `data/`**:
   ```bash
   mkdir -p data/cache data/models
   ```
   Эти директории должны создаваться только в `data/` через Docker volumes.

5. **Создайте `.env` файл на удаленном хосте** с необходимыми переменными (см. раздел "Переменные окружения")

### Workflow разработки

Проект разрабатывается локально, а запускается и тестируется на удаленном GPU хосте.

1. **Редактируйте код локально** в Visual Code IDE

2. **Деплой на удаленный хост:**
   ```bash
   ./scripts/deploy.sh
   ```
   
   Команда автоматически выполнит:
   - Синхронизацию кода (git или rsync)
   - Копирование .env файла (если настроено)
   - Сборку Docker образов на удаленном хосте
   - Перезапуск сервисов

3. **Быстрые команды:**
   ```bash
   # Только синхронизация кода
   ./scripts/deploy.sh sync
   
   # Только сборка
   ./scripts/deploy.sh build
   
   # Только перезапуск
   ./scripts/deploy.sh restart
   
   # Просмотр логов
   ./scripts/deploy.sh logs
   ./scripts/deploy.sh logs yolov8  # логи конкретного сервиса
   
   # Статус сервисов
   ./scripts/deploy.sh status
   
   # SSH подключение к хосту
   ./scripts/deploy.sh ssh
   ```

### Методы синхронизации

#### Git метод (рекомендуется для продакшена)
- Код версионируется через git
- Требует настройки git на удаленном хосте
- Более надежный и отслеживаемый

Настройка в `.env`:
```bash
DEPLOY_METHOD="git"
```

#### Rsync метод (рекомендуется для разработки)
- Быстрая синхронизация без коммитов
- Идеально для активной разработки
- Исключает файлы из .gitignore автоматически

Настройка в `.env`:
```bash
DEPLOY_METHOD="rsync"
```

## Переменные окружения

Создайте файл `.env` в корне проекта на основе `.env.example`:

```bash
cp .env.example .env
nano .env
```

Файл `.env` содержит все настройки проекта, разделенные на блоки:
- **Конфигурация приложения** (home-sentinel): VIDEO_URL, YOLO_MODEL, INSIGHTFACE_MODEL и т.д.
- **Конфигурация базы данных Immich**: IMMICH_DB_HOST, IMMICH_DB_PASSWORD и т.д.
- **Конфигурация деплоя**: REMOTE_HOST, REMOTE_USER, DEPLOY_METHOD и т.д.

**Важно:** Файл `.env` не коммитится в git (уже в `.gitignore`). Используйте `.env.example` как шаблон.

## Структура сервисов

После деплоя на удаленном хосте доступны следующие сервисы:

- **home-sentinel**: детекция объектов и распознавание лиц (YOLOv11 + InsightFace)
  - Обработка RTSP видеопотока
  - Распознавание лиц с использованием базы из Immich
  - Детекция объектов в реальном времени
  - Анализ аудио потоков (YAMNet - классификация звуков)
  - Запись статистики в PostgreSQL

## MQTT и Home Assistant

Сервис публикует в MQTT события и состояния для интеграции с Home Assistant (Discovery, сенсоры, триггеры). Идентификатор устройства задаётся в `.env` как `MQTT_DEVICE_ID` (по умолчанию `home_sentinel`).

### Тестовая отправка URL распознанного лица

Чтобы вручную отправить тестовое сообщение с URL картинки лица в топик «Последний кадр» (для проверки интеграции или отладки):

```bash
# Без авторизации (локальный брокер)
mosquitto_pub -h localhost -p 1883 -t "home_sentinel/image/latest/url" -m "https://example.com/test-face.jpg"

# С логином/паролем (подставьте значения из .env: MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD)
mosquitto_pub -h YOUR_BROKER -p 1883 -u YOUR_USER -P YOUR_PASS -t "home_sentinel/image/latest/url" -m "https://example.com/test-face.jpg"
```

Если в `.env` задан другой `MQTT_DEVICE_ID`, замените `home_sentinel` в топике на его значение. После публикации в Home Assistant обновится сущность «Последний кадр» (image) и покажет указанный URL.

Опционально можно отправить и сенсор «Последнее лицо» (имя + confidence):

```bash
mosquitto_pub -h localhost -p 1883 -t "home_sentinel/sensor/last_face" -m '{"name":"Test User","confidence":0.95,"frame":0,"timestamp":"2025-01-30T12:00:00"}'
```

## Troubleshooting

### Проблемы с деплоем

**Ошибка "Unable to locate package docker-buildx-plugin":**
- Это нормально для Ubuntu 24.04.3. Скрипт `scripts/setup-host.sh` автоматически установит buildx вручную, если пакет недоступен.

**Проблемы с SSH подключением:**
- Проверьте доступ: `ssh user@your-gpu-server.com`
- Убедитесь, что SSH ключи настроены: `ssh-copy-id user@your-gpu-server.com`

### Проблемы с Docker на удаленном хосте

**Docker требует sudo:**
- После выполнения `scripts/setup-host.sh` выйдите и войдите снова
- Или выполните: `newgrp docker`

**Проверка статуса Docker:**
```bash
ssh user@your-gpu-server.com
sudo systemctl status docker
```

### Проблемы с GPU
Убедитесь, что на удаленном хосте установлен:
- NVIDIA драйвер
- nvidia-container-toolkit
- Docker с поддержкой GPU

Проверка на удаленном хосте:
```bash
ssh user@your-gpu-server.com
docker run --rm --gpus all nvidia/cuda:12.3.2-base-ubuntu22.04 nvidia-smi
```

Если GPU не доступна в Docker:
```bash
# Проверьте установку nvidia-container-toolkit
sudo nvidia-ctk --version

# Перезапустите Docker
sudo systemctl restart docker
```

### Просмотр логов на удаленном хосте

```bash
# Через скрипт деплоя
./scripts/deploy.sh logs

# Или напрямую через SSH
ssh user@your-gpu-server.com 'cd /path/to/home-sentinel && docker compose logs -f'
```

## Структура данных

Все данные (кэши, модели, конфигурации) хранятся в директории `data/`, которая:
- Исключена из git (через .gitignore)
- Отделена от кода
- Легко бэкапится отдельно
- Не синхронизируется при деплое (если не нужно)

## Лицензия

MIT
