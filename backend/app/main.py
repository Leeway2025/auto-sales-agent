import os
import asyncio
import tempfile
import httpx
import json
from typing import Optional, Dict, Any, List
from functools import partial

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Load backend/.env before importing azure clients (which read env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from .azure_clients import get_aoai_client, transcribe_file, issue_speech_token
from .prompt_templates import SYSTEM_PROMPT_BUILDER_TEMPLATE_MD, INTERVIEWER_SYSTEM_PROMPT
from .cosyvoice_client import get_cosyvoice_client
import re


# ---------- App & CORS ----------
app = FastAPI(title="Voice-to-Agent MVP", version="0.1.0")

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
    # Allow startup; endpoints will raise if used without config
    MODEL = "__MISSING_MODEL__"


# ---------- Schemas ----------
class ChatIn(BaseModel):
    message: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None  # Add thread_id for context


class OnboardTextIn(BaseModel):
    transcript: str
    user_id: Optional[str] = "demo-user"
    language_hint: Optional[str] = "zh-CN"


# ---------- Multi-turn Onboarding (sessions) ----------
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
    voice_template: Optional[bytes] = None  # Reference audio for voice cloning


_SESSIONS: Dict[str, SessionState] = {}

# ---------- Conversation History (for fast chat) ----------
# Store conversation history in memory: {thread_id: [{role, content}, ...]}
_CONVERSATION_HISTORY: Dict[str, List[Dict[str, str]]] = {}

_FIELD_ORDER = [
    "brand",        # 品牌
    "industry",     # 行业/领域
    "product",      # 产品/服务简述
    "audience",     # 目标受众
    "channels",     # 渠道: 电话/短信/两者
    "goals",        # 销售目标/转化动作
    "tone",         # 语气/风格
    "objections",   # 常见异议
    "region_lang",  # 区域/语言
]


def _new_session(user_id: str, seed: Optional[str] = None) -> SessionState:
    import uuid
    import time
    sid = str(uuid.uuid4())
    state = SessionState(
        session_id=sid,
        user_id=user_id or "demo-user",
        created_at=time.time(),
        fields={
            "brand": None,
            "industry": None,
            "product": None,
            "audience": None,
            "channels": None,  # one of: 电话/短信/两者
            "goals": None,
            "tone": None,
            "objections": None,
            "region_lang": None,
        },
        missing=list(_FIELD_ORDER),
        history=[],
    )
    if seed:
        # Try extract once with seed to prefill
        extracted = _extract_fields(seed)
        _apply_extracted(state, extracted)
        state.history.append({"role": "user", "text": seed})
    _SESSIONS[sid] = state
    return state


def _apply_extracted(state: SessionState, extracted: Dict[str, Any]):
    for k, v in (extracted or {}).items():
        if k in state.fields and v:
            state.fields[k] = v
    state.missing = [k for k in _FIELD_ORDER if not state.fields.get(k)]


def _next_question(missing_key: str) -> str:
    q = {
        "brand": "请告诉我你的品牌名称或公司名。",
        "industry": "你主要面向哪个行业或领域？",
        "product": "请用一句话描述你的产品或服务的核心价值。",
        "audience": "你的目标受众是谁？例如中小电商、上班族或其他。",
        "channels": "你期望通过电话、短信，还是两者都使用进行触达？",
        "goals": "你更希望推动的下一步动作是什么？如购买、试用、预约或索取资料。",
        "tone": "你希望对话的语气与风格如何？如自然亲切、专业克制等。",
        "objections": "用户常见的顾虑或异议有哪些？",
        "region_lang": "是否有区域或语言偏好？例如中国大陆/中文，或其他。",
    }
    return q.get(missing_key, "还有其他要补充的信息吗？")


def _extract_fields(text: str) -> Dict[str, Any]:
    """Use LLM to extract fields into a strict JSON schema."""
    aoai = get_aoai_client()
    schema = (
        "请从用户提供的信息中抽取以下字段，输出 JSON：\n"
        "brand(品牌,字符串), industry(行业,字符串), product(产品/服务一句话,字符串), audience(目标受众,字符串),\n"
        "channels(渠道,仅可为'电话'/'短信'/'两者'), goals(下一步动作,字符串), tone(语气风格,字符串),\n"
        "objections(常见异议,字符串或逗号分隔), region_lang(区域与语言,字符串)。\n"
        "若缺失请填 null。只输出 JSON，不要额外解释。"
    )
    try:
        resp = aoai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": schema},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        # Best effort JSON parse
        import json
        obj = json.loads(content)
        # Normalize channels
        ch = obj.get("channels")
        if isinstance(ch, str):
            ch = ch.strip()
            if "短信" in ch and "电" in ch:
                obj["channels"] = "两者"
            elif "短信" in ch:
                obj["channels"] = "短信"
            elif "电" in ch or "电话" in ch:
                obj["channels"] = "电话"
        return obj
    except Exception:
        return {}


def _build_profile_summary(fields: Dict[str, Any]) -> str:
    def val(k):
        return (fields.get(k) or "").strip()
    brand = val("brand") or "品牌"
    industry = val("industry") or "通用SaaS"
    product = val("product") or "一款面向潜在客户的产品/服务"
    audience = val("audience") or "潜在客户"
    channels = val("channels") or "两者"
    goals = val("goals") or "试用或预约"
    tone = val("tone") or "自然亲切、专业、以人为本"
    objections = val("objections") or "价格、效果、实施成本"
    region_lang = val("region_lang") or "中国大陆/中文"

    lines = [
        f"品牌：{brand}",
        f"行业：{industry}",
        f"产品：{product}",
        f"受众：{audience}",
        f"渠道：{channels}",
        f"目标：{goals}",
        f"语气：{tone}",
        f"异议：{objections}",
        f"区域与语言：{region_lang}",
    ]
    return "\n".join(lines)


# ---------- Helpers ----------

async def _download_to_temp(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        tmp.write(resp.content)
    tmp.flush()
    return tmp.name


def _ensure_model_configured():
    if MODEL == "__MISSING_MODEL__":
        raise HTTPException(status_code=500, detail="AZURE_OPENAI_DEPLOYMENT not configured")


def _strip_markdown(md: str) -> str:
    """Convert potential Markdown to plain text to avoid formatting leaks in dialogue."""
    s = md or ""
    # Fenced code blocks markers
    s = re.sub(r"```", " ", s)
    # Inline code
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Bold/italic markers
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    # Headings
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)
    # Lists
    s = re.sub(r"^\s*[\-\*\+]\s+", "", s, flags=re.M)
    # Numbered lists like 1. text or 1) text
    s = re.sub(r"^\s*\d+[\.|\)]\s+", "", s, flags=re.M)
    # Bullets like •, ·, ●
    s = re.sub(r"^\s*[•·●]\s+", "", s, flags=re.M)
    # Blockquotes
    s = re.sub(r"^\s*>\s+", "", s, flags=re.M)
    # Links/images
    s = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    # Horizontal rules
    s = re.sub(r"^\s*---\s*$", "", s, flags=re.M)
    s = re.sub(r"^\s*([\-*_]\s*){3,}$", "", s, flags=re.M)
    # Collapse whitespace
    s = re.sub(r"\r", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


# ---------- Routes ----------
@app.post("/api/onboard")
async def onboard(
    file: Optional[UploadFile] = File(default=None),
    audio_url: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default="demo-user"),
    language_hint: Optional[str] = Form(default="zh-CN"),
):
    """Upload an audio file or provide audio_url, then:
    STT -> Prompt Builder (Markdown) -> Create Assistant -> return ids and prompt.
    """
    _ensure_model_configured()

    if not file and not audio_url:
        raise HTTPException(status_code=400, detail="Provide file or audio_url")

    # Save audio to temp (offload file I/O)
    if file:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1] or ".wav")
        content = await file.read()
        await run_in_threadpool(tmp.write, content)
        await run_in_threadpool(tmp.flush)
        audio_path = tmp.name
    else:
        audio_path = await _download_to_temp(audio_url)  # may raise

    # 1) STT (offload blocking SDK call)
    transcript = await run_in_threadpool(partial(transcribe_file, audio_path, locale=language_hint or "zh-CN"))

    # 2) Prompt Builder -> Markdown
    aoai = get_aoai_client()
    # Note: OpenAI SDK calls are synchronous but fast enough for MVP, 
    # ideally should use AsyncAzureOpenAI or run_in_executor. 
    # For now, let's keep it simple as per original code structure but acknowledge it.
    # To be strictly non-blocking, we should wrap it.
    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_BUILDER_TEMPLATE_MD},
            {"role": "user", "content": transcript},
        ],
    ))
    prompt_md = resp.choices[0].message.content
    instructions_plain = _strip_markdown(prompt_md)

    # 3) Create Assistant (Agent)
    assistant = await run_in_threadpool(lambda: aoai.beta.assistants.create(
        model=MODEL,
        name="Sales Agent",
        instructions=instructions_plain,
        metadata={"userId": user_id, "source": "voice-onboard"},
    ))

    return {
        "agent_id": assistant.id,
        "prompt": prompt_md,
        "transcript": transcript,
        "created_at": getattr(assistant, "created_at", None),
    }


@app.post("/api/onboard_text")
async def onboard_text(body: OnboardTextIn):
    """Create an assistant directly from a transcript (no audio upload)."""
    _ensure_model_configured()
    if not (body.transcript or "").strip():
        raise HTTPException(status_code=400, detail="transcript is required")

    aoai = get_aoai_client()
    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_BUILDER_TEMPLATE_MD},
            {"role": "user", "content": body.transcript},
        ],
    ))
    prompt_md = resp.choices[0].message.content
    instructions_plain = _strip_markdown(prompt_md)

    assistant = await run_in_threadpool(lambda: aoai.beta.assistants.create(
        model=MODEL,
        name="Sales Agent",
        instructions=instructions_plain,
        metadata={"userId": body.user_id or "demo-user", "source": "text-onboard"},
    ))

    return {
        "agent_id": assistant.id,
        "prompt": prompt_md,
        "transcript": body.transcript,
        "created_at": getattr(assistant, "created_at", None),
    }


@app.get("/api/agents")
async def list_agents(user_id: Optional[str] = None):
    _ensure_model_configured()
    aoai = get_aoai_client()
    # Increase limit to show more agents (default is 20)
    items = await run_in_threadpool(lambda: aoai.beta.assistants.list(order="desc", limit=100))
    data = []
    for a in items.data:
        if user_id and (getattr(a, "metadata", {}) or {}).get("userId") != user_id:
            continue
        # Get first 100 chars of instructions as description
        instructions = getattr(a, "instructions", "") or ""
        description = instructions[:100] + "..." if len(instructions) > 100 else instructions
        data.append({
            "id": a.id,
            "name": getattr(a, "name", ""),
            "description": description,
            "created_at": getattr(a, "created_at", None),
            "userId": (getattr(a, "metadata", {}) or {}).get("userId"),
        })
    return data


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    _ensure_model_configured()
    aoai = get_aoai_client()
    a = await run_in_threadpool(lambda: aoai.beta.assistants.retrieve(assistant_id=agent_id))
    return {
        "id": a.id,
        "name": getattr(a, "name", ""),
        "instructions": getattr(a, "instructions", ""),
        "metadata": getattr(a, "metadata", {}),
        "created_at": getattr(a, "created_at", None),
    }


@app.post("/api/agents/{agent_id}/chat")
async def chat(agent_id: str, body: ChatIn):
    """Fast chat endpoint using Chat Completions API instead of Assistants API.
    
    This is 3-5x faster than the old Assistants API approach because:
    - Single API call instead of 7-14 calls
    - No polling overhead
    - Direct conversation history management
    """
    _ensure_model_configured()
    aoai = get_aoai_client()

    # Generate thread_id if not provided
    import uuid
    thread_id = body.thread_id or str(uuid.uuid4())
    
    # Get or initialize conversation history
    if thread_id not in _CONVERSATION_HISTORY:
        _CONVERSATION_HISTORY[thread_id] = []
        
        # Get agent instructions for system message
        try:
            agent = await run_in_threadpool(lambda: aoai.beta.assistants.retrieve(assistant_id=agent_id))
            instructions = getattr(agent, "instructions", "") or "你是一个有帮助的AI助手。"
            _CONVERSATION_HISTORY[thread_id].append({
                "role": "system",
                "content": instructions
            })
        except Exception:
            # Fallback if agent not found
            _CONVERSATION_HISTORY[thread_id].append({
                "role": "system",
                "content": "你是一个有帮助的AI助手。"
            })
    
    # Add user message to history
    _CONVERSATION_HISTORY[thread_id].append({
        "role": "user",
        "content": body.message
    })
    
    # Call Chat Completions API (fast, single call)
    try:
        response = await run_in_threadpool(lambda: aoai.chat.completions.create(
            model=MODEL,
            messages=_CONVERSATION_HISTORY[thread_id],
            temperature=0.7,
            max_tokens=800
        ))
        
        reply = response.choices[0].message.content or ""
        
        # Add assistant reply to history
        _CONVERSATION_HISTORY[thread_id].append({
            "role": "assistant",
            "content": reply
        })
        
        # Limit history to last 20 messages to prevent context overflow
        if len(_CONVERSATION_HISTORY[thread_id]) > 21:  # 1 system + 20 messages
            # Keep system message and last 20
            _CONVERSATION_HISTORY[thread_id] = [
                _CONVERSATION_HISTORY[thread_id][0]  # system
            ] + _CONVERSATION_HISTORY[thread_id][-20:]
        
        return {"reply": reply, "thread_id": thread_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")



@app.post("/api/agents/{agent_id}/chat/stream")
async def chat_stream(agent_id: str, body: ChatIn):
    """Streaming chat endpoint using Server-Sent Events (SSE).
    
    This provides real-time streaming of LLM responses, dramatically improving
    perceived latency from 4s to <1s.
    """
    _ensure_model_configured()
    aoai = get_aoai_client()

    # Generate thread_id if not provided
    import uuid
    thread_id = body.thread_id or str(uuid.uuid4())
    
    # Get or initialize conversation history
    if thread_id not in _CONVERSATION_HISTORY:
        _CONVERSATION_HISTORY[thread_id] = []
        
        # Get agent instructions for system message
        try:
            agent = await run_in_threadpool(lambda: aoai.beta.assistants.retrieve(assistant_id=agent_id))
            instructions = getattr(agent, "instructions", "") or "你是一个有帮助的AI助手。"
            _CONVERSATION_HISTORY[thread_id].append({
                "role": "system",
                "content": instructions
            })
        except Exception:
            _CONVERSATION_HISTORY[thread_id].append({
                "role": "system",
                "content": "你是一个有帮助的AI助手。"
            })
    
    # Add user message to history
    _CONVERSATION_HISTORY[thread_id].append({
        "role": "user",
        "content": body.message
    })
    
    # Stream generator function
    async def generate():
        try:
            # Call Chat Completions API with streaming enabled
            response = await run_in_threadpool(lambda: aoai.chat.completions.create(
                model=MODEL,
                messages=_CONVERSATION_HISTORY[thread_id],
                temperature=0.7,
                max_tokens=800,
                stream=True  # Enable streaming
            ))
            
            full_reply = ""
            
            # Stream each chunk as it arrives
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_reply += content
                    
                    # Send SSE event
                    yield f"data: {json.dumps({'content': content, 'done': False})}\n\n"
            
            # Add complete reply to history
            _CONVERSATION_HISTORY[thread_id].append({
                "role": "assistant",
                "content": full_reply
            })
            
            # Limit history to last 20 messages
            if len(_CONVERSATION_HISTORY[thread_id]) > 21:
                _CONVERSATION_HISTORY[thread_id] = [
                    _CONVERSATION_HISTORY[thread_id][0]
                ] + _CONVERSATION_HISTORY[thread_id][-20:]
            
            # Send final event with thread_id
            yield f"data: {json.dumps({'done': True, 'thread_id': thread_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.get("/api/speech/token")
async def speech_token():
    return await issue_speech_token()


# ---------- CosyVoice TTS endpoints ----------
@app.post("/api/tts")
async def text_to_speech(
    text: str = Form(...),
    speaker: str = Form(default="default"),
    speed: float = Form(default=1.0)
):
    """Synthesize speech using CosyVoice2 with preset speaker
    
    Args:
        text: Text to synthesize
        speaker: Speaker ID
        speed: Speech speed (0.5 - 2.0)
        
    Returns:
        Audio file (WAV format)
    """
    cosyvoice = get_cosyvoice_client()
    
    try:
        audio_data = await cosyvoice.synthesize(
            text=text,
            speaker=speaker,
            speed=speed
        )
        
        from fastapi.responses import Response
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=speech.wav"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")


@app.post("/api/tts/clone")
async def text_to_speech_clone(
    text: str = Form(...),
    reference_audio: UploadFile = File(...),
    speed: float = Form(default=1.0)
):
    """Synthesize speech using CosyVoice2 with voice cloning
    
    Args:
        text: Text to synthesize
        reference_audio: Reference audio file for voice cloning (WAV, 3-10s)
        speed: Speech speed (0.5 - 2.0)
        
    Returns:
        Audio file (WAV format) with cloned voice
    """
    cosyvoice = get_cosyvoice_client()
    
    try:
        # Read reference audio
        ref_audio_bytes = await reference_audio.read()
        
        # Synthesize with voice cloning
        audio_data = await cosyvoice.synthesize(
            text=text,
            reference_audio=ref_audio_bytes,
            speed=speed
        )
        
        from fastapi.responses import Response
        return Response(
            content=audio_data,
            media_type="audio/wav",
            headers={
                "Content-Disposition": f"attachment; filename=cloned_speech.wav"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {str(e)}")


@app.get("/api/tts/speakers")
async def get_speakers():
    """Get list of available preset speakers"""
    cosyvoice = get_cosyvoice_client()
    
    try:
        speakers = await cosyvoice.get_speakers()
        return {"speakers": speakers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get speakers: {str(e)}")


@app.get("/api/tts/health")
async def tts_health():
    """Check CosyVoice TTS health status"""
    cosyvoice = get_cosyvoice_client()
    
    is_healthy = await cosyvoice.health_check()
    
    return {
        "healthy": is_healthy,
        "enabled": cosyvoice.enabled,
        "url": cosyvoice.base_url
    }


# ---------- Onboarding sessions endpoints ----------
@app.post("/api/onboard_session/start")
async def onboard_session_start(body: SessionStartIn):
    _ensure_model_configured()
    state = _new_session(user_id=body.user_id or "demo-user", seed=body.seed_transcript)
    
    # Generate initial greeting/question using Interviewer LLM
    aoai = get_aoai_client()
    messages = [{"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT}]
    
    # If there is a seed transcript, treat it as the first user message
    if body.seed_transcript:
        messages.append({"role": "user", "content": body.seed_transcript})
    else:
        # If no seed, ask LLM to start
        messages.append({"role": "user", "content": "Hello, I want to create a sales agent. Please start the interview."})

    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
    ))
    reply = resp.choices[0].message.content
    
    # If seed existed, we already added it to history in _new_session, now add assistant reply
    state.history.append({"role": "assistant", "text": reply})
    
    return {"session": state.model_dump(), "reply": reply}


@app.post("/api/onboard_session/{session_id}/message")
async def onboard_session_message(session_id: str, body: SessionMessageIn):
    _ensure_model_configured()
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    
    # 1. Record user message
    state.history.append({"role": "user", "text": body.message})
    
    # 2. Extract fields in background (to track progress)
    # We extract from the *latest* message or potentially the whole history if needed. 
    # For simplicity and cost, let's extract from the latest message + context if possible, 
    # but _extract_fields is currently stateless. 
    # Let's try to extract from the latest message. 
    # Ideally, we should pass the whole conversation to the extractor, but that might be heavy.
    # Let's stick to per-message extraction for now, or maybe concatenate last few.
    extracted = await run_in_threadpool(partial(_extract_fields, body.message))
    _apply_extracted(state, extracted)

    # 3. Generate Interviewer Response
    aoai = get_aoai_client()
    messages = [{"role": "system", "content": INTERVIEWER_SYSTEM_PROMPT}]
    
    # Reconstruct history for LLM
    # Limit history to last 10 turns to avoid context overflow
    recent_history = state.history[-10:] 
    for h in recent_history:
        role = h["role"]
        # Map 'text' to 'content'
        content = h.get("text", "")
        messages.append({"role": role, "content": content})

    # Optional: Inject a system hint if we have all fields
    if not state.missing:
        messages.append({
            "role": "system", 
            "content": "(System Note: You have collected all required fields. If the user seems ready, propose to generate the agent.)"
        })

    resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7,
    ))
    reply = resp.choices[0].message.content
    state.history.append({"role": "assistant", "text": reply})

    # Check if we are "done" based on fields OR LLM signal
    done = len(state.missing) == 0
    if "[DONE]" in reply:
        done = True
        reply = reply.replace("[DONE]", "").strip()
        # Update history with cleaned reply
        state.history[-1]["text"] = reply

    return {"session": state.model_dump(), "reply": reply, "done": done}


@app.post("/api/onboard_session/{session_id}/voice_template")
async def upload_voice_template(session_id: str, audio: UploadFile = File(...)):
    """Upload voice template for the onboarding session
    
    This voice will be used as the reference audio for voice cloning when the agent speaks.
    """
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    
    # Read and store voice template
    audio_bytes = await audio.read()
    state.voice_template = audio_bytes
    
    return {"success": True, "message": "Voice template uploaded successfully"}


@app.post("/api/onboard_session/{session_id}/finalize")
async def onboard_session_finalize(session_id: str):
    _ensure_model_configured()
    state = _SESSIONS.get(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="session not found")
    
    # Relaxed check: We allow generation even if fields are missing.
    # We will rely on defaults in _build_profile_summary.
    # if state.missing:
    #     raise HTTPException(status_code=400, detail=f"missing fields: {', '.join(state.missing)}")

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


    # Prepare metadata with voice template if available
    import base64
    metadata = {
        "userId": state.user_id,
        "source": "mt-onboard"
    }
    
    # Store voice template as base64 in metadata if available
    if state.voice_template:
        metadata["voice_template_b64"] = base64.b64encode(state.voice_template).decode('utf-8')
    
    assistant = await run_in_threadpool(lambda: aoai.beta.assistants.create(
        model=MODEL,
        name=(state.fields.get("brand") or "Sales Agent"),
        instructions=instructions_plain,
        metadata=metadata,
    ))
    return {
        "agent_id": assistant.id,
        "prompt": prompt_md,
        "profile": state.fields,
        "has_voice_template": state.voice_template is not None,
        "created_at": getattr(assistant, "created_at", None),
    }
