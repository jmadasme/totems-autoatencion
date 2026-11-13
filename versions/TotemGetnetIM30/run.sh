#!/usr/bin/env bash
# Arranque del tótem de autoatención TotemGetnetIM30.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
  echo "Creando entorno virtual..."
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
fi

# Carga .env si existe
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8000}"
MODE="${GETNET_MODE:-simulation}"

echo "Iniciando tótem Getnet IM30 en http://${HOST}:${PORT} (modo=${MODE})"
exec .venv/bin/uvicorn app:app --host "$HOST" --port "$PORT"
