# CosyVoice2 部署指南

平台的所有语音合成功能依赖 CosyVoice2。下面给出两种常用方式：使用仓库自带脚本一键部署，或手动部署。

## 方式一：使用脚本（推荐本地快速体验）
在仓库根目录执行：
```bash
bash deploy_cosyvoice.sh
```
脚本会：
1) 安装 pynini 所需的系统依赖（macOS 用 brew，Linux 用 apt）。  
2) 克隆 https://github.com/FunAudioLLM/CosyVoice 并初始化子模块。  
3) 创建 Python 3.11 虚拟环境并安装依赖（包含 torch CPU 版）。  
4) 从 ModelScope 下载 `iic/CosyVoice2-0.5B` 模型（需要 `MODELSCOPE_API_TOKEN`，否则尝试匿名）。  
5) 启动 CosyVoice FastAPI 服务（默认端口 9880）。

> 若你缺少 Python 3.11，请先安装（如 `brew install python@3.11` 或相应包管理器）。

## 方式二：手动部署（自定义环境/路径）
1) 安装依赖：C++ 编译环境 + OpenFST（如 `sudo apt-get install build-essential libfst-dev`）。  
2) 克隆并初始化子模块：  
```bash
git clone https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
git submodule update --init --recursive
```
3) 创建并激活 Python 3.11 venv，安装依赖：  
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install pynini
pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```
4) 下载模型（推荐设置 `MODELSCOPE_API_TOKEN`）：  
```bash
python -c "from modelscope.hub.snapshot_download import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B')"
```
5) 启动服务（默认端口 9880）：  
```bash
python runtime/python/fastapi/auto_server.py
# 如需指定模型或端口：
# COSYVOICE_MODEL_DIR=pretrained_models/CosyVoice2-0.5B COSYVOICE_PORT=9880 python runtime/python/fastapi/auto_server.py
```

## 运行后验证
1) 确认 `backend/.env` 配置：`COSYVOICE_URL=http://localhost:9880`，`COSYVOICE_ENABLED=true`。  
2) 后端启动后，调用 `GET http://localhost:8000/api/tts/health` 应返回 `{"healthy": true, "enabled": true, "url": "http://localhost:9880"}`。  
3) 使用接口验证：
```bash
curl -X POST http://localhost:8000/api/tts \
  -F "text=你好，CosyVoice" \
  -o /tmp/out.wav
```
若 `/tmp/out.wav` 非空且可播放，说明 TTS 正常。
