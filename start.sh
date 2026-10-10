#!/usr/bin/env bash
# GitSentinel Startup Script for macOS and Linux
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "======================================================="
echo "  🛡️ GitSentinel - Git 统一管理与安全提交拦截系统"
echo "======================================================="

# Detect Python 3
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "❌ 错误: 未检测到 Python 运行环境，请先安装 Python 3.10+。"
    exit 1
fi

echo "正在启动 GitSentinel 桌面应用..."
"$PYTHON_CMD" sentinel.py "$@"
