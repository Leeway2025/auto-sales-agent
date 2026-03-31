"""CosyVoice2 TTS Client

This module provides a client for interacting with CosyVoice2 API for text-to-speech
synthesis with voice cloning capability.
"""

import os
import httpx
import base64
import io
import wave
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


def _crop_wav_bytes(data: bytes, segment_seconds: float = 9.0) -> bytes:
    """
    Pick a mid-section (~segment_seconds) from a WAV byte stream.
    Falls back to the original data on error.
    """
    if not data or segment_seconds <= 0:
        return data
    try:
        bio = io.BytesIO(data)
        with wave.open(bio, "rb") as r:
            frame_rate = r.getframerate()
            n_channels = r.getnchannels()
            sampwidth = r.getsampwidth()
            total_frames = r.getnframes()
            seg_frames = int(segment_seconds * frame_rate)
            if total_frames <= seg_frames:
                start_frame = 0
            else:
                start_frame = max(0, (total_frames - seg_frames) // 2)
            r.setpos(start_frame)
            frames = r.readframes(seg_frames)
        if not frames:
            return data
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(n_channels)
            w.setsampwidth(sampwidth)
            w.setframerate(frame_rate)
            w.writeframes(frames)
        return out.getvalue()
    except Exception as exc:  # pragma: no cover - best effort cropping
        logger.warning(f"Failed to crop reference audio: {exc}")
        return data


class CosyVoiceClient:
    """Client for CosyVoice2 TTS API"""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize CosyVoice client
        
        Args:
            base_url: Base URL of CosyVoice2 API (default: from env or localhost:9880)
        """
        self.base_url = base_url or os.getenv("COSYVOICE_URL", "http://localhost:9880")
        self.enabled = os.getenv("COSYVOICE_ENABLED", "true").lower() == "true"
        
    async def synthesize(
        self,
        text: str,
        speaker: str = "default",
        speed: float = 1.0,
        reference_audio: Optional[bytes] = None
    ) -> bytes:
        """Synthesize speech from text
        
        Args:
            text: Text to synthesize
            speaker: Speaker ID (ignored if reference_audio provided)
            speed: Speech speed (0.5 - 2.0)
            reference_audio: Reference audio for voice cloning (WAV format, 3-10s)
            
        Returns:
            Audio data in WAV format
            
        Raises:
            httpx.HTTPError: If API request fails
        """
        if not self.enabled:
            raise RuntimeError("CosyVoice is not enabled. Set COSYVOICE_ENABLED=true in .env")
        
        trimmed_ref = _crop_wav_bytes(reference_audio) if reference_audio else None

        async with httpx.AsyncClient(timeout=30.0) as client:
            if trimmed_ref:
                # Voice cloning mode
                logger.info(f"Synthesizing with voice cloning (cropped ~9s ref): {len(text)} chars")
                
                # Encode reference audio to base64
                ref_audio_b64 = base64.b64encode(trimmed_ref).decode('utf-8')
                
                payload = {
                    "text": text,
                    "reference_audio": ref_audio_b64,
                    "speed": speed
                }
            else:
                # Preset speaker mode
                logger.info(f"Synthesizing with speaker '{speaker}': {len(text)} chars")
                
                payload = {
                    "text": text,
                    "speaker": speaker,
                    "speed": speed
                }
            
            try:
                response = await client.post(
                    f"{self.base_url}/api/inference",
                    json=payload
                )
                response.raise_for_status()
                
                logger.info(f"Synthesis successful: {len(response.content)} bytes")
                return response.content
                
            except httpx.HTTPError as e:
                logger.error(f"CosyVoice API error: {e}")
                raise
    
    async def get_speakers(self) -> List[Dict[str, str]]:
        """Get list of available preset speakers
        
        Returns:
            List of speaker info dicts with 'id' and 'name'
        """
        if not self.enabled:
            return []
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(f"{self.base_url}/api/speakers")
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    return data
                logger.error("Unexpected speakers payload type: %s", type(data).__name__)
                return []
            except httpx.HTTPError as e:
                logger.error(f"Failed to get speakers: {e}")
                return []
    
    async def health_check(self) -> bool:
        """Check if CosyVoice API is healthy
        
        Returns:
            True if API is reachable and healthy
        """
        if not self.enabled:
            return False
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
            except Exception:
                return False


# Global client instance
_client: Optional[CosyVoiceClient] = None


def get_cosyvoice_client() -> CosyVoiceClient:
    """Get or create global CosyVoice client instance"""
    global _client
    if _client is None:
        _client = CosyVoiceClient()
    return _client


# Expose crop helper for other modules
def crop_reference_audio(data: bytes, segment_seconds: float = 9.0) -> bytes:
    return _crop_wav_bytes(data, segment_seconds=segment_seconds)
