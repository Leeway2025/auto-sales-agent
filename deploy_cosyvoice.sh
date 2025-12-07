#!/bin/bash

#
# 使用 venv 在本地全自动部署 CosyVoice 的脚本。
#

# 如果任何命令失败，立即退出脚本
set -e

echo "### 正在使用 Python 自带的 venv 部署 CosyVoice... ###"
echo

# --- 步骤 1: 安装 pynini 的系统级依赖 ---
echo "### 步骤 1: 准备 pynini 的系统依赖... ###"
# pynini 需要 C++ 编译环境和 OpenFST 库
if [[ "$(uname)" == "Darwin" ]]; then
    # macOS 系统
    echo "检测到 macOS。正在检查 Homebrew..."
    if ! command -v brew &> /dev/null; then
        echo "错误: 未找到 Homebrew。请先访问 https://brew.sh/ 安装 Homebrew。"
        exit 1
    fi
    echo "正在使用 Homebrew 安装 openfst 和 pkg-config (pynini 依赖)..."
    # 如果已安装，brew 会自动跳过
    brew install openfst pkg-config
    # pynini 编译时需要 C++17 标准
    export CXXFLAGS="-std=c++17"
    echo "macOS 系统依赖已就绪。"

elif [[ "$(uname)" == "Linux" ]]; then
    # Linux (Debian/Ubuntu) 系统
    echo "检测到 Linux。正在使用 apt 安装 build-essential 和 libfst-dev..."
    echo "此步骤可能需要您输入管理员密码。"
    sudo apt-get update
    sudo apt-get install -y build-essential libfst-dev
    echo "Linux 系统依赖已就绪。"
else
    echo "警告: 未知操作系统。脚本将继续，但 'pip install pynini' 步骤可能会失败。"
    echo "如果失败，请手动为您的系统安装 OpenFST C++ 库。"
fi
echo

# --- 步骤 2: 准备代码仓库 ---
echo "### 步骤 2: 准备 CosyVoice 代码仓库... ###"
if [ ! -d "CosyVoice" ]; then
    echo "克隆仓库: https://github.com/FunAudioLLM/CosyVoice.git"
    git clone https://github.com/FunAudioLLM/CosyVoice.git
fi
cd CosyVoice
echo "更新 Git 子模块..."
git submodule update --init --recursive
echo "仓库已就绪。"
echo

# --- 步骤 3: 创建并激活 venv 虚拟环境 ---
VENV_DIR="venv"
echo "### 步骤 3: 在 ./$VENV_DIR 创建 Python 3.11 虚拟环境... ###"
if [ ! -d "$VENV_DIR" ]; then
    # 强制使用 python3.11，这是解决 torch 安装问题的关键
    if ! command -v python3.11 &> /dev/null; then
        echo "错误: 未找到 python3.11 命令。"
        echo "请先安装 Python 3.11 (例如: brew install python@3.11)，然后再运行此脚本。"
        exit 1
    fi
    python3.11 -m venv $VENV_DIR
fi
echo "激活虚拟环境..."
source $VENV_DIR/bin/activate
echo "虚拟环境已激活。"
echo

# --- 步骤 4: 安装 Python 依赖 ---
echo "### 步骤 4: 安装 Python 依赖项... ###"
echo "正在使用 pip 安装 pynini..."
pip install pynini
echo "正在使用 pip 安装其余依赖..."
echo "优先单独安装 torch..."
pip install torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
echo "所有 Python 依赖项已安装。"
echo

# --- 步骤 5: 下载预训练模型 ---
echo "### 步骤 5: 下载预训练模型... ###"
echo "这个过程可能需要一些时间，具体取决于你的网络状况。"
python3 -c "
import os
from modelscope.hub.api import HubApi
from modelscope.hub.snapshot_download import snapshot_download

# 从环境变量读取 Token 并登录
token = os.getenv('MODELSCOPE_API_TOKEN')
if not token:
    print('警告: 未找到 MODELSCOPE_API_TOKEN 环境变量。')
    print('将尝试匿名下载，如果失败，请设置该环境变量。')
else:
    api = HubApi()
    api.login(token)
    print('已使用 MODELSCOPE_API_TOKEN 登录。')

models = [
    'iic/CosyVoice2-0.5B'
]
cache_dir = '.'
print('开始下载模型...')
for model_id in models:
    print(f'  -> 正在下载 {model_id}...')
    model_path = os.path.join(cache_dir, model_id.split('/')[1])
    if os.path.exists(model_path):
        print(f'     模型 {model_id} 已存在, 跳过下载。')
    else:
        snapshot_download(model_id, cache_dir=cache_dir)
        print(f'     模型 {model_id} 下载完成。')
print('所有模型已准备就绪。')
"
echo "模型下载流程结束。"
echo

# --- 步骤 6: 启动服务 ---
echo "### 步骤 6: 启动 CosyVoice FastAPI 服务... ###"
echo "服务将运行在: http://0.0.0.0:9880"
echo "你可以随时按 CTRL+C 来停止服务。"
echo
python webui.py