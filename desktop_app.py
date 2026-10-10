import os
import sys
import threading
import time
import socket
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from backend.repo_manager import repo_manager
from backend.background_watcher import background_watcher
from backend.notifier import notifier

DEFAULT_PORT = 28888
HOST = "127.0.0.1"

def find_available_port(start_port: int = DEFAULT_PORT) -> int:
    """Finds an available TCP port starting from start_port"""
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((HOST, port)) != 0:
                return port
    return start_port

def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((HOST, port)) == 0:
                return True
        time.sleep(0.1)
    return False

def run_uvicorn_server(port: int):
    from backend.app import app
    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()

def start_tray(window, app_url: str, port: int):
    """Starts background system tray using pystray"""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return None

    icon_path = PROJECT_ROOT / "assets" / "icon.png"
    if icon_path.exists():
        try:
            img = Image.open(icon_path).resize((64, 64))
        except Exception:
            img = Image.new("RGBA", (64, 64), color=(15, 23, 42, 255))
    else:
        img = Image.new("RGBA", (64, 64), color=(15, 23, 42, 255))

    def on_show_window(icon, item):
        if window:
            try:
                window.restore()
                window.show()
            except Exception:
                import webbrowser
                webbrowser.open(app_url)
        else:
            import webbrowser
            webbrowser.open(app_url)

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
        if window:
            try:
                window.destroy()
            except Exception:
                pass
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("🛡️ 打开 GitSentinel 控制面板", on_show_window, default=True),
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

    icon = pystray.Icon("GitSentinel", img, "GitSentinel 哨兵系统", menu)
    tray_thread = threading.Thread(target=icon.run, daemon=True)
    tray_thread.start()
    return icon

def main():
    port = find_available_port(DEFAULT_PORT)
    app_url = f"http://{HOST}:{port}"

    # 1. Start FastAPI server in background thread
    server_thread = threading.Thread(target=run_uvicorn_server, args=(port,), daemon=True)
    server_thread.start()

    # 2. Wait for server to become responsive
    if not wait_for_server(port):
        print(f"[GitSentinel] 警告: 后端服务在端口 {port} 启动较慢，继续尝试打开界面...")

    # 3. Try launching native desktop window with pywebview
    webview_available = False
    try:
        import webview
        webview_available = True
    except ImportError:
        webview_available = False

    notifier.notify(
        title="🛡️ GitSentinel 哨兵已就绪",
        message=f"GitSentinel 桌面应用已启动，正在守护全系统 Git 仓库与提交安全",
        event_type="info"
    )

    if webview_available:
        try:
            window = webview.create_window(
                title="GitSentinel - Git 统一管理与安全提交拦截系统",
                url=app_url,
                width=1240,
                height=820,
                min_size=(960, 640),
                background_color="#0f172a",
                text_select=True,
                confirm_close=False
            )

            # Start tray in background
            start_tray(window, app_url, port)

            # Start webview event loop (blocks main thread until window closed)
            webview.start(debug=False)
            os._exit(0)
        except Exception as e:
            print(f"[GitSentinel] 原生窗口创建失败 ({e})，正在降级为浏览器托盘模式...")

    # Fallback to browser + tray mode
    import webbrowser
    start_tray(None, app_url, port)
    time.sleep(1.0)
    webbrowser.open(app_url)

    print(f"\n=======================================================")
    print(f"  🛡️ GitSentinel - Git 统一管理与安全提交拦截系统")
    print(f"  🌐 控制面板地址: {app_url}")
    print(f"=======================================================\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        os._exit(0)

if __name__ == "__main__":
    main()
