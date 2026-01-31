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

### ================================================================
###   ARGUMENTS
### ================================================================
DO_UPDATE=0
for arg in "$@"; do
    case "$arg" in
        --update|-u) DO_UPDATE=1 ;;
        --help|-h)
            echo "Использование: sudo $0 [--update]"
            echo "  --update, -u   принудительно обновить buildx, конфиги, builder и кеши"
            echo "                без флага уже установленное не переустанавливается"
            exit 0
            ;;
    esac
done

echo -e "${BLUE}🔧 Настройка хоста для Ubuntu/Debian + Docker + NVIDIA + BuildKit...${NC}"
echo ""

### ================================================================
###   ROOT CHECK
### ================================================================
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Запустите: sudo ./scripts/setup-host.sh${NC}"
    exit 1
fi

### ================================================================
###   UPDATE SYSTEM
### ================================================================
echo -e "${BLUE}📦 Обновление списка пакетов...${NC}"
apt update -qq

### ================================================================
###   DISABLE AUTOMATIC UPDATES (Ubuntu/Debian)
### ================================================================
echo -e "${BLUE}🔒 Отключение автоматических обновлений...${NC}"
# Конфиг APT: не обновлять списки и не ставить обновления по расписанию
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'APTEOF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
APT::Periodic::Download-Upgradeable-Packages "0";
APT::Periodic::AutocleanInterval "0";
APTEOF
# Сервис unattended-upgrades
systemctl disable --now unattended-upgrades 2>/dev/null || true
# Таймеры apt-daily (apt update/upgrade по расписанию)
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
systemctl mask apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true
# Останавливаем сервисы, если запущены
systemctl stop apt-daily.service apt-daily-upgrade.service 2>/dev/null || true
echo -e "${GREEN}✔ Автообновления отключены (обновляйте систему вручную)${NC}"

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

        # Универсальный репозиторий для всех версий Ubuntu/Debian
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
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
###   DOCKER SUBNETS (daemon.json + firewall)
### ================================================================
DOCKER_SUBNETS=(
    "172.17.0.0/16"
    "172.18.0.0/16"
    "172.19.0.0/16"
    "172.20.0.0/16"
)

### ================================================================
###   CONFIGURE DOCKER DAEMON + DNS + RUNTIME + ADDRESS POOLS
### ================================================================
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]] || [[ "$DO_UPDATE" = 1 ]]; then
    echo -e "${BLUE}⚙️ Настройка /etc/docker/daemon.json ...${NC}"
    # default-address-pools: те же подсети, что и в UFW DOCKER-USER
    cat >/etc/docker/daemon.json <<EOF
{
  "default-runtime": "nvidia",
  "dns": ["8.8.8.8", "1.1.1.1"],
  "default-address-pools": [
    {"base": "172.17.0.0/16", "size": 24},
    {"base": "172.18.0.0/16", "size": 24},
    {"base": "172.19.0.0/16", "size": 24},
    {"base": "172.20.0.0/16", "size": 24}
  ],
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
else
    echo -e "${GREEN}✔ daemon.json уже настроен (--update для перезаписи)${NC}"
fi

### ================================================================
###   INSTALL/UPDATE DOCKER BUILDX (LATEST VERSION)
### ================================================================
# Системный плагин из пакета Docker иногда падает с segfault (Invalid Plugins: buildx failed to fetch metadata: signal: segmentation fault).
# Всегда ставим/подменяем плагин версией с GitHub и перезаписываем системный путь.
BUILDX_PATH="/usr/local/lib/docker/cli-plugins/docker-buildx"
BUILDX_SYSTEM_PLUGIN="/usr/lib/docker/cli-plugins/docker-buildx"
mkdir -p /usr/local/lib/docker/cli-plugins

if [[ ! -x "$BUILDX_PATH" ]] || [[ "$DO_UPDATE" = 1 ]]; then
    echo -e "${BLUE}⬆ Обновление Docker Buildx...${NC}"
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) BUILDX_ARCH="amd64" ;;
        aarch64|arm64) BUILDX_ARCH="arm64" ;;
        *) BUILDX_ARCH="amd64" ;;
    esac

    LATEST=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest \
     | grep tag_name | cut -d '"' -f 4)
    if [[ -z "$LATEST" ]]; then
        LATEST="v0.14.1"
    fi

    echo -e "${BLUE}📥 Скачивание buildx $LATEST (${BUILDX_ARCH})...${NC}"
    curl -SL \
      "https://github.com/docker/buildx/releases/download/${LATEST}/buildx-${LATEST}.linux-${BUILDX_ARCH}" \
      -o "$BUILDX_PATH"
    chmod +x "$BUILDX_PATH"
    # Подменить системный плагин (из docker-ce), иначе при segfault Docker грузит сломанный бинарник
    mkdir -p "$(dirname "$BUILDX_SYSTEM_PLUGIN")"
    cp -f "$BUILDX_PATH" "$BUILDX_SYSTEM_PLUGIN"
    chmod +x "$BUILDX_SYSTEM_PLUGIN"
    if systemctl is-active --quiet docker; then
        systemctl restart docker
        sleep 2
    fi
    echo -e "${GREEN}✔ Buildx установлен/обновлён до ${LATEST}${NC}"
else
    echo -e "${GREEN}✔ Buildx уже установлен (--update для обновления)${NC}"
    # Всё равно подменяем системный плагин нашей копией (на случай обновления пакета docker-ce)
    if [[ -x "$BUILDX_PATH" ]]; then
        mkdir -p "$(dirname "$BUILDX_SYSTEM_PLUGIN")"
        cp -f "$BUILDX_PATH" "$BUILDX_SYSTEM_PLUGIN"
        chmod +x "$BUILDX_SYSTEM_PLUGIN"
    fi
fi

### ================================================================
###   CONFIGURE BUILDKITD DNS
### ================================================================
if [[ ! -f /etc/docker/buildkitd.toml ]] || [[ "$DO_UPDATE" = 1 ]]; then
    echo -e "${BLUE}🌐 Настройка BuildKit DNS...${NC}"
    cat >/etc/docker/buildkitd.toml <<EOF
[worker.oci]
  netns = "host"

[worker.oci.network]
  nameservers = ["8.8.8.8", "1.1.1.1"]
EOF
    systemctl restart docker
    sleep 2
else
    echo -e "${GREEN}✔ buildkitd.toml уже настроен (--update для перезаписи)${NC}"
fi

### ================================================================
###   RESET BUILDKIT CACHE (только при --update)
### ================================================================
if [[ "$DO_UPDATE" = 1 ]]; then
    echo -e "${BLUE}🧹 Очистка BuildKit кешей...${NC}"
    docker buildx prune -a -f >/dev/null 2>&1 || true
    rm -rf /var/lib/docker/buildkit 2>/dev/null || true
    sleep 1
fi

### ================================================================
###   CREATE NEW BUILDER "sane-builder"
### ================================================================
if ! docker buildx inspect sane-builder &>/dev/null || [[ "$DO_UPDATE" = 1 ]]; then
    echo -e "${BLUE}🏗 Создание Buildx builder sane-builder...${NC}"
    docker buildx rm sane-builder >/dev/null 2>&1 || true
    docker buildx create --name sane-builder --driver docker-container --use >/dev/null
    docker buildx inspect sane-builder --bootstrap
    echo -e "${GREEN}✔ Builder sane-builder создан${NC}"
else
    echo -e "${GREEN}✔ Builder sane-builder уже есть (--update для пересоздания)${NC}"
fi

### ================================================================
###   TEST BUILDKIT DNS
### ================================================================
echo -e "${BLUE}🧪 Проверка DNS BuildKit...${NC}"

docker buildx build --builder sane-builder --progress=plain - <<EOF
FROM alpine
RUN nslookup google.com
EOF

echo -e "${GREEN}🎉 Настройка завершена — BuildKit, DNS, Docker и NVIDIA работают.${NC}"