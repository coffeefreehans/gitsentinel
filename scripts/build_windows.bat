@echo off
title GitSentinel Windows 打包构建器
cd /d "%~dp0\.."

echo ========================================================
echo   🛡️ GitSentinel - Windows 桌面应用一键打包
echo ========================================================
echo.

echo [1/3] 检查 Python 与依赖...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 错误: 未检测到 Python，请确认已安装并添加到 PATH。
    pause
    exit /b 1
)

echo [2/3] 安装/更新 PyInstaller 打包依赖...
pip install pyinstaller pillow pystray pywebview --quiet

echo [3/3] 开始打包应用...
python package.py

echo.
echo ========================================================
echo 构建完成！可前往 dist\ 目录查看产物：
echo - 便携独立程序目录: dist\GitSentinel\GitSentinel.exe
echo - 发布压缩包: dist\GitSentinel-Windows-x64.zip
echo ========================================================
pause
