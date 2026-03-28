import os
import httpx
from typing import Optional

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
    Synthesize speech using Azure Speech and return raw audio bytes.
    """
    key = os.getenv("AZURE_SPEECH_KEY")
    region = _normalize_region(os.getenv("AZURE_SPEECH_REGION", ""))
    if not key or not region:
        raise RuntimeError("Missing AZURE_SPEECH_KEY or AZURE_SPEECH_REGION")

    voice = voice_name or os.getenv("AZURE_SPEECH_VOICE", "zh-CN-XiaoxiaoNeural")

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
    )

    # Disable default speaker output; we'll read the stream instead.
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=False)
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    result = synthesizer.speak_text(text)

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        stream = speechsdk.AudioDataStream(result)
        return stream.read_all()

    details = getattr(result, "cancellation_details", None)
    msg = details.error_details if details else "Speech synthesis failed"
    raise RuntimeError(msg)
