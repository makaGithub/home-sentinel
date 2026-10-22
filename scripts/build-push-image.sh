#!/usr/bin/env bash
# Сборка hs-gpu-helper.
# По умолчанию — тонкий слой поверх уже собранного home-sentinel:0.1.0 (быстро).
# Полная сборка с нуля: FULL_BUILD=1 ./scripts/build-push-image.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGISTRY="${REGISTRY:-harbor.iportal.ru/zhizhin}"
IMAGE_NAME="${IMAGE_NAME:-hs-gpu-helper}"
TAG="${TAG:-0.1.0}"
PLATFORM="${PLATFORM:-linux/amd64}"
FULL_BUILD="${FULL_BUILD:-0}"

PIP_INDEX_URL="${PIP_INDEX_URL:-https://devpi.iportal.ru/root/pypi/+simple/}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-devpi.iportal.ru}"

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

if [[ "${FULL_BUILD}" == "1" ]]; then
  echo "==> FULL build ${FULL_IMAGE}"
  CUDA_IMAGE_DEVEL="${CUDA_IMAGE_DEVEL:-harbor.iportal.ru/hub.docker.com/nvidia/cuda:12.3.2-devel-ubuntu22.04}"
  CUDA_IMAGE_RUNTIME="${CUDA_IMAGE_RUNTIME:-harbor.iportal.ru/hub.docker.com/nvidia/cuda:12.3.2-runtime-ubuntu22.04}"
  PKG_CACHE_UBUNTU="${PKG_CACHE_UBUNTU:-http://pkg-cache-ubuntu.iportal.ru}"
  TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu121}"
  docker buildx build \
    --platform "${PLATFORM}" \
    --build-arg "CUDA_IMAGE_DEVEL=${CUDA_IMAGE_DEVEL}" \
    --build-arg "CUDA_IMAGE_RUNTIME=${CUDA_IMAGE_RUNTIME}" \
    --build-arg "PKG_CACHE_UBUNTU=${PKG_CACHE_UBUNTU}" \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
    --build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}" \
    --build-arg "TORCH_INDEX_URL=${TORCH_INDEX_URL}" \
    --tag "${FULL_IMAGE}" \
    --tag "${REGISTRY}/${IMAGE_NAME}:latest" \
    --file "${ROOT}/code/Dockerfile" \
    --progress=plain \
    --push \
    "${ROOT}/code"
else
  BASE_IMAGE="${BASE_IMAGE:-harbor.iportal.ru/zhizhin/hs-gpu-helper:0.1.3}"
  echo "==> LAYER build ${FULL_IMAGE}"
  echo "    base: ${BASE_IMAGE}"
  echo "    (only fastapi + gpu_helper code)"
  docker buildx build \
    --platform "${PLATFORM}" \
    --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
    --build-arg "PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}" \
    --tag "${FULL_IMAGE}" \
    --tag "${REGISTRY}/${IMAGE_NAME}:latest" \
    --file "${ROOT}/code/Dockerfile.layer" \
    --progress=plain \
    --push \
    "${ROOT}/code"
fi

echo "==> Pushed ${FULL_IMAGE}"
echo "==> Pushed ${REGISTRY}/${IMAGE_NAME}:latest"
