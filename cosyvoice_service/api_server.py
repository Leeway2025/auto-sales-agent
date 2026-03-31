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
import tempfile
from typing import Optional, List, Dict

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
FALLBACK_PROMPT_AUDIO = os.getenv("COSYVOICE_FALLBACK_PROMPT_AUDIO", "/workspace/CosyVoice/asset/zero_shot_prompt.wav")
FALLBACK_PROMPT_TEXT = os.getenv("COSYVOICE_FALLBACK_PROMPT_TEXT", "希望你以后能够做的比我还好呦。")
_model = None
_preset_speakers: List[Dict[str, str]] = []


def _load_preset_speakers(model) -> None:
    """Extract model-native speaker IDs that are valid for inference_sft."""
    global _preset_speakers
    try:
        speaker_ids = list(model.list_available_spks())
    except Exception:
        speaker_ids = list(getattr(getattr(model, "frontend", None), "spk2info", {}).keys())

    _preset_speakers = [{"id": str(spk_id), "name": str(spk_id)} for spk_id in speaker_ids if str(spk_id)]
    if _preset_speakers:
        preview = ", ".join(spk["id"] for spk in _preset_speakers[:8])
        logger.info(f"Loaded {len(_preset_speakers)} preset speakers: {preview}")
    else:
        logger.warning("No preset speakers found in model. Preset TTS requires speaker embeddings (spk2info.pt).")


def _load_model():
    global _model
    if _model is not None:
        return _model
    logger.info(f"Loading CosyVoice2 model from {MODEL_DIR} ...")
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2
        _model = CosyVoice2(MODEL_DIR, load_jit=False, load_trt=False)
        _load_preset_speakers(_model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Model loaded on {device}. CUDA: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"GPU: {torch.cuda.get_device_name(0)}, "
                        f"VRAM: {torch.cuda.get_device_properties(0).total_memory // 1024**3}GB")
    except Exception as e:
        logger.error(f"Failed to load CosyVoice2 model: {e}")
        raise
    return _model


def _fallback_prompt_available() -> bool:
    return os.path.exists(FALLBACK_PROMPT_AUDIO)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="CosyVoice2 TTS Service", version="1.0.0")


class SynthesizeRequest(BaseModel):
    text: str
    speaker: str = "default"
    speed: float = 1.0
    reference_audio: Optional[str] = None  # base64-encoded WAV


@app.on_event("startup")
async def startup():
    _load_model()


@app.get("/health")
def health():
    ready = _model is not None
    return {
        "status": "ok" if ready else "loading",
        "model_loaded": ready,
        "preset_speaker_count": len(_preset_speakers),
        "fallback_prompt_available": _fallback_prompt_available(),
    }


@app.get("/api/speakers")
def list_speakers():
    return _preset_speakers


@app.post("/api/inference")
async def inference(req: SynthesizeRequest):
    model = _load_model()

    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    speed = max(0.5, min(2.0, req.speed))
    tmp_ref_path: Optional[str] = None

    try:
        if req.reference_audio:
            # Voice cloning: zero-shot inference
            ref_bytes = base64.b64decode(req.reference_audio)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_ref:
                tmp_ref.write(ref_bytes)
                tmp_ref_path = tmp_ref.name

            logger.info(f"Zero-shot TTS: {len(req.text)} chars, ref_audio={len(ref_bytes)}B")
            # CosyVoice2 zero_shot needs reference text; use empty string as fallback
            result_gen = model.inference_zero_shot(
                req.text, "", tmp_ref_path, speed=speed, stream=False
            )
        else:
            # Preset speaker
            speaker_ids = [spk["id"] for spk in _preset_speakers]
            if not speaker_ids:
                if not _fallback_prompt_available():
                    raise HTTPException(
                        status_code=400,
                        detail="No preset speakers available and fallback prompt audio is missing.",
                    )
                logger.info("No preset speakers available; using built-in zero-shot fallback prompt.")
                result_gen = model.inference_zero_shot(
                    req.text,
                    FALLBACK_PROMPT_TEXT,
                    FALLBACK_PROMPT_AUDIO,
                    speed=speed,
                    stream=False,
                )
            else:
                selected_speaker = (req.speaker or "default").strip()
                if selected_speaker == "default" or selected_speaker not in speaker_ids:
                    selected_speaker = speaker_ids[0]

                logger.info(f"SFT TTS: {len(req.text)} chars, speaker={selected_speaker}")
                result_gen = model.inference_sft(
                    req.text, selected_speaker, speed=speed, stream=False
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
    finally:
        if tmp_ref_path and os.path.exists(tmp_ref_path):
            try:
                os.remove(tmp_ref_path)
            except OSError:
                pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9880"))
    uvicorn.run(app, host="0.0.0.0", port=port)
