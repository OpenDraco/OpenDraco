#!/usr/bin/env bash
# Linux / macOS counterpart of start_api.ps1.
# `$PSScriptRoot` becomes this script's dir; the repo root is one up.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/api/.env"
API_HOST="0.0.0.0"
API_PORT="8000"

# Parse api/.env for API_HOST / API_PORT (skip blanks and comments).
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        trim="${line#"${line%%[![:space:]]*}"}"
        trim="${trim%"${trim##*[![:space:]]}"}"
        [ -z "$trim" ] && continue
        case "$trim" in \#*) continue ;; esac
        key="${trim%%=*}"
        val="${trim#*=}"
        key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
        val="${val#"${val%%[![:space:]]*}"}"; val="${val%"${val##*[![:space:]]}"}"
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        case "$key" in
            API_HOST) API_HOST="$val" ;;
            API_PORT) API_PORT="$val" ;;
        esac
    done < "$ENV_FILE"
fi

# Venv installed by install.sh to `~/.evomas-venv` (in the user's home so
# the repo stays free of build artefacts).
VENV_DIR="$HOME/.evomas-venv"
UVICORN="$VENV_DIR/bin/uvicorn"
if [ ! -x "$UVICORN" ]; then
    echo "[start_api] uvicorn not found at $UVICORN -- run ./install.sh first." >&2
    exit 1
fi
echo "Starting EvoMas API server on http://${API_HOST}:${API_PORT}"
# --app-dir points at the repo root (not api/) so `from api import common`
# inside api/server.py finds the `api` package on sys.path.
exec "$UVICORN" --app-dir "$REPO_ROOT" api.server:app \
    --host "$API_HOST" --port "$API_PORT" --reload
