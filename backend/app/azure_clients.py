import os
import httpx
from typing import Optional
from xml.sax.saxutils import escape

from openai import AzureOpenAI
import azure.cognitiveservices.speech as speechsdk


# -------- Azure OpenAI (Assistants + Chat) --------
_client_singleton: Optional[AzureOpenAI] = None

def get_aoai_client() -> AzureOpenAI:
    global _client_singleton
    if _client_singleton is None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
        if not endpoint or not api_key:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY")
        _client_singleton = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
    return _client_singleton


# -------- Azure Speech (STT token & STT function) --------

def _normalize_region(region: str) -> str:
    # Azure Speech region like "australiaeast"; tolerate inputs with spaces/case
    return (region or "").replace(" ", "").lower()


async def issue_speech_token() -> dict:
    key = os.getenv("AZURE_SPEECH_KEY")
    region = _normalize_region(os.getenv("AZURE_SPEECH_REGION", ""))
    if not key or not region:
        raise RuntimeError("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")
    url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers={"Ocp-Apim-Subscription-Key": key}, timeout=10)
        r.raise_for_status()
        return {"token": r.text, "region": region, "expiresIn": 600}


def transcribe_file(path: str, locale: str = "zh-CN") -> str:
    # Note: This is a blocking call using the SDK. 
    # It should be run in a thread pool executor when called from async code.
    key = os.getenv("AZURE_SPEECH_KEY")
    region = _normalize_region(os.getenv("AZURE_SPEECH_REGION", ""))
    if not key or not region:
        raise RuntimeError("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = locale

    audio_config = speechsdk.AudioConfig(filename=path)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text or ""
    elif result.reason == speechsdk.ResultReason.NoMatch:
        return ""
    else:
        # Canceled or other
        details = getattr(result, "cancellation_details", None)
        msg = details.error_details if details else "Speech recognition failed"
        raise RuntimeError(msg)


def synthesize_speech_azure(text: str, voice_name: Optional[str] = None) -> bytes:
    """
    Synthesize speech via Azure Speech REST API and return WAV bytes.
    """
    key = os.getenv("AZURE_SPEECH_KEY")
    region = _normalize_region(os.getenv("AZURE_SPEECH_REGION", ""))
    if not key or not region:
        raise RuntimeError("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")

    if not text or not text.strip():
        raise RuntimeError("text is required")

    voice = (
        voice_name
        or os.getenv("AZURE_TTS_VOICE")
        or os.getenv("AZURE_SPEECH_VOICE")
        or "zh-CN-XiaoxiaoNeural"
    )

    token_url = f"https://{region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    tts_url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = (
        "<speak version='1.0' xml:lang='zh-CN'>"
        f"<voice name='{voice}'>{escape(text.strip())}</voice>"
        "</speak>"
    )

    with httpx.Client(timeout=20.0) as client:
        token_resp = client.post(
            token_url,
            headers={"Ocp-Apim-Subscription-Key": key},
        )
        token_resp.raise_for_status()
        token = token_resp.text

        tts_resp = client.post(
            tts_url,
            content=ssml.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
                "User-Agent": "auto-sales-agent",
            },
        )
        tts_resp.raise_for_status()
        return tts_resp.content
