@echo off
title GitSentinel 哨兵系统
cd /d "%~dp0"
echo ========================================================
echo   GitSentinel - Git 统一管理与安全提交拦截系统
echo ========================================================
echo.
echo 正在启动 GitSentinel 服务 (托盘驻留模式)...
echo 控制台地址: http://127.0.0.1:28888
echo.
python sentinel.py tray
pause
