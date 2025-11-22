"""CosyVoice2 TTS Client

This module provides a client for interacting with CosyVoice2 API for text-to-speech
synthesis with voice cloning capability.
"""

import os
import httpx
import base64
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class CosyVoiceClient:
    """Client for CosyVoice2 TTS API"""
    
    def __init__(self, base_url: Optional[str] = None):
        """Initialize CosyVoice client
        
        Args:
            base_url: Base URL of CosyVoice2 API (default: from env or localhost:9880)
        """
        self.base_url = base_url or os.getenv("COSYVOICE_URL", "http://localhost:9880")
        self.enabled = os.getenv("COSYVOICE_ENABLED", "false").lower() == "true"
        
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
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            if reference_audio:
                # Voice cloning mode
                logger.info(f"Synthesizing with voice cloning: {len(text)} chars")
                
                # Encode reference audio to base64
                ref_audio_b64 = base64.b64encode(reference_audio).decode('utf-8')
                
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
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to get speakers: {e}")
                return [{"id": "default", "name": "Default"}]
    
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
