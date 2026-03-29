# Auto Sales Agent Platform

[![GitHub](https://img.shields.io/badge/GitHub-Leeway2025%2Fauto--sales--agent-blue?logo=github)](https://github.com/Leeway2025/auto-sales-agent)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/react-18-61dafb.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.114+-009688.svg)](https://fastapi.tiangolo.com/)

一个基于 LLM 的智能销售 Agent 创建和管理平台，支持语音交互、声音克隆、流式对话，以及**机器人自动电话外呼销售**。

> **核心亮点**: LLM 对话式 Onboarding + CosyVoice2 声音克隆 + 毫秒级流式响应 + 云虎呼叫中心自动外呼

---

## 核心功能

### 1. LLM 驱动的 Onboarding 向导
- 智能对话式信息收集（品牌、行业、受众、话术风格等）
- 自动生成个性化销售 Agent system prompt
- 声音模板录制：录制 5 秒声音，Agent 将用你的声音说话

### 2. 高性能聊天系统
- 流式响应，首字延迟 < 1 秒
- Server-Sent Events (SSE) 实时打字效果
- 自动对话历史管理（保留最近 20 轮）

### 3. CosyVoice2 声音克隆 TTS
- 声音克隆：使用 Onboarding 录制的声音模板合成语音
- Azure TTS 自动回退（CosyVoice2 不可用时）
- T4 GPU 优化部署，单轮合成延迟约 3 秒

### 4. 机器人自动电话外呼
- 对接云虎呼叫中心 API，一键触发外呼任务
- 全自动对话循环：客户录音 → Azure STT → LLM → TTS → 播放
- 智能挂机：LLM 判断通话结束时自动挂断
- Webhook 接收呼叫状态、录音片段、通话记录

---

## 技术架构

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + Uvicorn (Python 3.11) |
| 前端 | React 18 + TypeScript + Vite + MUI |
| LLM | Azure OpenAI (gpt-4o-mini) |
| STT | Azure Speech Services |
| TTS | CosyVoice2（声音克隆）+ Azure TTS（回退） |
| 外呼 | 云虎呼叫中心 (call.yunhus.com) |
| 部署 | Docker Compose + NVIDIA T4 GPU |

---

## 项目结构

```
auto/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI 主应用 + 所有路由
│   │   ├── azure_clients.py       # Azure OpenAI / Speech 封装
│   │   ├── cosyvoice_client.py    # CosyVoice2 HTTP 客户端
│   │   ├── callcenter_client.py   # 云虎呼叫中心 API 客户端
│   │   ├── robot_call_engine.py   # 机器人外呼对话引擎
│   │   └── prompt_templates.py    # Prompt 模板（含挂机规则）
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── cosyvoice_service/             # CosyVoice2 微服务
│   ├── api_server.py              # FastAPI TTS 服务
│   ├── Dockerfile                 # T4 GPU 优化镜像
│   ├── entrypoint.sh
│   └── download_model.py          # 自动下载模型
├── frontend/
│   ├── src/
│   │   ├── pages/                 # Onboarding / Agents / Chat
│   │   ├── hooks/                 # Azure Speech SDK / 声音克隆
│   │   └── api/index.ts           # API 客户端
│   ├── Dockerfile                 # 多阶段构建 + Nginx
│   └── nginx.conf                 # API 反向代理 + SSE 支持
├── docker-compose.yml             # 一键启动三服务
└── docs/
    ├── deployment.md              # 完整部署指南
    ├── robot_call_architecture.md # 外呼架构与 API 文档
    └── cosyvoice_deployment.md    # CosyVoice2 手动部署
```

---

## 快速开始（Docker Compose）

```bash
git clone https://github.com/Leeway2025/auto-sales-agent.git
cd auto-sales-agent

cp backend/.env.example backend/.env
# 编辑 backend/.env，填入所有必填项（见下方）

# 首次启动（自动下载 CosyVoice2 模型 ~2GB）
MODEL_DOWNLOAD=1 docker compose up -d --build
```

服务启动后：
- 前端：`http://your-server-ip`
- 后端 API 文档：`http://your-server-ip:8000/docs`
- CosyVoice2：`http://your-server-ip:9880/health`

详细部署说明见 [docs/deployment.md](docs/deployment.md)。

---

## 环境变量

复制并填写 `backend/.env`：

```bash
cp backend/.env.example backend/.env
```

### 必填

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=australiaeast
```

### 外呼功能（使用机器人电话时必填）

```env
CALLCENTER_APP_ID=your-appid
CALLCENTER_ACC_KEY=your-acckey
ROBOT_CALL_AUDIO_BASE_URL=http://your-server-ip:8000
```

### 可选

```env
CORS_ORIGINS=http://localhost:5173   # 生产改为实际域名
COSYVOICE_ENABLED=true
AZURE_TTS_VOICE=zh-CN-XiaoxiaoNeural
ROBOT_CALL_MAX_TURNS=20
ROBOT_CALL_TURN_TIMEOUT=30
```

---

## 使用指南

### 创建销售 Agent

1. 访问 `/onboard-session`
2. 与 AI 面试官对话，提供品牌、行业、产品等信息
3. 出现"创建"按钮后，可选择录制 5 秒声音模板
4. 点击"确认生成"完成创建

### 网页聊天

1. 访问 `/agents`，点击任意 Agent 的"聊天"
2. 支持文字输入和流式语音回复

### 机器人自动外呼

```bash
curl -X POST http://your-server:8000/api/robot_call/start \
  -H "Content-Type: application/json" \
  -d '{"phone": "13800138000", "agent_id": "asst_xxx"}'
```

系统将自动拨打客户电话，用 Agent 的声音和话术进行销售对话，并在合适时机自动挂断。

详细架构和 Webhook 说明见 [docs/robot_call_architecture.md](docs/robot_call_architecture.md)。

---

## 呼叫中心配置

在云虎呼叫中心管理后台配置以下回调地址：

| 回调类型 | 地址 |
|---------|------|
| 坐席状态回调 | `http://your-server:8000/api/webhook/callcenter/status` |
| 实时录音片段 | `http://your-server:8000/api/webhook/callcenter/audio` |
| 通话记录回调 | `http://your-server:8000/api/webhook/callcenter/record` |

---

## 当前待办事项

以下是部署和使用前需要完成的配置工作：

### 部署前（必须）
- [ ] 填写 `backend/.env` 中所有 `AZURE_*` 必填项
- [ ] 确认服务器已安装 `nvidia-container-toolkit`（T4 GPU 节点）
- [ ] 将 `CORS_ORIGINS` 改为实际前端域名/IP

### 外呼功能（使用前必须）
- [ ] `backend/.env` 填入 `CALLCENTER_APP_ID` 和 `CALLCENTER_ACC_KEY`
- [ ] `backend/.env` 填入 `ROBOT_CALL_AUDIO_BASE_URL`（服务器公网地址）
- [ ] 在云虎呼叫中心后台配置以下 3 个 Webhook 回调地址（将 `your-server` 替换为服务器 IP 或域名）：
  - **坐席状态回调**：`http://your-server:8000/api/webhook/callcenter/status`
    （接收 ring/answer/hangup 事件，接通时触发机器人开场白）
  - **实时录音片段回调**：`http://your-server:8000/api/webhook/callcenter/audio`
    （每轮客户说完推送录音，驱动 STT→LLM→TTS 对话循环，**缺此项机器人无法回应客户**）
  - **通话记录回调**：`http://your-server:8000/api/webhook/callcenter/record`
    （通话结束后推送完整记录，含时长和录音文件地址）
- [ ] 在 Agent system prompt 中加入挂机说明（新建 Agent 自动包含，旧 Agent 需手动更新）

### 生产加固（上线前建议）
- [ ] 为外呼 Webhook 添加 IP 白名单或签名验证
- [ ] 将 `/tmp/*.wav` 音频临时文件改为 OSS/CDN 存储（当前为本地 /tmp）
- [ ] 将机器人会话从内存改为 Redis（当前重启后会话丢失）
- [ ] 配置 HTTPS（呼叫中心回调通常要求 HTTPS）
- [ ] 确认外呼合规：时段限制、频次限制、号码黑名单

---

## API 文档

启动后访问：
- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`

主要端点：

| 端点 | 说明 |
|------|------|
| `POST /api/onboard_session/start` | 开始 Onboarding |
| `POST /api/onboard_session/{id}/message` | Onboarding 对话 |
| `POST /api/onboard_session/{id}/finalize` | 生成 Agent |
| `GET /api/agents` | Agent 列表 |
| `POST /api/agents/{id}/chat/stream` | 流式聊天 |
| `POST /api/robot_call/start` | 触发机器人外呼 |
| `POST /api/tts` | TTS 合成 |
| `GET /health` | 服务健康检查 |

---

## 安全注意事项

- **永远不要提交 `.env` 文件**（已在 `.gitignore` 排除）
- 生产环境启用 HTTPS
- 配置正确的 `CORS_ORIGINS`，不要使用 `*`
- 外呼 Webhook 建议配置 IP 白名单

---

## 许可证

MIT License
