# CosyVoice2 TTS Service — T4 GPU Optimised
#
# Build:
#   docker build -t cosyvoice2-service:latest ./cosyvoice_service
#
# Run (requires nvidia-container-toolkit):
#   docker run --gpus '"device=0"' -p 9880:9880 \
#     -v /data/models:/workspace/models \
#     cosyvoice2-service:latest
#
# The model directory (CosyVoice2-0.5B) must be pre-downloaded to
# /data/models/CosyVoice2-0.5B on the host (or use MODEL_DOWNLOAD=1 env
# to auto-download from ModelScope at first start).

# ── Base: CUDA 12.1 + cuDNN 8 on Ubuntu 22.04 (matches T4 driver minimum) ──
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8

# ── System packages ─────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip python3.10-venv \
    git git-lfs \
    ffmpeg sox libsox-dev \
    build-essential cmake \
    curl wget ca-certificates \
    libsndfile1 \
    && git lfs install \
    && rm -rf /var/lib/apt/lists/*

# Make python3.10 the default python
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1 \
    && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

WORKDIR /workspace

# ── Clone CosyVoice2 (including submodules) ─────────────────────────────────
RUN git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git

# ── Python dependencies ──────────────────────────────────────────────────────
# Install PyTorch for CUDA 12.1 first (pinned for T4 compatibility)
RUN pip install --no-cache-dir \
    torch==2.2.2+cu121 \
    torchaudio==2.2.2+cu121 \
    --extra-index-url https://download.pytorch.org/whl/cu121

# Install CosyVoice requirements.
# Skip TensorRT and DeepSpeed to avoid build-time CUDA toolchain (nvcc) dependency
# in runtime images; they are not required for this inference service path.
RUN cd CosyVoice && \
    grep -Ev "tensorrt|deepspeed" requirements.txt > requirements_notrt.txt && \
    pip install --no-cache-dir -r requirements_notrt.txt \
        --extra-index-url https://download.pytorch.org/whl/cu121

# Install our API server dependencies
RUN pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.30.6 \
    soundfile==0.12.1 \
    numpy \
    pydantic==2.7.0 \
    modelscope==1.20.0

# ── PYTHONPATH: expose CosyVoice packages ───────────────────────────────────
ENV PYTHONPATH="/workspace/CosyVoice:/workspace/CosyVoice/third_party/Matcha-TTS:${PYTHONPATH}"

# ── Model directory (mount a host volume here) ──────────────────────────────
ENV COSYVOICE_MODEL_DIR=/workspace/models/CosyVoice2-0.5B

# ── Copy our API server ──────────────────────────────────────────────────────
COPY api_server.py /workspace/api_server.py

# ── Model download helper (runs only when MODEL_DOWNLOAD=1) ─────────────────
COPY download_model.py /workspace/download_model.py

# ── T4 GPU tuning: limit memory fragmentation, use TF32 ─────────────────────
ENV PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512 \
    TORCH_BACKENDS_CUDNN_BENCHMARK=1

EXPOSE 9880

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:9880/health || exit 1

# ── Entrypoint ───────────────────────────────────────────────────────────────
COPY entrypoint.sh /workspace/entrypoint.sh
RUN chmod +x /workspace/entrypoint.sh
CMD ["/workspace/entrypoint.sh"]
