#!/usr/bin/env bash
# Quick bootstrap after重启: start backend + (optionally) CosyVoice if its venv exists.
set -euo pipefail

REPO_DIR="/home/liwei/auto/auto-sales-agent"
BACKEND_DIR="$REPO_DIR/backend"
COSY_DIR="$REPO_DIR/CosyVoice"
RUN_DIR="$REPO_DIR/run"
mkdir -p "$RUN_DIR"

start_backend() {
  # stop existing uvicorn
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    pkill -f "uvicorn app.main:app" || true
    sleep 1
  fi

  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  source "$REPO_DIR/.venv/bin/activate"
  nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --timeout-keep-alive 300 \
    > "$RUN_DIR/backend.log" 2>&1 &
  echo $! > "$RUN_DIR/backend.pid"
  echo "[OK] backend started (pid $(cat "$RUN_DIR/backend.pid"))"
}

start_cosyvoice_if_present() {
  # Start CosyVoice only if its venv exists and nothing running
  if pgrep -f "CosyVoice/webui.py" >/dev/null 2>&1; then
    echo "[SKIP] CosyVoice already running."
    return
  fi
  if [ ! -x "$COSY_DIR/venv/bin/python" ]; then
    echo "[SKIP] CosyVoice venv not found at $COSY_DIR/venv; skip auto-start."
    return
  fi
  cd "$COSY_DIR"
  # shellcheck disable=SC1091
  source "$COSY_DIR/venv/bin/activate"
  MODEL_DIR="${MODEL_DIR:-$COSY_DIR/pretrained_models/CosyVoice2-0.5B}"
  nohup python runtime/python/fastapi/auto_server.py --port 9880 --model_dir "$MODEL_DIR" \
    > "$RUN_DIR/cosyvoice.log" 2>&1 &
  echo $! > "$RUN_DIR/cosyvoice.pid"
  echo "[OK] CosyVoice started (pid $(cat "$RUN_DIR/cosyvoice.pid"))"
}

start_backend
start_cosyvoice_if_present

echo "Logs: $RUN_DIR/backend.log , $RUN_DIR/cosyvoice.log (if started)"
