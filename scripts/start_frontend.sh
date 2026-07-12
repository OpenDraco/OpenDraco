#!/usr/bin/env bash
# Linux / macOS counterpart of start_frontend.ps1.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/app"

# Self-heal: if a contributor invokes `evomas web` without running setup
# first (or just `git pull`ed and forgot), `npx ng serve` will fetch the
# wrong `ng` package from npmjs and exit with "could not determine
# executable to run". Install local deps once if node_modules is absent.
if [ ! -d "$APP_DIR/node_modules" ]; then
    echo "[start_frontend] app/node_modules missing -- running 'npm install' first"
    (cd "$APP_DIR" && npm install --no-audit --no-fund)
fi

echo "Starting EvoMas Angular frontend on http://localhost:4200"
cd "$APP_DIR"
exec npx ng serve --open
