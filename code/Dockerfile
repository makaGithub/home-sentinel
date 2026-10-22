# syntax=harbor.iportal.ru/hub.docker.com/docker/dockerfile:1.4
#
# hs-gpu-helper — GPU HTTP API для Talos + nvidia-gpu-lite-stack.
# Прокси: Harbor / DevPI / pkg-cache-ubuntu (см. scripts/build-push-image.sh).

ARG CUDA_IMAGE_DEVEL=harbor.iportal.ru/hub.docker.com/nvidia/cuda:12.3.2-devel-ubuntu22.04
ARG CUDA_IMAGE_RUNTIME=harbor.iportal.ru/hub.docker.com/nvidia/cuda:12.3.2-runtime-ubuntu22.04

##############################
# ===== STAGE 1: BUILDER =====
##############################
FROM ${CUDA_IMAGE_DEVEL} AS builder

ARG PKG_CACHE_UBUNTU=http://pkg-cache-ubuntu.iportal.ru
ARG PIP_INDEX_URL=https://devpi.iportal.ru/root/pypi/+simple/
ARG PIP_TRUSTED_HOST=devpi.iportal.ru
# Только cu121 index — иначе DevPI/PyPI отдаёт свежий torch с CUDA 13
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120

RUN set -eux; \
    find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
      -exec sed -i \
        -e "s|https\\?://archive.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
        -e "s|https\\?://security.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
        {} +; \
    apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake \
      libopenblas-dev liblapack-dev \
      python3.10 python3.10-dev python3-pip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3.10 -m pip install --no-cache-dir --upgrade pip wheel setuptools

RUN python3.10 -m pip uninstall -y numpy onnxruntime onnxruntime-gpu insightface || true

RUN python3.10 -m pip install --no-cache-dir "numpy>=1.24,<2.0"
RUN python3.10 -m pip install --no-cache-dir onnxruntime-gpu==1.19.2
RUN python3.10 -m pip install --no-cache-dir onnx==1.16.2
RUN python3.10 -m pip install --no-cache-dir \
    tqdm scikit-image prettytable easydict "albumentations>=1.4.6,<2.0" \
    "numpy>=1.24,<2.0"
RUN python3.10 -m pip install --no-cache-dir --no-deps insightface==0.7.3

# torch/vision строго с cu121 (не через DevPI — иначе CUDA 13)
RUN python3.10 -m pip install --no-cache-dir \
    --index-url "${TORCH_INDEX_URL}" \
    torch torchvision

COPY requirements-gpu.txt /tmp/requirements-gpu.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python3.10 -m pip install --no-cache-dir -r /tmp/requirements-gpu.txt \
    "numpy>=1.24,<2.0"

COPY . /app


##############################
# ===== STAGE 2: RUNTIME =====
##############################
FROM ${CUDA_IMAGE_RUNTIME}

ARG PKG_CACHE_UBUNTU=http://pkg-cache-ubuntu.iportal.ru

WORKDIR /app

# Без X11/GTK (opencv-headless) и без libpq-dev (psycopg2-binary).
RUN set -eux; \
    find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
      -exec sed -i \
        -e "s|https\\?://archive.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
        -e "s|https\\?://security.ubuntu.com|${PKG_CACHE_UBUNTU}|g" \
        {} +; \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libopenblas0 libgomp1 liblapack3 \
      python3.10 \
      fonts-dejavu-core fonts-liberation && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python3 && \
    ln -sf /usr/bin/python3.10 /usr/local/bin/python

COPY --from=builder /usr/lib/python3.10 /usr/lib/python3.10
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY --from=builder /app /app/code

RUN mkdir -p /app/tmp /app/cache /app/models /app/data/screenshots
ENV TMPDIR=/app/tmp

RUN rm -f /opt/nvidia/entrypoint.d/*.sh 2>/dev/null || true && \
    rm -f /etc/profile.d/cuda*.sh 2>/dev/null || true && \
    printf '#!/bin/bash\nexec "$@"\n' > /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

ENV PYTHONUNBUFFERED=1 \
    OPENCV_LOG_LEVEL=ERROR \
    NO_ALBUMENTATIONS_UPDATE=1 \
    YOLO_VERBOSE=False \
    NVIDIA_DISABLE_REQUIRE=1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

WORKDIR /app/code
ENV PORT=8080
EXPOSE 8080
CMD ["python3.10", "-m", "gpu_helper.server"]
