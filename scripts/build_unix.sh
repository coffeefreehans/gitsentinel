#!/usr/bin/env bash
# GitSentinel macOS & Linux Packaging Script
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "======================================================="
echo "  🛡️ GitSentinel - macOS & Linux 桌面应用一键打包"
echo "======================================================="

# Detect Python 3
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "❌ 错误: 未检测到 Python 运行环境。"
    exit 1
fi

echo "[1/3] 检查并安装打包必备依赖..."
"$PYTHON_CMD" -m pip install pyinstaller pillow pystray pywebview --quiet

echo "[2/3] 生成多分辨率图标资产..."
"$PYTHON_CMD" scripts/generate_icons.py

echo "[3/3] 运行自动化打包流水线..."
"$PYTHON_CMD" package.py

echo "======================================================="
echo "✅ 构建完成！可在 dist/ 目录下查看编译产物。"
echo "======================================================="
