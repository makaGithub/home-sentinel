# syntax=docker/dockerfile:1.4

##############################
# ===== STAGE 1: BUILDER =====
##############################
FROM nvidia/cuda:12.3.2-devel-ubuntu22.04 AS builder

# --- 1. Python и системные зависимости ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git wget curl \
    libboost-all-dev libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev libpq-dev \
    python3.10 python3.10-dev python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- 2. Обновляем pip и колёса ---
RUN python3.10 -m pip install --no-cache-dir --upgrade pip wheel setuptools

# --- 3. Устанавливаем стабильные версии для GPU-инференса ---
# удаляем всё лишнее, чтобы избежать конфликтов
RUN python3.10 -m pip uninstall -y numpy onnxruntime onnxruntime-gpu insightface || true

# Ставим NumPy <2.0 (совместимо с ORT и Torch)
RUN python3.10 -m pip install --no-cache-dir "numpy>=1.24,<2.0"

# GPU-runtime под CUDA 12.3
RUN python3.10 -m pip install --no-cache-dir onnxruntime-gpu==1.19.2

# ONNX и зависимости InsightFace
RUN python3.10 -m pip install --no-cache-dir onnx==1.16.2
RUN python3.10 -m pip install --no-cache-dir \
    tqdm scikit-image prettytable easydict "albumentations>=1.4.6,<2.0"

# Ставим InsightFace без зависимостей (чтобы не перетянул CPU-ORT)
RUN python3.10 -m pip install --no-cache-dir --no-deps insightface==0.7.3

# PyTorch с CUDA 12.1 (совместимо с CUDA 12.3 runtime)
RUN python3.10 -m pip install --no-cache-dir \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121



# --- 4. Остальные зависимости из requirements.txt ---
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3.10 -m pip install --no-cache-dir -r /tmp/requirements.txt

# --- 5. Копируем исходный код ---
COPY . /app


##############################
# ===== STAGE 2: RUNTIME =====
##############################
FROM nvidia/cuda:12.3.2-runtime-ubuntu22.04

WORKDIR /app

# --- 1. Минимальные системные зависимости ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev libpq-dev \
    python3.10 python3-pip \
    fonts-dejavu-core fonts-liberation && \
    rm -rf /var/lib/apt/lists/*

# --- 2. Копируем окружение и приложение ---
COPY --from=builder /usr/lib/python3.10 /usr/lib/python3.10
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
# Копируем код в /app/code (будет перекрыт volume mount при запуске)
COPY --from=builder /app /app/code

# --- 3. Подготавливаем директории ---
# НЕ создаем /app/cache и /app/models здесь - они должны быть смонтированы через volumes
# Если они созданы в образе, они перекрывают volume mounts
RUN mkdir -p /app/tmp
ENV TMPDIR=/app/tmp

# --- 4. Переменные окружения ---
ENV PYTHONUNBUFFERED=1 \
    OPENCV_LOG_LEVEL=ERROR \
    NO_ALBUMENTATIONS_UPDATE=1 \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

# --- 5. Команда запуска ---
# WORKDIR будет установлен в /app/code через docker-compose.yml
CMD ["python3.10", "main.py"]

