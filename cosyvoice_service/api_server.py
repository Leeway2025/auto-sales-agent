"""CosyVoice2 API Service

Thin FastAPI wrapper around CosyVoice2 for voice cloning TTS.
Designed to run as an independent microservice on a GPU node (T4 or better).

Endpoints:
  GET  /health              -> liveness probe
  GET  /api/speakers        -> list preset speakers
  POST /api/inference       -> synthesize speech (clone or preset)
"""

import os
import io
import base64
import logging
import sys
from typing import Optional

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path setup — CosyVoice repo must be on PYTHONPATH (set in Dockerfile)
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model loading (done once at startup)
# ---------------------------------------------------------------------------
MODEL_DIR = os.getenv("COSYVOICE_MODEL_DIR", "/workspace/models/CosyVoice2-0.5B")
_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model
    logger.info(f"Loading CosyVoice2 model from {MODEL_DIR} ...")
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2
        _model = CosyVoice2(MODEL_DIR, load_jit=False, load_trt=False)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Model loaded on {device}. CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"GPU: {torch.cuda.get_device_name(0)}, "
                        f"VRAM: {torch.cuda.get_device_properties(0).total_memory // 1024**3}GB")
    except Exception as e:
        logger.error(f"Failed to load CosyVoice2 model: {e}")
        raise
    return _model


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CosyVoice2 TTS Service", version="1.0.0")

PRESET_SPEAKERS = [
    {"id": "中文女", "name": "中文女"},
    {"id": "中文男", "name": "中文男"},
    {"id": "英文女", "name": "英文女"},
    {"id": "英文男", "name": "英文男"},
]


class SynthesizeRequest(BaseModel):
    text: str
    speaker: str = "中文女"
    speed: float = 1.0
    reference_audio: Optional[str] = None  # base64-encoded WAV


@app.on_event("startup")
async def startup():
    _load_model()


@app.get("/health")
def health():
    ready = _model is not None
    return {"status": "ok" if ready else "loading", "model_loaded": ready}


@app.get("/api/speakers")
def list_speakers():
    return PRESET_SPEAKERS


@app.post("/api/inference")
async def inference(req: SynthesizeRequest):
    model = _load_model()

    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    speed = max(0.5, min(2.0, req.speed))

    try:
        if req.reference_audio:
            # Voice cloning: zero-shot inference
            ref_bytes = base64.b64decode(req.reference_audio)
            ref_buf = io.BytesIO(ref_bytes)
            ref_audio, sample_rate = sf.read(ref_buf)

            # Write to temp buffer for CosyVoice2 API
            tmp_buf = io.BytesIO()
            sf.write(tmp_buf, ref_audio, sample_rate, format="WAV")
            tmp_buf.seek(0)

            logger.info(f"Zero-shot TTS: {len(req.text)} chars, ref_audio={len(ref_bytes)}B")
            # CosyVoice2 zero_shot needs reference text; use empty string as fallback
            result_gen = model.inference_zero_shot(
                req.text, "", tmp_buf, speed=speed, stream=False
            )
        else:
            # Preset speaker
            logger.info(f"SFT TTS: {len(req.text)} chars, speaker={req.speaker}")
            result_gen = model.inference_sft(
                req.text, req.speaker, speed=speed, stream=False
            )

        # Collect all audio chunks
        audio_chunks = []
        sample_rate = 22050
        for result in result_gen:
            audio_chunks.append(result["tts_speech"].numpy().flatten())
            sample_rate = result.get("sample_rate", 22050)

        if not audio_chunks:
            raise RuntimeError("Model returned no audio data")

        import numpy as np
        audio = np.concatenate(audio_chunks)

        # Encode to WAV bytes
        out_buf = io.BytesIO()
        sf.write(out_buf, audio, sample_rate, format="WAV")
        wav_bytes = out_buf.getvalue()

        logger.info(f"Synthesis complete: {len(wav_bytes)} bytes, {len(audio)/sample_rate:.2f}s")
        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9880"))
    uvicorn.run(app, host="0.0.0.0", port=port)
