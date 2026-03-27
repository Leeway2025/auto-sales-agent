# 部署指南

本文档覆盖三种场景：本地开发、Docker Compose 一键部署（推荐服务器）、以及 T4 GPU 节点的 CosyVoice2 声音克隆服务部署。

---

## 前置要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux (推荐 Ubuntu 22.04) / macOS |
| Python | 3.11+ |
| Node.js | 18+ |
| Docker | 24+ |
| Docker Compose | v2.20+ (`docker compose` 命令) |
| NVIDIA 驱动 | 525+（仅 GPU 节点需要） |
| nvidia-container-toolkit | 最新版（仅 GPU 节点需要） |

---

## 一、环境变量配置

所有密钥统一放在 `backend/.env`，**不要提交到 Git**（已在 `.gitignore` 排除）。

```bash
cp backend/.env.example backend/.env
nano backend/.env   # 填入真实值
```

### 必填

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini        # 已部署的模型名称
AZURE_SPEECH_KEY=your-speech-key
AZURE_SPEECH_REGION=australiaeast          # Speech 资源所在区域
```

### 可选（有默认值）

```env
AZURE_OPENAI_API_VERSION=2024-06-01
CORS_ORIGINS=http://localhost:5173         # 生产环境改为前端域名
AZURE_TTS_VOICE=zh-CN-XiaoxiaoNeural      # Azure TTS 回退音色
COSYVOICE_URL=http://localhost:9880        # Docker Compose 中自动覆盖
COSYVOICE_ENABLED=true
```

---

## 二、本地开发（无 Docker）

### 后端

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
```

Vite 已配置 `/api` → `http://localhost:8000` 代理，开发时无需额外配置。

### CosyVoice2（本地可选）

若需在本地测试声音克隆，参考 [cosyvoice_deployment.md](cosyvoice_deployment.md)。
不需要时在 `backend/.env` 设置 `COSYVOICE_ENABLED=false`，系统将跳过 TTS 功能。

---

## 三、Docker Compose 部署（推荐服务器）

此方式启动三个容器：`frontend`（Nginx）、`backend`（FastAPI）、`cosyvoice`（CosyVoice2 GPU）。

### 1. 克隆仓库并配置环境变量

```bash
git clone https://github.com/Leeway2025/auto-sales-agent.git
cd auto-sales-agent
cp backend/.env.example backend/.env
nano backend/.env   # 填入 AZURE_* 密钥
```

生产环境修改 CORS：

```env
CORS_ORIGINS=http://your-server-ip   # 或实际域名
```

### 2. 首次启动（自动下载 CosyVoice2 模型 ~2GB）

```bash
MODEL_DOWNLOAD=1 docker compose up -d --build
```

模型下载完成后保存在 Docker volume `cosyvoice_models` 中，后续重启无需重新下载。

### 3. 后续启动

```bash
docker compose up -d
```

### 4. 验证服务

```bash
# 后端健康检查
curl http://localhost:8000/health
# 期望: {"status":"ok"}

# CosyVoice 健康检查（模型加载约需 2 分钟）
curl http://localhost:9880/health
# 期望: {"status":"ok","model_loaded":true}

# TTS 集成测试
curl -X POST http://localhost:8000/api/tts \
  -F "text=你好，部署成功" \
  -o /tmp/test.wav && echo "TTS OK"

# 访问前端
open http://localhost   # 或浏览器打开服务器 IP
```

### 5. 查看日志

```bash
docker compose logs -f backend      # 后端日志
docker compose logs -f cosyvoice    # 模型加载日志
docker compose logs -f frontend     # Nginx 访问日志
```

---

## 四、T4 GPU 节点专项配置

### 安装 nvidia-container-toolkit

```bash
# Ubuntu 22.04
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 验证 GPU 可用

```bash
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
```

应输出 T4 的 GPU 信息。

### CosyVoice2 在 T4 上的表现

| 场景 | 首次延迟 | 后续延迟 | 显存占用 |
|------|---------|---------|---------|
| 预设音色 | ~3s | ~1.5s | ~3GB |
| 声音克隆（零样本） | ~5s | ~3s | ~4GB |

T4 显存 16GB，运行 CosyVoice2-0.5B 有充足余量。

### 仅部署 CosyVoice2 服务（单独 GPU 节点）

如果 CosyVoice2 运行在独立 GPU 节点，单独构建和运行：

```bash
# 在 GPU 节点上
docker build -t cosyvoice2-service:latest ./cosyvoice_service

# 首次运行（下载模型）
docker run -d --gpus '"device=0"' \
  -p 9880:9880 \
  -v /data/models:/workspace/models \
  -e MODEL_DOWNLOAD=1 \
  --name cosyvoice \
  cosyvoice2-service:latest

# 后续运行
docker run -d --gpus '"device=0"' \
  -p 9880:9880 \
  -v /data/models:/workspace/models \
  --name cosyvoice \
  cosyvoice2-service:latest
```

然后在 `backend/.env` 中设置：

```env
COSYVOICE_URL=http://<gpu-node-ip>:9880
```

---

## 五、服务端口总览

| 服务 | 端口 | 说明 |
|------|------|------|
| frontend (Nginx) | 80 | 对外访问入口，反向代理 /api |
| backend (FastAPI) | 8000 | REST API + SSE 流式聊天 |
| cosyvoice (TTS) | 9880 | 声音合成微服务，仅内网访问 |

生产环境建议：
- 在 80/443 前加 Nginx 或 CDN，配置 HTTPS
- 9880 端口**不对公网开放**，仅 backend 容器内网访问

---

## 六、常见问题

**CosyVoice 容器一直重启？**
通常是模型未下载完成。查看日志：`docker compose logs cosyvoice`，确认是否有下载错误，或手动设置 `MODEL_DOWNLOAD=1` 重新拉起。

**后端报 `CosyVoice is disabled`？**
检查 `backend/.env` 中 `COSYVOICE_ENABLED=true` 且 `COSYVOICE_URL` 指向正确地址。

**Azure Speech 报 401？**
确认 `AZURE_SPEECH_KEY` 和 `AZURE_SPEECH_REGION` 与 Azure Portal 中的资源匹配。Region 格式如 `australiaeast`（无空格，全小写）。

**前端空白页？**
检查 `CORS_ORIGINS` 是否包含了前端访问的实际地址。
