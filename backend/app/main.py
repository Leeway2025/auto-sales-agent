import os
import uuid
import time
import json
import base64
import logging
import re
import tempfile
from typing import Optional, Dict, Any, List
from functools import partial
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load backend/.env before importing azure clients (which read env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from .azure_clients import (
    get_aoai_client,
    transcribe_file,
    issue_speech_token,
    synthesize_speech_azure,
)
from .prompt_templates import SYSTEM_PROMPT_BUILDER_TEMPLATE_MD, INTERVIEWER_SYSTEM_PROMPT
from .cosyvoice_client import get_cosyvoice_client, crop_reference_audio


# ---------- App & CORS ----------
app = FastAPI(title="Voice-to-Agent MVP", version="0.2.0")

_cors = os.getenv("CORS_ORIGINS", "*")
allow_origins = [o.strip() for o in _cors.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = os.getenv("AZURE_OPENAI_DEPLOYMENT")
if not MODEL:
    MODEL = "__MISSING_MODEL__"

# Serve built frontend (SPA). Mount under /app to avoid shadowing /api routes when running without nginx.
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    app.mount("/app", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse("/app")
else:
    logger.warning(f"Frontend dist not found at {frontend_dist}; root will serve docs.")

    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse("/docs")


# ---------- Schemas ----------
class ChatIn(BaseModel):
    message: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    generate_audio: bool = True  # Control audio generation


class SessionStartIn(BaseModel):
    seed_transcript: Optional[str] = None
    user_id: Optional[str] = "demo-user"


class SessionMessageIn(BaseModel):
    message: str
    user_id: Optional[str] = "demo-user"


class SessionState(BaseModel):
    session_id: str
    user_id: str
    created_at: float
    fields: Dict[str, Any]
    missing: List[str]
    history: List[Dict[str, str]]
    voice_template: Optional[bytes] = None


# ---------- In-memory Stores ----------
_SESSIONS: Dict[str, SessionState] = {}
_CONVERSATION_HISTORY: Dict[str, List[Dict[str, str]]] = {}
_AGENTS_CACHE: Dict[str, Dict[str, Any]] = {} # Cache for agent details
_USER_ID_DEFAULT = "demo-user"


# ---------- Unified TTS Service ----------
async def synthesize_speech(
    text: str,
    reference_audio: Optional[bytes] = None,
    speaker: str = "default",
    speed: float = 1.0,
) -> bytes:
    """
    Prefer CosyVoice for cloning/preset voices, fallback to Azure TTS when needed.
    """
    client = get_cosyvoice_client()

    if client.enabled:
        try:
            resolved_speaker = speaker
            if reference_audio is None:
                speakers = await client.get_speakers()
                if speakers:
                    speaker_ids = [spk.get("id", "") for spk in speakers if spk.get("id")]
                    if speaker_ids and (not speaker or speaker == "default" or speaker not in speaker_ids):
                        resolved_speaker = speaker_ids[0]
                else:
                    logger.warning("CosyVoice has no preset speakers; service-side zero-shot fallback will be used.")

            return await client.synthesize(
                text=text,
                reference_audio=reference_audio,
                speaker=resolved_speaker,
                speed=speed,
            )
        except Exception as e:
            if reference_audio is not None:
                logger.error("CosyVoice clone synthesis failed: %s", e)
                raise HTTPException(status_code=502, detail=f"CosyVoice synthesis failed: {e}") from e
            logger.warning("CosyVoice synthesis failed, falling back to Azure TTS: %s", e)
    else:
        logger.warning("CosyVoice is disabled; using Azure TTS fallback.")

    try:
        return await run_in_threadpool(synthesize_speech_azure, text)
    except Exception as e:
        logger.error("Azure TTS fallback failed: %s", e)
        raise HTTPException(status_code=502, detail=f"TTS synthesis failed: {e}") from e


@app.post("/api/tts")
async def tts_endpoint(
    text: str = Form(...),
    speaker: str = Form("default"),
    speed: float = Form(1.0),
):
    try:
        audio = await synthesize_speech(text=text, speaker=speaker, speed=float(speed))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid speed value")
    return Response(content=audio, media_type="audio/wav")


@app.post("/api/tts/clone")
async def tts_clone_endpoint(
    text: str = Form(...),
    reference_audio: UploadFile = File(...),
    speed: float = Form(1.0),
):
    ref_bytes = await reference_audio.read()
    if not ref_bytes:
        raise HTTPException(status_code=400, detail="Reference audio is empty")
    try:
        audio = await synthesize_speech(text=text, reference_audio=ref_bytes, speed=float(speed))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid speed value")
    return Response(content=audio, media_type="audio/wav")


@app.get("/api/tts/speakers")
async def tts_speakers():
    client = get_cosyvoice_client()
    speakers = await client.get_speakers() if client.enabled else []
    return {"speakers": speakers}


@app.get("/api/tts/health")
async def tts_health():
    client = get_cosyvoice_client()
    healthy = await client.health_check() if client.enabled else False
    return {"healthy": healthy, "enabled": client.enabled, "url": client.base_url}


# ---------- Helpers ----------
def _ensure_model_configured():
    if MODEL == "__MISSING_MODEL__":
        raise HTTPException(status_code=500, detail="AZURE_OPENAI_DEPLOYMENT not configured")

async def get_agent_details(agent_id: str) -> Dict[str, Any]:
    """
    Retrieves agent details, using a cache to avoid repeated API calls.
    """
    if agent_id in _AGENTS_CACHE:
        return _AGENTS_CACHE[agent_id]

    _ensure_model_configured()
    aoai = get_aoai_client()
    try:
        agent = await run_in_threadpool(lambda: aoai.beta.assistants.retrieve(assistant_id=agent_id))
        details = {
            "id": agent.id,
            "instructions": getattr(agent, "instructions", ""),
            "metadata": getattr(agent, "metadata", {}),
        }
        _AGENTS_CACHE[agent_id] = details
        return details
    except Exception as e:
        logger.error(f"Failed to retrieve agent {agent_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found.")


# ---------- Core Chat Route (Streaming) ----------
@app.post("/api/agents/{agent_id}/chat/stream")
async def chat_stream(agent_id: str, body: ChatIn):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    - Streams text chunks from LLM.
    - After text is complete, generates audio and streams it.
    """
    _ensure_model_configured()
    aoai = get_aoai_client()

    thread_id = body.thread_id or str(uuid.uuid4())

    if thread_id not in _CONVERSATION_HISTORY:
        agent_details = await get_agent_details(agent_id)
        instructions = agent_details.get("instructions", "You are a helpful AI assistant.")
        _CONVERSATION_HISTORY[thread_id] = [{"role": "system", "content": instructions}]

    _CONVERSATION_HISTORY[thread_id].append({"role": "user", "content": body.message})

    async def generate():
        full_reply = ""
        try:
            # 1. Stream LLM text response
            response_stream = await run_in_threadpool(lambda: aoai.chat.completions.create(
                model=MODEL,
                messages=_CONVERSATION_HISTORY[thread_id],
                temperature=0.7,
                max_tokens=800,
                stream=True
            ))

            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    yield f"data: {json.dumps({'type': 'text', 'content': content})}\\n\n"

            _CONVERSATION_HISTORY[thread_id].append({"role": "assistant", "content": full_reply})

            # Truncate history
            if len(_CONVERSATION_HISTORY[thread_id]) > 21:
                _CONVERSATION_HISTORY[thread_id] = \
                    [_CONVERSATION_HISTORY[thread_id][0]] + _CONVERSATION_HISTORY[thread_id][-20:]

            # 2. Generate and stream audio if requested
            if body.generate_audio and full_reply:
                agent_details = await get_agent_details(agent_id)
                metadata = agent_details.get("metadata", {})
                ref_audio_b64 = metadata.get("voice_template_b64")
                ref_audio = base64.b64decode(ref_audio_b64) if ref_audio_b64 else None

                audio_data: Optional[bytes] = None
                try:
                    audio_data = await synthesize_speech(full_reply, reference_audio=ref_audio)
                except HTTPException as e:
                    logger.warning(f"TTS failed for thread {thread_id}: {e.detail}")
                except Exception as e:
                    logger.error(f"Unexpected TTS error for thread {thread_id}: {e}")

                if audio_data:
                    audio_b64 = base64.b64encode(audio_data).decode('utf-8')
                    yield f"data: {json.dumps({'type': 'audio', 'content': audio_b64})}\\n\n"

            # 3. Send final 'done' event
            yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id})}\\n\n"

        except Exception as e:
            logger.error(f"Error during chat stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


# ---------- Onboarding and Agent Management Routes (Simplified) ----------
# Note: The original onboarding logic is complex. We keep the core finalization part.
# The multi-turn conversation part is preserved but could be refactored.
@app.post("/api/upload")
async def upload_audio(file: UploadFile = File(...)):
    """
    Legacy compatibility for the onboarding page:
    - saves the uploaded audio to a temp file
    - runs Azure Speech-to-Text
    - returns the transcript
    """
    suffix = Path(file.filename or "audio").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        data = await file.read()
        tmp.write(data)
        tmp_path = tmp.name

    try:
        transcript = await run_in_threadpool(partial(transcribe_file, tmp_path))
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return {"filename": file.filename or Path(tmp_path).name, "transcript": transcript}


@app.post("/api/generate")
async def generate_agent_from_transcript(body: Dict[str, Any]):
    """
    Legacy compatibility endpoint used by the onboarding UI.
    Creates an Azure Assistant based on a single transcript.
    """
    _ensure_model_configured()
    transcript = (body or {}).get("transcript", "").strip()
    user_id = (body or {}).get("user_id") or _USER_ID_DEFAULT
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript is required")

    aoai = get_aoai_client()

    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_BUILDER_TEMPLATE_MD},
            {"role": "user", "content": transcript},
        ],
        temperature=0.3,
    ))
    prompt_md = resp.choices[0].message.content
    instructions_plain = _strip_markdown(prompt_md)

    assistant = await run_in_threadpool(lambda: aoai.beta.assistants.create(
        model=MODEL,
        name="Voice Agent",
        instructions=instructions_plain,
        metadata={"userId": user_id, "source": "legacy-generate"},
    ))

    return {"agent_id": assistant.id, "prompt": prompt_md}

def _build_profile_summary(fields: Dict[str, Any]) -> str:
    # (This function is simplified for brevity, assuming it exists as before)
    return "\n".join([f"{k}: {v}" for k, v in fields.items() if v])

def _strip_markdown(md: str) -> str:
    # (This function is simplified for brevity, assuming it exists as before)
    s = md or ""
    s = re.sub(r"```.*```", "", s, flags=re.DOTALL)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"[*_#>`-]", "", s)
    return s.strip()

@app.post("/api/onboard_session/{session_id}/finalize")
async def onboard_session_finalize(session_id: str):
    _ensure_model_configured()
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")

    aoai = get_aoai_client()
    user_summary = _build_profile_summary(state.fields)

    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_BUILDER_TEMPLATE_MD},
            {"role": "user", "content": user_summary},
        ],
        temperature=0.3,
    ))
    prompt_md = resp.choices[0].message.content
    instructions_plain = _strip_markdown(prompt_md)

    metadata = {"userId": state.user_id, "source": "mt-onboard"}
    if state.voice_template:
        metadata["voice_template_b64"] = base64.b64encode(state.voice_template).decode('utf-8')

    assistant = await run_in_threadpool(lambda: aoai.beta.assistants.create(
        model=MODEL,
        name=(state.fields.get("brand") or "Sales Agent"),
        instructions=instructions_plain,
        metadata=metadata,
    ))
    
    # Clear session after finalization
    _SESSIONS.pop(session_id, None)

    return {
        "agent_id": assistant.id,
        "prompt": prompt_md,
        "profile": state.fields,
        "has_voice_template": state.voice_template is not None,
    }

@app.get("/api/agents")
async def list_agents(user_id: Optional[str] = None):
    _ensure_model_configured()
    aoai = get_aoai_client()
    items = await run_in_threadpool(lambda: aoai.beta.assistants.list(order="desc", limit=100))
    data = []
    for a in items.data:
        metadata = getattr(a, "metadata", {}) or {}
        if user_id and metadata.get("userId") != user_id:
            continue
        
        instructions = getattr(a, "instructions", "") or ""
        description = instructions[:100] + "..." if len(instructions) > 100 else instructions
        data.append({
            "id": a.id,
            "name": getattr(a, "name", ""),
            "description": description,
            "created_at": getattr(a, "created_at", None),
            "userId": metadata.get("userId"),
        })
    return data

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    return await get_agent_details(agent_id)


@app.get("/api/speech/token")
async def speech_token():
    return await issue_speech_token()

# The multi-turn session management logic is kept for compatibility
# but can be further simplified or refactored.
# For brevity, only including the finalize endpoint and supporting functions.
# The full session logic from the original file should be here if needed.
_FIELD_ORDER = ["brand", "industry", "product", "audience", "channels", "goals", "tone", "objections", "region_lang"]

def _new_session(user_id: str, seed: Optional[str] = None) -> SessionState:
    sid = str(uuid.uuid4())
    state = SessionState(session_id=sid, user_id=user_id or _USER_ID_DEFAULT, created_at=time.time(), fields={}, missing=list(_FIELD_ORDER), history=[])
    _SESSIONS[sid] = state
    return state

@app.post("/api/onboard_session/start")
async def onboard_session_start(body: SessionStartIn):
    _ensure_model_configured()
    state = _new_session(user_id=body.user_id or "demo-user", seed=body.seed_transcript)
    # Simplified: just return the new session. The frontend will send the first message.
    return {"session": state.model_dump(), "reply": "Hello! I'm here to help you create a sales agent. What is your brand or company name?"}

@app.post("/api/onboard_session/{session_id}/message")
async def onboard_session_message(session_id: str, body: SessionMessageIn):
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    _ensure_model_configured()
    aoai = get_aoai_client()

    # Append user message to session history
    state.history.append({"role": "user", "text": body.message})

    # Build messages for LLM: system prompt + full conversation history
    messages = [{"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT}]
    for h in state.history:
        role = h["role"] if h["role"] in ("user", "assistant") else "user"
        messages.append({"role": role, "content": h["text"]})

    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=300,
    ))
    reply = resp.choices[0].message.content or ""

    state.history.append({"role": "assistant", "text": reply})

    # Extract [DONE] signal from reply
    done = "[DONE]" in reply
    clean_reply = reply.replace("[DONE]", "").strip()

    # Attempt to extract known fields from conversation via a quick LLM pass
    # This runs only when done to avoid extra latency on every turn
    if done:
        extract_messages = [
            {"role": "system", "content": (
                "Extract the following fields from the conversation as JSON. "
                "Fields: brand, industry, product, audience, channels, goals, tone, objections, region_lang. "
                "Return ONLY valid JSON with these keys. Use null for missing fields."
            )},
            {"role": "user", "content": "\n".join(
                f"{h['role']}: {h['text']}" for h in state.history
            )},
        ]
        try:
            extract_resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
                model=MODEL,
                messages=extract_messages,
                temperature=0,
                max_tokens=400,
            ))
            raw = extract_resp.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            raw = re.sub(r"```(?:json)?|```", "", raw).strip()
            extracted = json.loads(raw)
            for field in _FIELD_ORDER:
                val = extracted.get(field)
                if val and val != "null":
                    state.fields[field] = val
            state.missing = [f for f in _FIELD_ORDER if not state.fields.get(f)]
        except Exception as e:
            logger.warning(f"Field extraction failed: {e}")

    return {"session": state.model_dump(), "reply": clean_reply, "done": done}

@app.post("/api/onboard_session/{session_id}/voice_template")
async def upload_voice_template(session_id: str, audio: UploadFile = File(...)):
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    raw = await audio.read()
    state.voice_template = crop_reference_audio(raw)
    return {"success": True, "message": "Voice template uploaded."}

# Health check for monitoring
@app.get("/health")
def health_check():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# 机器人外呼 — 触发接口 & 呼叫中心 Webhook
# ═══════════════════════════════════════════════════════════════════════════

from .callcenter_client import make_call as _cc_make_call, get_recording_url
from .robot_call_engine import (
    create_session, get_session, remove_session,
    AUDIO_BASE_URL,
)


class RobotCallStartIn(BaseModel):
    phone: str
    agent_id: str
    task_id: Optional[str] = None
    crm_id: Optional[str] = None


@app.post("/api/robot_call/start")
async def robot_call_start(body: RobotCallStartIn):
    """触发对指定号码的机器人外呼。"""
    _ensure_model_configured()

    # 获取 Agent 指令和声音模板
    agent_details = await get_agent_details(body.agent_id)
    instructions = agent_details.get("instructions", "你是一名专业的销售顾问，请主动介绍产品。")
    metadata = agent_details.get("metadata", {})
    voice_template_b64 = metadata.get("voice_template_b64")

    # 向呼叫中心发起外呼
    result = await _cc_make_call(
        phone=body.phone,
        agent_id=body.agent_id,
        task_id=body.task_id,
        crm_id=body.crm_id,
    )
    call_uuid = result.get("uuid") or str(uuid.uuid4())

    # 创建对话会话
    create_session(
        call_uuid=call_uuid,
        agent_id=body.agent_id,
        agent_instructions=instructions,
        phone=body.phone,
        voice_template_b64=voice_template_b64,
    )

    logger.info("Robot call started: phone=%s agent=%s uuid=%s", body.phone, body.agent_id, call_uuid)
    return {"call_uuid": call_uuid, "phone": body.phone, "status": "calling"}


# ---------- 坐席状态回调 (Webhook) ----------
# 呼叫中心推送格式（参考文档第 10 节）:
# { "uuid": "...", "buuid": "...", "status": "ring|answer|hangup",
#   "callee": "...", "memberid": "...(agent_id)", ... }

@app.post("/api/webhook/callcenter/status")
async def webhook_callcenter_status(body: Dict[str, Any]):
    """呼叫中心坐席状态回调（ring / answer / hangup）。"""
    call_uuid = body.get("uuid") or body.get("buuid", "")
    status = body.get("status", "")
    logger.info("Webhook status: uuid=%s status=%s", call_uuid, status)

    session = get_session(call_uuid)

    if status == "answer" and session:
        # 通话接通 → 播放开场白
        opener_audio = await session.on_answered()
        if opener_audio and AUDIO_BASE_URL:
            # 将音频存到临时可访问路径（简化实现，生产可用 OSS/CDN）
            audio_filename = f"{call_uuid}_opener.wav"
            audio_path = f"/tmp/{audio_filename}"
            with open(audio_path, "wb") as f:
                f.write(opener_audio)
            audio_url = f"{AUDIO_BASE_URL}/api/robot_call/audio/{audio_filename}"
            return {"code": 0, "audio_url": audio_url}

    elif status == "hangup" and session:
        session.on_hangup()
        remove_session(call_uuid)

    return {"code": 0}


# ---------- 通话记录回调 (Webhook) ----------
# 呼叫中心推送格式（参考文档第 11 节）:
# { "id": 69100, "type": "callout", "destNumber": "...",
#   "recordFilename": "...", "downloadIp": "...", ... }

@app.post("/api/webhook/callcenter/record")
async def webhook_callcenter_record(body: Dict[str, Any]):
    """通话结束后呼叫中心推送通话记录（含录音信息）。"""
    record_id = body.get("id")
    call_uuid = body.get("uuid", "")
    record_filename = body.get("recordFilename", "")
    download_ip = body.get("downloadIp", "")
    duration = body.get("duration", 0)
    bill_sec = body.get("billsec", 0)

    logger.info(
        "Call record: id=%s uuid=%s duration=%ds billsec=%ds file=%s",
        record_id, call_uuid, duration, bill_sec, record_filename,
    )

    # 如果有录音文件，可在此触发录音分析（异步，不阻塞回调响应）
    if record_filename and download_ip:
        recording_url = f"http://{download_ip}/{record_filename}"
        logger.info("Recording available: %s", recording_url)
        # TODO: 可在此触发后处理任务（话术分析、CRM 写入等）

    return "0"   # 文档约定成功返回字符 "0"


# ---------- 收到客户说话录音片段（Webhook 或轮询） ----------
# 如果呼叫中心支持「实时录音片段推送」，用此接口：

@app.post("/api/webhook/callcenter/audio")
async def webhook_callcenter_audio(body: Dict[str, Any]):
    """收到客户单轮说话录音 URL，驱动一轮 STT→LLM→TTS。"""
    call_uuid = body.get("uuid", "")
    audio_url = body.get("audio_url", "")

    if not call_uuid or not audio_url:
        return {"code": 1, "msg": "missing uuid or audio_url"}

    session = get_session(call_uuid)
    if not session:
        logger.warning("No session for uuid=%s", call_uuid)
        return {"code": 1, "msg": "session not found"}

    reply_audio = await session.on_user_audio(audio_url)

    if reply_audio and AUDIO_BASE_URL:
        audio_filename = f"{call_uuid}_turn{session.turn}.wav"
        with open(f"/tmp/{audio_filename}", "wb") as f:
            f.write(reply_audio)
        audio_url_out = f"{AUDIO_BASE_URL}/api/robot_call/audio/{audio_filename}"
        return {"code": 0, "audio_url": audio_url_out}

    return {"code": 0}


# ---------- 临时音频文件下载（供呼叫中心拉取） ----------

@app.get("/api/robot_call/audio/{filename}")
async def serve_robot_audio(filename: str):
    """提供 TTS 生成的音频文件给呼叫中心下载播放。"""
    # 安全：只允许 uuid_*.wav 格式，防止路径穿越
    import re as _re
    if not _re.match(r'^[a-zA-Z0-9_-]+\.wav$', filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = f"/tmp/{filename}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Audio not found")
    with open(path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="audio/wav")
