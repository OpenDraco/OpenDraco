#!/usr/bin/env bash
# Linux / macOS counterpart of ollama_cpu_only.ps1.
# Kills anything bound to Ollama's port, then re-launches `ollama serve`
# with GPU acceleration disabled.
set -euo pipefail

PORT=11434

# Find PIDs on $PORT. Prefer `lsof` (BSD/macOS + most Linux); fall back to
# `fuser` (util-linux) if lsof isn't present.
pids=""
if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti :"$PORT" 2>/dev/null || true)"
elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$PORT"/tcp 2>/dev/null | awk '{$1=$1};1' || true)"
fi

if [ -n "$pids" ]; then
    echo "Killing PIDs on port $PORT: $pids"
    # shellcheck disable=SC2086 -- intentional word-splitting on $pids
    kill -9 $pids 2>/dev/null || true
fi

# CPU-only flags. CUDA_VISIBLE_DEVICES="" hides GPUs from CUDA-aware libs;
# OLLAMA_NO_CUDA=1 is the explicit Ollama opt-out.
export CUDA_VISIBLE_DEVICES=""
export OLLAMA_NO_CUDA=1

# Start in the background; print PID so it's easy to stop.
ollama serve &
echo "Started ollama (CPU-only) in background, pid=$!"
