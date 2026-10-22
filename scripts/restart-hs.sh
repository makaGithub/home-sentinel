#!/usr/bin/env bash
# restart home-sentinel и сразу docker logs -f
# Запуск из любой директории: restart-hs
set -euo pipefail

# Каталог compose: env → /srv/home-sentinel → рядом со скриптом (../)
if [[ -n "${HOME_SENTINEL_DIR:-}" ]]; then
  ROOT="$HOME_SENTINEL_DIR"
elif [[ -d /srv/home-sentinel ]]; then
  ROOT=/srv/home-sentinel
else
  SCRIPT_PATH="${BASH_SOURCE[0]}"
  while [[ -L "$SCRIPT_PATH" ]]; do
    SCRIPT_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || readlink "$SCRIPT_PATH")"
  done
  ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
fi

cd "$ROOT"

SINCE="$(date -u +%Y-%m-%dT%H:%M:%S)"

docker compose restart home-sentinel
exec docker logs home-sentinel -f --since "${SINCE}"
