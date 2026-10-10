import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure UTF-8 output encoding across Windows/macOS/Linux
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from backend.repo_manager import repo_manager
from backend.background_watcher import background_watcher
from backend.notifier import notifier

PORT = 28888
HOST = "127.0.0.1"

def run_server(auto_open_browser: bool = False):
    from backend.app import app
    print(f"\n=======================================================")
    print(f"  🛡️ GitSentinel - Git 统一管理与安全提交拦截系统")
    print(f"  🌐 控制面板地址: http://{HOST}:{PORT}")
    print(f"=======================================================\n")
    if auto_open_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.2), webbrowser.open(f"http://{HOST}:{PORT}")),
            daemon=True
        ).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

def run_tray():
    try:
        import pystray
        from PIL import Image
    except ImportError:
        print("[GitSentinel] 未安装 pystray 或 Pillow，切换为普通控制台模式启动。")
        run_server(auto_open_browser=True)
        return

    # Start server in background thread
    server_thread = threading.Thread(target=run_server, args=(False,), daemon=True)
    server_thread.start()

    # Wait for server to boot, then open browser
    def open_web():
        time.sleep(1.2)
        webbrowser.open(f"http://{HOST}:{PORT}")

    threading.Thread(target=open_web, daemon=True).start()

    # Load shield icon for system tray
    icon_path = PROJECT_ROOT / "assets" / "icon.png"
    if icon_path.exists():
        try:
            img = Image.open(icon_path).resize((64, 64))
        except Exception:
            img = Image.new("RGBA", (64, 64), color=(15, 23, 42, 255))
    else:
        img = Image.new("RGBA", (64, 64), color=(15, 23, 42, 255))

    def on_open_dashboard(icon, item):
        webbrowser.open(f"http://{HOST}:{PORT}")

    def on_toggle_global(icon, item):
        current = repo_manager.is_global_hooks_enabled()
        repo_manager.set_global_hooks(not current)
        notifier.notify(
            title="🛡️ 全局拦截模式变更",
            message="全局 Git 提交拦截已开启" if not current else "全局 Git 提交拦截已关闭",
            event_type="info"
        )

    def on_check_updates(icon, item):
        background_watcher.trigger_check_now()
        notifier.notify("🔄 检查远程更新", "已触发后台远程仓库更新轮询检测", "info")

    def on_test_toast(icon, item):
        notifier.notify("🔔 GitSentinel 提示", "系统桌面通知工作正常！", "info")

    def on_exit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("🛡️ GitSentinel 控制台", on_open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "⚡ 全局提交前拦截",
            on_toggle_global,
            checked=lambda item: repo_manager.is_global_hooks_enabled()
        ),
        pystray.MenuItem("🔄 立即检测远程更新", on_check_updates),
        pystray.MenuItem("🔔 发送测试通知", on_test_toast),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("❌ 退出 GitSentinel", on_exit)
    )

    icon = pystray.Icon("GitSentinel", img, "GitSentinel 哨兵", menu)
    notifier.notify(
        title="🛡️ GitSentinel 哨兵已就绪",
        message=f"已在后台启动并驻留托盘，控制面板: http://{HOST}:{PORT}",
        event_type="info"
    )
    icon.run()

def run_post_commit_notify(args):
    """Handles post-commit notification triggered by git hook"""
    repo_name = args[0] if len(args) > 0 else "Git Repo"
    commit_hash = args[1] if len(args) > 1 else ""
    commit_msg = args[2] if len(args) > 2 else ""
    repo_path = args[3] if len(args) > 3 else os.getcwd()
    notifier.notify(
        title="✅ Git 提交完成",
        message=f"[{repo_name}] {commit_hash}: {commit_msg}",
        event_type="commit",
        repo_path=repo_path
    )
    sys.exit(0)

def main():
    # If invoked with subcommands from git hook (e.g. intercept, post-commit-notify)
    if len(sys.argv) > 1 and sys.argv[1] == "intercept":
        from interceptor.interceptor_gui import main as interceptor_main
        # Forward remaining args to interceptor
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        interceptor_main()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "post-commit-notify":
        run_post_commit_notify(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(description="GitSentinel Desktop App & CLI Manager")
    parser.add_argument(
        "action",
        nargs="?",
        default="app",
        choices=["app", "start", "tray", "server", "headless", "enable-global", "disable-global", "status"],
        help="Action to perform: 'app' (Native Desktop GUI), 'tray' (Tray+Browser), 'start'/'server' (Web Server), etc."
    )
    args = parser.parse_args()

    if args.action == "app":
        from desktop_app import main as app_main
        app_main()
    elif args.action == "start":
        run_server(auto_open_browser=True)
    elif args.action == "server" or args.action == "headless":
        run_server(auto_open_browser=False)
    elif args.action == "tray":
        run_tray()
    elif args.action == "enable-global":
        res = repo_manager.set_global_hooks(True)
        print(f"Global pre-commit hooks enabled: {res}")
    elif args.action == "disable-global":
        res = repo_manager.set_global_hooks(False)
        print(f"Global pre-commit hooks disabled: {res}")
    elif args.action == "status":
        enabled = repo_manager.is_global_hooks_enabled()
        print(f"GitSentinel Global Intercept Mode: {'ENABLED' if enabled else 'DISABLED'}")

if __name__ == "__main__":
    main()
