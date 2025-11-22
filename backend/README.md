Voice-to-Agent Backend (FastAPI + Azure)

功能
- 语音转写（Azure Speech STT）
- 从转写文本生成高质量 System Prompt（Markdown；Azure OpenAI Chat Completions）
- 顺手创建 Azure Assistant（Agent）
- 与 Agent 聊天（Assistants Threads/Runs）
- 浏览器端语音用的短期 Speech Token 下发

API
- POST /api/onboard（multipart form-data: file 或 form 字段 audio_url）
- GET  /api/agents?user_id=...
- GET  /api/agents/{id}
- POST /api/agents/{id}/chat
- GET  /api/speech/token

环境变量（backend/.env）
- AZURE_OPENAI_ENDPOINT=https://<your-azure-openai>.openai.azure.com
- AZURE_OPENAI_API_KEY=<your-aoai-key>
- AZURE_OPENAI_API_VERSION=2025-01-01-preview
- AZURE_OPENAI_DEPLOYMENT=gpt-4o
- AZURE_SPEECH_KEY=<your-speech-key>
- AZURE_SPEECH_REGION=australiaeast  # 无空格
- CORS_ORIGINS=http://localhost:5173

本地运行
1) python -m venv .venv && source .venv/bin/activate
2) pip install -r backend/requirements.txt
3) uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

健康检查（可选）
- Azure OpenAI：python backend/scripts/aoai_health.py
- 端到端：python backend/scripts/tts_gen.py 生成 /tmp/onboard_zh.wav → 调 /api/onboard → 再调 /api/agents/{id}/chat

部署（Azure App Service 推荐）
A. 直接部署源码：
- 选择 Python 3.11 运行时
- 启动命令：uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
- 在 App Service 应用设置中配置上方环境变量

B. Docker 部署（backend/Dockerfile 已提供）：
- docker build -t voice-agent-backend:latest ./backend
- docker run --env-file ./backend/.env -p 8000:8000 voice-agent-backend:latest
- 推送至 ACR，并在 App Service 使用容器镜像部署

注意
- 切勿在代码库中提交真实密钥；请使用环境变量/密钥管理器
- Speech 区域建议使用 australiaeast（无空格）
- System Prompt 模板在 backend/app/prompt_templates.py
- 浏览器 STT/TTS：先 GET /api/speech/token 获取短期 token

