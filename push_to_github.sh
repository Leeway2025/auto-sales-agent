#!/bin/bash

# GitHub 推送脚本（使用本地 token 文件）
# 用户: leewaylicn

set -e  # 遇到错误立即退出

echo "🚀 准备推送到 GitHub..."
echo ""

# 检查 token 文件
TOKEN_FILE=".github_token"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "❌ 错误: 找不到 $TOKEN_FILE 文件"
    echo ""
    echo "请创建 $TOKEN_FILE 文件并添加你的 GitHub token："
    echo "GITHUB_TOKEN=ghp_your_token_here"
    echo ""
    exit 1
fi

# 读取 token
source "$TOKEN_FILE"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ 错误: $TOKEN_FILE 中没有找到 GITHUB_TOKEN"
    exit 1
fi

echo "✅ 已读取 GitHub token"

# 询问仓库名称
echo ""
echo "📝 请输入仓库名称（例如：auto-sales-agent）："
read REPO_NAME

if [ -z "$REPO_NAME" ]; then
    echo "❌ 仓库名称不能为空"
    exit 1
fi

# 检查是否已经添加了 remote
if git remote | grep -q origin; then
    echo "⚠️  Remote 'origin' 已存在，将更新为新仓库"
    git remote remove origin
fi

# 添加 remote（使用 token）
REPO_URL="https://${GITHUB_TOKEN}@github.com/leewaylicn/${REPO_NAME}.git"
git remote add origin "$REPO_URL"
echo "✅ 已添加 remote"

# 设置主分支
git branch -M main

echo ""
echo "📋 推送前检查："
echo "   - 用户: leewaylicn"
echo "   - 仓库: $REPO_NAME"
echo "   - 分支: main"
echo ""

# 最终确认
read -p "确认推送到 GitHub? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 取消推送"
    git remote remove origin
    exit 0
fi

echo ""
echo "🚀 开始推送..."
echo ""

# 推送
if git push -u origin main; then
    echo ""
    echo "✅ 推送成功！"
    echo "🎉 访问你的仓库: https://github.com/leewaylicn/$REPO_NAME"
    echo ""
    
    # 清理 remote 中的 token（安全起见）
    git remote set-url origin "https://github.com/leewaylicn/${REPO_NAME}.git"
    echo "🔒 已清理 remote URL 中的 token"
else
    echo ""
    echo "❌ 推送失败"
    echo ""
    echo "可能的原因："
    echo "1. GitHub 仓库尚未创建"
    echo "2. Token 权限不足（需要 'repo' 权限）"
    echo "3. Token 已过期"
    echo "4. 网络连接问题"
    echo ""
    echo "请检查后重试"
    
    # 清理
    git remote remove origin
    exit 1
fi
