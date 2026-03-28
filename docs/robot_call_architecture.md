# 机器人自动外呼销售架构

## 整体流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                         触发外呼                                      │
│  POST /api/robot_call/start { phone, agent_id }                     │
└────────────────────────────┬────────────────────────────────────────┘
                             │ 1. 获取 Agent 指令 + 声音模板
                             │ 2. 调用呼叫中心 API 发起外呼
                             │ 3. 创建 RobotCallSession（内存）
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      云虎呼叫中心                                     │
│              call.yunhus.com:4434                                   │
│                                                                     │
│  ① 拨打客户手机号                                                     │
│  ② 客户接听 → 推送 Webhook status=answer                            │
│  ③ 播放系统返回的音频 URL                                            │
│  ④ 录制客户说话 → 推送录音片段 URL                                   │
│  ⑤ 通话结束 → 推送 Webhook status=hangup + 通话记录                 │
└────────┬────────────────────────────────────────────────────────────┘
         │ Webhook 回调
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        后端 (FastAPI)                               │
│                                                                     │
│  /api/webhook/callcenter/status  ← ring / answer / hangup          │
│  /api/webhook/callcenter/audio   ← 客户单轮录音 URL                 │
│  /api/webhook/callcenter/record  ← 通话结束记录                     │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  RobotCallSession                           │   │
│  │                                                             │   │
│  │  客户录音 URL                                               │   │
│  │      │                                                      │   │
│  │      ▼                                                      │   │
│  │  ① 下载录音（httpx）                                        │   │
│  │      │                                                      │   │
│  │      ▼                                                      │   │
│  │  ② Azure STT → 文字                                        │   │
│  │      │                                                      │   │
│  │      ▼                                                      │   │
│  │  ③ Azure OpenAI LLM                                        │   │
│  │    （Agent system prompt + 对话历史）                       │   │
│  │    → 销售话术回复文字                                       │   │
│  │      │                                                      │   │
│  │      ▼                                                      │   │
│  │  ④ CosyVoice2 TTS（声音克隆）                              │   │
│  │    回退：Azure TTS                                          │   │
│  │    → 回复 WAV 音频                                          │   │
│  │      │                                                      │   │
│  │      ▼                                                      │   │
│  │  ⑤ 保存到 /tmp，返回公网 URL                               │   │
│  │    → 呼叫中心拉取并播放给客户                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 新增文件说明

| 文件 | 职责 |
|------|------|
| [app/callcenter_client.py](../backend/app/callcenter_client.py) | 呼叫中心 HTTP API 封装：token、外呼、挂断、记录、录音地址 |
| [app/robot_call_engine.py](../backend/app/robot_call_engine.py) | 单路通话会话状态机：STT→LLM→TTS 完整对话循环 |
| `main.py` 新增路由 | 外呼触发 + 3 个 Webhook 接收端点 + 音频文件下载 |

---

## API 端点

### 触发外呼

```http
POST /api/robot_call/start
{
  "phone": "13800138000",
  "agent_id": "asst_xxxx",
  "task_id": "task_001",   // 可选
  "crm_id": "crm_001"      // 可选
}
```

响应：
```json
{ "call_uuid": "uuid-xxx", "phone": "13800138000", "status": "calling" }
```

### Webhook（呼叫中心配置回调地址）

| 地址 | 触发时机 |
|------|---------|
| `POST /api/webhook/callcenter/status` | ring / answer / hangup 状态变化 |
| `POST /api/webhook/callcenter/audio` | 每轮客户说话录音片段就绪 |
| `POST /api/webhook/callcenter/record` | 通话结束后推送完整记录 |

---

## 环境变量

```env
# 呼叫中心认证
CALLCENTER_URL=http://call.yunhus.com:4434
CALLCENTER_APP_ID=EF18QSHXI41M0I9BFL244NH160I5PHOR
CALLCENTER_ACC_KEY=6IIC2CUR3WDR3K9YS93NZLU2W7HKWYH0

# 机器人音频公网地址（呼叫中心需要能拉取）
ROBOT_CALL_AUDIO_BASE_URL=https://your-server.com

# 行为参数
ROBOT_CALL_MAX_TURNS=20    # 最大对话轮次
ROBOT_CALL_TURN_TIMEOUT=30 # 等待客户超时（秒）
```

---

## 呼叫中心配置要求

呼叫中心需在管理后台配置以下回调地址（将 `your-server.com` 替换为实际域名）：

| 回调类型 | 地址 |
|---------|------|
| 坐席状态回调 | `https://your-server.com/api/webhook/callcenter/status` |
| 实时录音片段 | `https://your-server.com/api/webhook/callcenter/audio` |
| 通话记录回调 | `https://your-server.com/api/webhook/callcenter/record` |

> 回调地址必须为 **HTTPS 公网可访问地址**。本地开发可用 `ngrok` 临时暴露。

---

## 通话挂机信号

LLM 回复中包含以下任意词时，系统会播完当前回复后主动挂机：

```
[HANGUP]  [END]  [再见]  [挂断]
```

在 Agent 的 system prompt 中可加入规则：

```
当判断客户明确拒绝或通话应结束时，在回复末尾加上 [HANGUP]。
```

---

## 延迟参考（T4 GPU）

| 阶段 | 耗时 |
|------|------|
| 下载客户录音 | ~0.2s |
| Azure STT | ~0.5s |
| Azure OpenAI LLM | ~0.8s |
| CosyVoice2 TTS（克隆） | ~3s |
| **单轮总延迟** | **~4.5s** |

> 单轮 4-5 秒是电话 AI 的合理范围。如需更低延迟，可用 Azure TTS 替代 CosyVoice2（降至约 2s），代价是失去声音克隆。

---

## 生产注意事项

1. **音频临时文件清理**：`/tmp/*.wav` 需定期清理，或改用 OSS/CDN 存储
2. **会话持久化**：当前 `_ROBOT_SESSIONS` 为内存字典，服务重启丢失；生产建议用 Redis
3. **并发限制**：单台服务器 CosyVoice2 + Azure STT 并发约 5-10 路，更高并发需水平扩展
4. **Webhook 安全**：生产环境应验证呼叫中心推送的签名或 IP 白名单
5. **合规**：自动外呼需遵守当地法规（如时段限制、频次限制、被叫号码名单管理）
