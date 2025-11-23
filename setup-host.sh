#!/bin/bash
set -e

### ================================================================
###   COLORS
### ================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🔧 Настройка хоста для Ubuntu 24.04 + Docker + NVIDIA + BuildKit...${NC}"
echo ""

### ================================================================
###   ROOT CHECK
### ================================================================
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Запустите: sudo ./setup-host.sh${NC}"
    exit 1
fi

### ================================================================
###   UPDATE SYSTEM
### ================================================================
echo -e "${BLUE}📦 Обновление списка пакетов...${NC}"
apt update -qq

### ================================================================
###   INSTALL REQUIRED PACKAGES
### ================================================================
apt install -y -qq \
    ca-certificates curl gnupg lsb-release git pciutils jq > /dev/null

### ================================================================
###   INSTALL DOCKER
### ================================================================
if ! command -v docker &>/dev/null; then
    echo -e "${BLUE}🐳 Установка Docker (официальный репо)...${NC}"

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) \
      signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list

    apt update -qq
    apt install -y -qq \
        docker-ce docker-ce-cli containerd.io docker-compose-plugin

else
    echo -e "${GREEN}✔ Docker уже установлен${NC}"
fi

### ================================================================
###   INSTALL NVIDIA DRIVERS (IF GPU)
### ================================================================
if lspci | grep -i nvidia >/dev/null; then
    echo -e "${BLUE}🎮 Найдена NVIDIA GPU${NC}"

    if ! command -v nvidia-smi >/dev/null; then
        echo -e "${YELLOW}📦 Установка NVIDIA драйвера...${NC}"
        apt install -y ubuntu-drivers-common
        ubuntu-drivers autoinstall
        echo -e "${YELLOW}Перезагрузите систему и запустите скрипт снова.${NC}"
        exit 0
    fi

    echo -e "${GREEN}✔ NVIDIA драйвер работает${NC}"

    ### NVIDIA container toolkit
    if ! command -v nvidia-ctk >/dev/null; then
        echo -e "${BLUE}📦 Установка nvidia-container-toolkit...${NC}"

        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

        ARCH=$(dpkg --print-architecture)

        echo "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] \
https://nvidia.github.io/libnvidia-container/stable/ubuntu22.04/${ARCH} /" \
            > /etc/apt/sources.list.d/nvidia-container-toolkit.list

        apt update -qq
        apt install -y -qq nvidia-container-toolkit

        nvidia-ctk runtime configure --runtime=docker
        systemctl restart docker
        sleep 2
    fi

    echo -e "${GREEN}✔ NVIDIA Container Toolkit готов${NC}"
else
    echo -e "${YELLOW}⚠ NVIDIA GPU не обнаружена${NC}"
fi

### ================================================================
###   CONFIGURE DOCKER DAEMON + DNS + RUNTIME
### ================================================================
echo -e "${BLUE}⚙️ Настройка /etc/docker/daemon.json ...${NC}"

mkdir -p /etc/docker

cat >/etc/docker/daemon.json <<EOF
{
  "default-runtime": "nvidia",
  "dns": ["8.8.8.8", "1.1.1.1"],
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  },
  "features": {
    "buildkit": true
  }
}
EOF

systemctl restart docker
sleep 2

### ================================================================
###   INSTALL/UPDATE DOCKER BUILDX (LATEST VERSION)
### ================================================================
echo -e "${BLUE}⬆ Обновление Docker Buildx...${NC}"

sudo mkdir -p /usr/local/lib/docker/cli-plugins

ARCH=$(uname -m)
case "$ARCH" in
    x86_64) BUILDX_ARCH="amd64" ;;
    aarch64|arm64) BUILDX_ARCH="arm64" ;;
    *) BUILDX_ARCH="amd64" ;;
esac

LATEST=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest \
 | grep tag_name | cut -d '"' -f 4)

if [ -z "$LATEST" ]; then
    LATEST="v0.14.1"
fi

echo -e "${BLUE}📥 Скачивание buildx $LATEST (${BUILDX_ARCH})...${NC}"

curl -SL \
  https://github.com/docker/buildx/releases/download/${LATEST}/buildx-${LATEST}.linux-${BUILDX_ARCH} \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx

chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

echo -e "${GREEN}✔ Buildx обновлён до ${LATEST}${NC}"

### ================================================================
###   CONFIGURE BUILDKITD DNS
### ================================================================
echo -e "${BLUE}🌐 Настройка BuildKit DNS...${NC}"

cat >/etc/docker/buildkitd.toml <<EOF
[worker.oci]
  netns = "host"

[worker.oci.network]
  nameservers = ["8.8.8.8", "1.1.1.1"]
EOF

systemctl restart docker
sleep 2

### ================================================================
###   RESET BUILDKIT CACHE
### ================================================================
echo -e "${BLUE}🧹 Очистка BuildKit кешей...${NC}"

docker buildx prune -a -f >/dev/null 2>&1 || true
rm -rf /var/lib/docker/buildkit 2>/dev/null || true
sleep 1

### ================================================================
###   CREATE NEW BUILDER "sane-builder"
### ================================================================
echo -e "${BLUE}🏗 Создание нового Buildx builder sane-builder...${NC}"

docker buildx rm sane-builder >/dev/null 2>&1 || true

docker buildx create \
    --name sane-builder \
    --driver docker-container \
    --use >/dev/null

docker buildx inspect sane-builder --bootstrap

echo -e "${GREEN}✔ Builder sane-builder создан${NC}"

### ================================================================
###   TEST BUILDKIT DNS
### ================================================================
echo -e "${BLUE}🧪 Проверка DNS BuildKit...${NC}"

docker buildx build --builder sane-builder --progress=plain - <<EOF
FROM alpine
RUN nslookup google.com
EOF

echo -e "${GREEN}🎉 Настройка завершена — BuildKit, DNS, Docker и NVIDIA работают.${NC}"