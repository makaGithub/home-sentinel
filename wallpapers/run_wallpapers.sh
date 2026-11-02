#!/bin/bash
# Тайминг фонов выступления «Страж дома» (0:00 / 0:35 / 1:00 / 2:28).
# Запуск с панели LXQt: «Слайдшоу фонов».
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
WALL_DIR="${WALL_DIR:-$DIR}"
STATE_FILE="/tmp/maka_wallpaper_idx"
PID_FILE="/tmp/maka_wallpaper_slideshow.pid"

export DISPLAY="${DISPLAY:-:0}"
if [[ -z "${XAUTHORITY:-}" && -f "${HOME}/.Xauthority" ]]; then
  export XAUTHORITY="${HOME}/.Xauthority"
fi

DAEMON_PID_FILE="/tmp/maka_wallpaper_daemon.pid"
if [[ ! -f "$DAEMON_PID_FILE" ]] || ! kill -0 "$(cat "$DAEMON_PID_FILE" 2>/dev/null || echo 0)" 2>/dev/null; then
  nohup "$HOME/.local/bin/wallpaper-daemon.py" </dev/null >/tmp/wallpaper-daemon.log 2>&1 &
fi

stop_other() {
  if [[ -f "$PID_FILE" ]]; then
    old="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${old:-}" && "$old" != "$$" ]] && kill -0 "$old" 2>/dev/null; then
      kill "$old" 2>/dev/null || true
      sleep 0.2
      kill -9 "$old" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
  local pid
  for pid in $(pgrep -f '/Pictures/wallpapers/run_wallpapers\.sh' 2>/dev/null || true); do
    if [[ "$pid" != "$$" ]]; then
      kill "$pid" 2>/dev/null || true
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
}

cleanup() {
  rm -f "$PID_FILE"
}
trap cleanup EXIT

stop_other
echo $$ > "$PID_FILE"

show_desktop() {
  if command -v wmctrl >/dev/null 2>&1; then
    wmctrl -k on >/dev/null 2>&1 && return 0
  fi
  if command -v xdotool >/dev/null 2>&1; then
    xdotool key --clearmodifiers super+d >/dev/null 2>&1 && return 0
  fi
  return 1
}

set_bg() {
  local idx="$1"
  local base="$2"
  local title="$3"
  echo "$idx" > "$STATE_FILE"
  sleep 0.12
  show_desktop || true
  notify-send -t 2000 -i preferences-desktop-wallpaper "Страж дома · Слайдшоу" "$title" \
    2>/dev/null || true
}

notify-send -t 2500 -i preferences-desktop-wallpaper "Страж дома · Слайдшоу" \
  "Старт · 0:00 → 0:35 → 1:00 → 2:28" 2>/dev/null || true

show_desktop || true

# 0:00 — Титул LIVE DEMO
set_bg 0 "bg_00_title" "1/4 · Страж дома · LIVE DEMO"
sleep 35

# 0:35 — Живое железо
set_bg 1 "bg_01_hardware" "2/4 · Железо своими руками"
sleep 25

# 1:00 — Умный дом, актуальность (3D-план)
set_bg 2 "bg_02_smart_home" "3/4 · Умный дом · актуальность"
sleep 88

# 2:28 — Финал (пёс / сценарии)
set_bg 3 "bg_03_results_final" "4/4 · Итоги и приватность"
notify-send -t 3000 -i preferences-desktop-wallpaper "Страж дома · Слайдшоу" \
  "Финал на экране · таймер завершён" 2>/dev/null || true
