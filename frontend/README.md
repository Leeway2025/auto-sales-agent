Voice Agent Studio (React + Vite)

Scripts
- npm install
- npm run dev (http://localhost:5173)

Dev proxy
- Vite proxies /api -> http://localhost:8000 (FastAPI)

Pages
- / (Onboard): upload/record audio -> /api/onboard -> show prompt (Markdown) & go to Chat
- /agents: list user agents -> /api/agents?user_id=demo-user
- /chat/:id: text chat + speech (STT/TTS). Toggle streaming recognition.
- /onboard-session: multi-turn onboarding wizard. Collect brand/industry/audience/channels etc step-by-step, then finalize to create Agent.

Speech SDK
- Uses GET /api/speech/token to obtain a short token and region
- STT: recognizeOnceAsync (default) or startContinuousRecognitionAsync (streaming on)
- TTS: zh-CN-XiaoxiaoNeural by default
