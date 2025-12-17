#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT/.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PY" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install -U pip
"$VENV_DIR/bin/python" -m pip install -r "$ROOT/code/requirements.txt"

echo "OK: venv ready at $VENV_DIR"
