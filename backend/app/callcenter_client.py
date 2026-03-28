"""云虎呼叫中心 API 客户端

接口文档摘要:
  接口地址: http://call.yunhus.com:4434
  认证方式: AppId + AccKey → 获取 token，后续请求携带 token

主要功能:
  - 获取/刷新 token
  - 发起外呼（机器人自动拨号）
  - 挂断通话
  - 查询通话记录
  - 获取录音下载地址
"""

import os
import time
import logging
import hashlib
import hmac
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# ---------- 配置 ----------
_BASE_URL = None
_APP_ID = None
_ACC_KEY = None

# token 缓存（有效期约 2 小时，提前 5 分钟刷新）
_token: Optional[str] = None
_token_expires_at: float = 0.0


def _get_config():
    global _BASE_URL, _APP_ID, _ACC_KEY
    if _BASE_URL is None:
        _BASE_URL = os.getenv("CALLCENTER_URL", "http://call.yunhus.com:4434")
        _APP_ID   = os.getenv("CALLCENTER_APP_ID", "")
        _ACC_KEY  = os.getenv("CALLCENTER_ACC_KEY", "")
    if not _APP_ID or not _ACC_KEY:
        raise RuntimeError("Missing CALLCENTER_APP_ID or CALLCENTER_ACC_KEY")
    return _BASE_URL, _APP_ID, _ACC_KEY


# ---------- Token ----------

async def _fetch_token() -> str:
    """向呼叫中心请求新 token，缓存结果。"""
    global _token, _token_expires_at
    base_url, app_id, acc_key = _get_config()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/api/token",
            json={"appid": app_id, "acckey": acc_key},
        )
        resp.raise_for_status()
        data = resp.json()

    # 接口返回格式参考文档（token 字段名以实际返回为准）
    token = data.get("token") or data.get("data", {}).get("token") or data.get("access_token")
    if not token:
        raise RuntimeError(f"Token not found in response: {data}")

    expires_in = int(data.get("expires_in", 7200))
    _token = token
    _token_expires_at = time.time() + expires_in - 300  # 提前 5 分钟刷新
    logger.info("CallCenter token refreshed, expires in %ds", expires_in)
    return _token


async def get_token() -> str:
    """返回有效 token，过期则自动刷新。"""
    if _token and time.time() < _token_expires_at:
        return _token
    return await _fetch_token()


def _auth_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ---------- 外呼 ----------

async def make_call(
    phone: str,
    agent_id: str,
    task_id: Optional[str] = None,
    crm_id: Optional[str] = None,
    member_id: Optional[str] = None,
    ext_number: Optional[str] = None,
) -> Dict[str, Any]:
    """发起一路外呼，返回呼叫 ID（uuid）。

    Args:
        phone:      被叫号码（客户手机）
        agent_id:   本系统 Agent ID，传入 crmid 字段供 Webhook 回调匹配
        task_id:    外呼任务 ID（可选）
        crm_id:     工单 ID（可选）
        member_id:  会员 ID（可选）
        ext_number: 使用的分机号（可选，不传由呼叫中心自动分配）
    """
    base_url, _, _ = _get_config()
    token = await get_token()

    payload: Dict[str, Any] = {
        "callee": phone,
        "method": 3,            # 3 = 接口发起
        "direction": "callout",
    }
    if ext_number:
        payload["extnumber"] = ext_number
    if task_id:
        payload["taskid"] = task_id
    if crm_id:
        payload["crmid"] = crm_id
    # 把 agent_id 塞进 memberid，便于 Webhook 回调时定位要用哪个 Agent
    payload["memberid"] = agent_id or "0"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{base_url}/api/call/out",
            json=payload,
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        data = resp.json()

    call_uuid = (
        data.get("uuid")
        or data.get("data", {}).get("uuid")
        or data.get("callid")
    )
    logger.info("Call initiated: phone=%s uuid=%s", phone, call_uuid)
    return {"uuid": call_uuid, "raw": data}


# ---------- 挂断 ----------

async def hangup_call(call_uuid: str) -> bool:
    """主动挂断通话。"""
    base_url, _, _ = _get_config()
    token = await get_token()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{base_url}/api/call/hangup",
            json={"uuid": call_uuid},
            headers=_auth_headers(token),
        )
        resp.raise_for_status()

    logger.info("Call hung up: uuid=%s", call_uuid)
    return True


# ---------- 通话记录 ----------

async def get_call_records(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """查询通话记录列表。"""
    base_url, _, _ = _get_config()
    token = await get_token()

    params: Dict[str, Any] = {"page": page, "pagesize": page_size}
    if start_time:
        params["starttime"] = start_time
    if end_time:
        params["endtime"] = end_time

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{base_url}/api/call/records",
            params=params,
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


# ---------- 录音下载地址 ----------

async def get_recording_url(record_id: int) -> Optional[str]:
    """获取指定通话记录的录音下载地址。"""
    base_url, _, _ = _get_config()
    token = await get_token()

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{base_url}/api/call/record/download",
            params={"id": record_id},
            headers=_auth_headers(token),
        )
        resp.raise_for_status()
        data = resp.json()

    return data.get("url") or data.get("download_url")
