#!/bin/bash
set -e

# Auto-download model if not present and MODEL_DOWNLOAD=1
if [ "${MODEL_DOWNLOAD:-0}" = "1" ] && [ ! -d "${COSYVOICE_MODEL_DIR}" ]; then
    echo "Downloading CosyVoice2-0.5B model from ModelScope..."
    python /workspace/download_model.py
fi

if [ ! -d "${COSYVOICE_MODEL_DIR}" ]; then
    echo "ERROR: Model directory not found: ${COSYVOICE_MODEL_DIR}"
    echo "Mount a volume with the model, or set MODEL_DOWNLOAD=1 to auto-download."
    exit 1
fi

PORT=${PORT:-9880}
WORKERS=${WORKERS:-1}

echo "Starting CosyVoice2 API service on port ${PORT}..."
exec python -m uvicorn api_server:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WORKERS}"
