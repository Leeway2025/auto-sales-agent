#!/usr/bin/env python3
"""Smoke test for /audio-stream (demo-callcenter.py compatible mode)."""

import argparse
import asyncio
import json
import math
import time
import uuid
import wave
import audioop
from typing import Optional

import websockets


def _tone_pcm(sample_rate: int, duration_ms: int, freq: float = 440.0) -> bytes:
    total = int(sample_rate * duration_ms / 1000)
    amplitude = 10000
    out = bytearray()
    for n in range(total):
        value = int(amplitude * math.sin(2 * math.pi * freq * n / sample_rate))
        out.extend(int(value).to_bytes(2, byteorder="little", signed=True))
    return bytes(out)


def _wav_to_pcm_mono_16k_or_8k(wav_path: str, target_sample_rate: int) -> bytes:
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        src_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sample_width != 2:
        if sample_width == 1:
            frames = audioop.bias(frames, 1, -128)
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2

    if channels > 1:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1

    if src_rate != target_sample_rate:
        frames, _ = audioop.ratecv(
            frames, sample_width, channels, src_rate, target_sample_rate, None
        )
    return frames


async def _send_pcm_frames(
    ws,
    pcm: bytes,
    sample_rate: int,
    frame_ms: int,
) -> None:
    frame_bytes = int(sample_rate * 2 * frame_ms / 1000)
    frame_bytes = max(frame_bytes, 320)  # 20ms@8k mono 16bit
    for i in range(0, len(pcm), frame_bytes):
        await ws.send(pcm[i:i + frame_bytes])
        await asyncio.sleep(frame_ms / 1000.0)


def _safe_json(text: str) -> Optional[dict]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def run(args: argparse.Namespace) -> None:
    async with websockets.connect(args.url, max_size=20 * 1024 * 1024) as ws:
        first = await asyncio.wait_for(ws.recv(), timeout=5)
        print("[recv]", first)

        metadata = {
            "uuid": args.call_uuid or f"smoke-{uuid.uuid4().hex[:10]}",
            "memberid": args.agent_id or "",
            "sample_rate": args.sample_rate,
            "mix_type": "mono",
        }
        await ws.send(json.dumps(metadata, ensure_ascii=False))
        ack = await asyncio.wait_for(ws.recv(), timeout=5)
        print("[recv]", ack)

        if args.wav:
            pcm = _wav_to_pcm_mono_16k_or_8k(args.wav, args.sample_rate)
        else:
            pcm = _tone_pcm(args.sample_rate, args.duration_ms, freq=660.0)

        await _send_pcm_frames(ws, pcm, args.sample_rate, args.frame_ms)
        await ws.send(json.dumps({"event": "flush"}, ensure_ascii=False))

        deadline = time.time() + args.listen_seconds
        got_stream_audio = False
        while time.time() < deadline:
            timeout = max(0.1, min(1.0, deadline - time.time()))
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                continue

            if isinstance(msg, bytes):
                print(f"[recv-binary] bytes={len(msg)}")
                continue

            payload = _safe_json(msg)
            if not payload:
                print("[recv-text]", msg[:300])
                continue

            if payload.get("type") == "streamAudio":
                data = payload.get("data", {}) or {}
                audio_b64 = data.get("audioData", "")
                print(
                    "[streamAudio]",
                    f"sampleRate={data.get('sampleRate')}",
                    f"audioDataBase64Len={len(audio_b64)}",
                )
                got_stream_audio = True
            else:
                print("[event]", json.dumps(payload, ensure_ascii=False))

        if got_stream_audio:
            print("RESULT: success (received streamAudio)")
        else:
            print("RESULT: no streamAudio in time window (check STT/LLM/TTS credentials)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test /audio-stream")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/audio-stream")
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--call-uuid", default="")
    parser.add_argument("--sample-rate", type=int, choices=[8000, 16000], default=8000)
    parser.add_argument("--wav", default="", help="Optional wav input instead of generated tone")
    parser.add_argument("--duration-ms", type=int, default=800)
    parser.add_argument("--frame-ms", type=int, default=20)
    parser.add_argument("--listen-seconds", type=int, default=18)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
