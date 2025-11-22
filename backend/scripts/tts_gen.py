import os
import azure.cognitiveservices.speech as speechsdk

TEXT = (
    "我需要一个产品经理助手，能帮我把用户需求转成结构化的用户故事和验收标准，"
    "语气专业亲切，偏简洁，用中文回答。如果需要可以输出 Markdown 列表。"
)

out = "/tmp/onboard_zh.wav"

key = os.getenv("AZURE_SPEECH_KEY")
region = (os.getenv("AZURE_SPEECH_REGION") or "").replace(" ", "").lower()
if not key or not region:
    raise SystemExit("Missing AZURE_SPEECH_KEY/AZURE_SPEECH_REGION")

speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
speech_config.speech_synthesis_voice_name = "zh-CN-XiaoxiaoNeural"
audio_config = speechsdk.audio.AudioConfig(filename=out)

synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
result = synthesizer.speak_text_async(TEXT).get()

if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
    details = getattr(result, "cancellation_details", None)
    raise SystemExit(f"TTS failed: {getattr(details, 'error_details', 'unknown')}")

print(out)

