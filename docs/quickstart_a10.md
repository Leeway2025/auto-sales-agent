# 新机器（A10）一键启动指南

适用场景：在新 GPU 机器（如 A10）快速拉起本项目（前后端 + CosyVoice）。假设已开放 80/443（可选）和内部端口 8000/9880。

## 1. 克隆仓库
```bash
git clone https://github.com/Leeway2025/auto-sales-agent.git
cd auto-sales-agent
```

## 2. 准备环境变量（解密 .env）
仓库附带 `backend/.env.enc`（AES-256-CBC 对称加密）。解密生成 `backend/.env`：
```bash
# 提前准备口令（请从安全渠道获取）
openssl enc -d -aes-256-cbc -pbkdf2 -in backend/.env.enc -out backend/.env
```
> 口令未写入仓库，请向管理员获取。请勿将解密后的 `backend/.env` 提交到 git。

## 3. 部署/启动 CosyVoice
推荐使用仓库脚本（CPU 版，默认端口 9880）：
```bash
bash deploy_cosyvoice.sh
```
- 会克隆 CosyVoice、初始化子模块、创建 venv、安装依赖并下载模型。
- GPU 环境如需自定义 torch/cuda 版本，可在 CosyVoice 目录手动调整依赖后再启动。
- 如已有 CosyVoice 服务，直接在 `backend/.env` 设置 `COSYVOICE_URL` 指向它，并确保 `COSYVOICE_ENABLED=true`。

## 4. 启动后端（及 CosyVoice）
项目根目录提供一键脚本：
```bash
./start_services.sh
```
- 后端：监听 127.0.0.1:8000
- CosyVoice：若检测到 `CosyVoice/venv`，将自动启动到 9880
- 日志：`run/backend.log`、`run/cosyvoice.log`

## 5. 前端/代理
- 仓库已包含 `frontend/dist`，可直接用 nginx 指向该目录，并将 `/api/` 反代到 `http://127.0.0.1:8000`。
- 若需重新构建前端：
```bash
cd frontend
npm i
npm run build
```

## 6. 验证
- 后端健康：`curl -k https://<your-domain>/health` 或 `curl http://127.0.0.1:8000/health`
- 语音 token：`curl -k https://<your-domain>/api/speech/token`
- CosyVoice：`curl http://127.0.0.1:8000/api/tts/health`

## 7. TLS/域名（可选）
- 准备域名解析到服务器 IP，80/443 开放。
- 申请证书（例：Let’s Encrypt）并在 nginx 中配置 80 -> 301/HTTPS，443 反代 `/api/` 到 8000，静态根设为 `frontend/dist`。

## 8. 常见问题
- `api/speech/token` 404：检查 nginx 代理是否保留 `/api` 前缀；配置应为 `proxy_pass http://127.0.0.1:8000;`（无尾斜杠）。
- TTS 失败：确认 CosyVoice 服务健康且 `COSYVOICE_URL` 可达；`COSYVOICE_ENABLED=true`；查看 `run/cosyvoice.log`。
- 推流聊天异常：核对 Azure OpenAI 配置 (`AZURE_OPENAI_*`) 是否正确，网络是否可达 Azure。
