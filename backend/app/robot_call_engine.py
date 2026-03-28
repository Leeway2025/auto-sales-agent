"""机器人外呼对话引擎

呼叫流程：
1. 呼叫中心发起外呼（make_call）
2. 呼叫中心 Webhook 回调 status=answer → 开始对话
3. 呼叫中心将录音文件 URL 推送 → 下载 → Azure STT → 文字
4. LLM（Agent 指令 + 对话历史）生成回复
5. CosyVoice2 TTS（声音克隆）→ WAV 音频
6. 将音频推送回呼叫中心播放（HTTP 回传 / 外链）
7. 循环直到 LLM 判定结束或客户挂机

音频交互模式（本实现）：
  呼叫中心使用「录音回传」模式：
    - 每轮客户说完，呼叫中心 Webhook 推送录音片段 URL
    - 系统下载录音 → STT → LLM → TTS → 返回音频 URL
    - 呼叫中心播放返回的音频 URL 给客户
  此模式无需 SIP 集成，只需 HTTP。
"""

import asyncio
import base64
import logging
import os
import time
import tempfile
import uuid
from typing import Optional, Dict, Any, List

import httpx
from fastapi.concurrency import run_in_threadpool

from .azure_clients import get_aoai_client, transcribe_file, synthesize_speech_azure
from .cosyvoice_client import get_cosyvoice_client
from .callcenter_client import hangup_call

logger = logging.getLogger(__name__)

# ---------- 会话存储（内存，可换 Redis） ----------
# key: call_uuid  value: RobotCallSession
_ROBOT_SESSIONS: Dict[str, "RobotCallSession"] = {}

# 最长通话轮次，超出后主动挂机（防止无限循环）
MAX_TURNS = int(os.getenv("ROBOT_CALL_MAX_TURNS", "20"))
# 单轮最长等待客户说话（秒），超时后挂机
TURN_TIMEOUT = int(os.getenv("ROBOT_CALL_TURN_TIMEOUT", "30"))

# 结束通话的关键词（LLM 回复中含任一词则挂机）
HANGUP_SIGNALS = ["[HANGUP]", "[END]", "[再见]", "[挂断]"]

# 公网可访问的音频服务基地址（呼叫中心需要能下载 TTS 音频）
AUDIO_BASE_URL = os.getenv("ROBOT_CALL_AUDIO_BASE_URL", "")


class RobotCallSession:
    """维护单路外呼机器人通话的完整状态。"""

    def __init__(
        self,
        call_uuid: str,
        agent_id: str,
        agent_instructions: str,
        phone: str,
        voice_template_b64: Optional[str] = None,
    ):
        self.call_uuid = call_uuid
        self.agent_id = agent_id
        self.phone = phone
        self.voice_template: Optional[bytes] = (
            base64.b64decode(voice_template_b64) if voice_template_b64 else None
        )
        self.history: List[Dict[str, str]] = [
            {"role": "system", "content": agent_instructions}
        ]
        self.turn = 0
        self.started_at = time.time()
        self.status = "ringing"   # ringing → active → ended

    # ------------------------------------------------------------------ #
    #  主对话循环（由 Webhook answer 事件触发）                              #
    # ------------------------------------------------------------------ #

    async def on_answered(self) -> Optional[bytes]:
        """通话接通：生成并返回开场白音频。"""
        self.status = "active"
        logger.info("[%s] Call answered, generating opener", self.call_uuid)

        opener = await self._llm_reply("（通话刚刚接通，请开始介绍）")
        if not opener:
            return None
        return await self._tts(opener)

    async def on_user_audio(self, audio_url: str) -> Optional[bytes]:
        """收到客户录音片段 URL → STT → LLM → TTS → 返回音频。"""
        if self.status != "active":
            return None

        self.turn += 1
        if self.turn > MAX_TURNS:
            logger.info("[%s] Max turns reached, hanging up", self.call_uuid)
            await hangup_call(self.call_uuid)
            self.status = "ended"
            return None

        # 1. 下载录音
        audio_bytes = await _download_audio(audio_url)
        if not audio_bytes:
            logger.warning("[%s] Failed to download audio from %s", self.call_uuid, audio_url)
            return None

        # 2. STT
        user_text = await _stt(audio_bytes)
        if not user_text:
            logger.info("[%s] STT returned empty, skipping turn", self.call_uuid)
            return None
        logger.info("[%s] User said: %s", self.call_uuid, user_text)

        # 3. LLM
        reply_text = await self._llm_reply(user_text)
        if not reply_text:
            return None
        logger.info("[%s] Agent reply: %s", self.call_uuid, reply_text[:80])

        # 4. 判断是否应挂机
        if any(sig in reply_text for sig in HANGUP_SIGNALS):
            clean = reply_text
            for sig in HANGUP_SIGNALS:
                clean = clean.replace(sig, "")
            audio = await self._tts(clean.strip()) if clean.strip() else None
            await asyncio.sleep(3)   # 播完再挂
            await hangup_call(self.call_uuid)
            self.status = "ended"
            return audio

        # 5. TTS → 返回音频
        return await self._tts(reply_text)

    def on_hangup(self):
        self.status = "ended"
        logger.info(
            "[%s] Call ended. turns=%d duration=%.0fs",
            self.call_uuid, self.turn, time.time() - self.started_at,
        )

    # ------------------------------------------------------------------ #
    #  内部方法                                                             #
    # ------------------------------------------------------------------ #

    async def _llm_reply(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        aoai = get_aoai_client()
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

        resp = await run_in_threadpool(lambda: aoai.chat.completions.create(
            model=model,
            messages=self.history,
            temperature=0.7,
            max_tokens=200,   # 电话场景回复要短
        ))
        reply = resp.choices[0].message.content or ""
        self.history.append({"role": "assistant", "content": reply})

        # 保持历史在 20 轮以内
        if len(self.history) > 41:
            self.history = [self.history[0]] + self.history[-40:]

        return reply

    async def _tts(self, text: str) -> Optional[bytes]:
        """优先 CosyVoice2（声音克隆），回退 Azure TTS。"""
        cosyvoice = get_cosyvoice_client()
        if cosyvoice.enabled:
            try:
                return await cosyvoice.synthesize(
                    text=text, reference_audio=self.voice_template
                )
            except Exception as e:
                logger.warning("[%s] CosyVoice TTS failed: %s, falling back", self.call_uuid, e)

        try:
            return await run_in_threadpool(synthesize_speech_azure, text)
        except Exception as e:
            logger.error("[%s] Azure TTS also failed: %s", self.call_uuid, e)
            return None


# ---------- 辅助函数 ----------

async def _download_audio(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.error("Failed to download audio %s: %s", url, e)
        return None


async def _stt(audio_bytes: bytes) -> str:
    """将音频字节写入临时文件，调用 Azure STT。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        return await run_in_threadpool(transcribe_file, tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ---------- 会话管理 ----------

def get_session(call_uuid: str) -> Optional[RobotCallSession]:
    return _ROBOT_SESSIONS.get(call_uuid)


def create_session(
    call_uuid: str,
    agent_id: str,
    agent_instructions: str,
    phone: str,
    voice_template_b64: Optional[str] = None,
) -> RobotCallSession:
    session = RobotCallSession(
        call_uuid=call_uuid,
        agent_id=agent_id,
        agent_instructions=agent_instructions,
        phone=phone,
        voice_template_b64=voice_template_b64,
    )
    _ROBOT_SESSIONS[call_uuid] = session
    return session


def remove_session(call_uuid: str):
    _ROBOT_SESSIONS.pop(call_uuid, None)
