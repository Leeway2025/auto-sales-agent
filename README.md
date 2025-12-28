# Auto Sales Agent Platform

[![GitHub](https://img.shields.io/badge/GitHub-leewaylicn%2Fauto--sales--agent-blue?logo=github)](https://github.com/leewaylicn/auto-sales-agent)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/react-18-61dafb.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com/)

一个基于 LLM 的智能销售 Agent 创建和管理平台，支持语音交互、声音克隆和流式对话。

> 🎯 **核心亮点**: LLM 驱动的对话式 Onboarding + 声音模板克隆 + 毫秒级流式响应

## ✨ 核心功能

### 1. LLM 驱动的 Onboarding 向导
- 🤖 智能对话式信息收集
- 📝 自动提取品牌、行业、受众等关键信息
- 🎯 动态生成个性化销售话术
- 🎙️ **声音模板录制**：录制 5 秒声音，Agent 将用你的声音说话

### 2. 高性能聊天系统
- ⚡ **流式响应**：首字延迟 < 1 秒
- 🚀 **Chat Completions API**：响应时间从 5-8 秒降至 4 秒
- 💬 实时打字效果
- 📜 自动对话历史管理

### 3. CosyVoice2 语音合成
- 🎤 使用 CosyVoice2 生成语音（默认输出 WAV）
- 🔊 支持声音克隆：可使用 onboarding 时录制的声音模板
- 🌐 多语言支持

## 🏗️ 技术架构

### 后端
- **框架**: FastAPI (Python 3.10+)
- **LLM**: Azure OpenAI (gpt-4o)
- **TTS**: CosyVoice2（必需，用于所有语音合成）
- **API 设计**: RESTful + SSE (Server-Sent Events)

### 前端
- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **UI 库**: Material-UI (MUI)
- **路由**: React Router v6

## 📁 项目结构

```
auto/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 主应用
│   │   ├── azure_clients.py     # Azure 服务封装
│   │   ├── cosyvoice_client.py  # CosyVoice2 客户端
│   │   └── prompt_templates.py  # Prompt 模板
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── OnboardSession.tsx  # Onboarding 向导
│   │   │   ├── Agents.tsx          # Agent 列表
│   │   │   └── Chat.tsx            # 聊天界面
│   │   ├── hooks/
│   │   │   ├── useSpeechSDK.ts     # Azure Speech SDK
│   │   │   └── useVoiceClone.ts    # 声音克隆
│   │   └── api/index.ts            # API 服务
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 🚀 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+
- CosyVoice2 服务（默认 `http://localhost:9880`，设置 `COSYVOICE_URL`）
- Azure OpenAI 账号
- Azure Speech Services 账号

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. 配置后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 Azure 凭证
```

**backend/.env** 示例：
```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_API_VERSION=2025-01-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-4o

AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=australiaeast

CORS_ORIGINS=http://localhost:5173

# CosyVoice2 (可选)
COSYVOICE_URL=http://localhost:9880
COSYVOICE_ENABLED=false
```

### 3. 启动后端

```bash
cd backend
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端将在 `http://localhost:8000` 启动

### 4. 配置前端

```bash
cd frontend

# 安装依赖
npm install
```

### 5. 启动前端

```bash
npm run dev
```

前端将在 `http://localhost:5173` 启动

## 📖 使用指南

### 创建 Agent

1. 访问 `http://localhost:5173/onboard-session`
2. 与 Interviewer Agent 对话，提供品牌信息
3. 等待 `[DONE]` 标记出现
4. **（可选）点击"录制声音"按钮**，录制 5 秒声音模板
5. 点击"确认生成"创建 Agent

### 与 Agent 聊天

1. 访问 `http://localhost:5173/agents`
2. 点击任意 Agent 的"聊天"按钮
3. 开始对话（支持流式响应）

## 🎯 性能优化

### 已实现的优化

| 优化项 | 优化前 | 优化后 | 提升 |
|--------|--------|--------|------|
| **聊天响应** | 5-8 秒 | 4 秒 | 20-50% |
| **首字延迟** | 4 秒 | < 1 秒 | 75% |
| **API 调用** | 7-14 次 | 1 次 | 7-14x |

### 优化技术
- ✅ Chat Completions API 替换 Assistants API
- ✅ Server-Sent Events (SSE) 流式响应
- ✅ 内存对话历史管理
- ✅ 自动历史裁剪（保留最近 20 条）

## 🔧 CosyVoice2 部署（必需用于 TTS）

平台的所有 TTS 均由 CosyVoice2 提供。请参考 [CosyVoice2 部署指南](docs/cosyvoice_deployment.md) 或自行在本地/服务器启动 CosyVoice2 服务，并在 `backend/.env` 配置 `COSYVOICE_URL` 与 `COSYVOICE_ENABLED=true`。快速一键启动（A10 等新机）可查看 [A10 Quickstart](docs/quickstart_a10.md)。

简要步骤：
1. 克隆 CosyVoice2 仓库
2. 下载模型
3. 运行 FastAPI 服务（端口 9880）
4. 配置 `COSYVOICE_ENABLED=true`

## 🐳 Docker 部署

### 后端

```bash
cd backend
docker build -t auto-backend .
docker run -d \
  --name auto-backend \
  --env-file .env \
  -p 8000:8000 \
  auto-backend
```

### 前端

```bash
cd frontend
npm run build

# 使用 nginx 托管
docker run -d \
  --name auto-frontend \
  -v $(pwd)/dist:/usr/share/nginx/html \
  -p 80:80 \
  nginx:alpine
```

## 📊 API 文档

启动后端后访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 主要端点

- `POST /api/onboard_session/start` - 开始 onboarding
- `POST /api/onboard_session/{id}/message` - 发送消息
- `POST /api/onboard_session/{id}/voice_template` - 上传声音模板
- `POST /api/onboard_session/{id}/finalize` - 生成 Agent
- `GET /api/agents` - 获取 Agent 列表
- `POST /api/agents/{id}/chat` - 与 Agent 聊天
- `POST /api/agents/{id}/chat/stream` - 流式聊天

## 🔐 安全注意事项

- ⚠️ **永远不要提交 `.env` 文件**
- 🔑 使用 Azure Key Vault 管理生产环境密钥
- 🌐 配置正确的 CORS 源
- 🔒 在生产环境启用 HTTPS

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📞 联系方式

如有问题，请提交 Issue 或联系维护者。

---

**Built with ❤️ using Azure OpenAI, FastAPI, and React**
