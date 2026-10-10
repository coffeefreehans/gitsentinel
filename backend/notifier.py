import os
import sys
import subprocess
import threading
import time
from typing import List, Dict, Any

class Notifier:
    def __init__(self):
        self._history: List[Dict[str, Any]] = []
        self._listeners = []

    def add_listener(self, callback):
        self._listeners.append(callback)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._history[-limit:][::-1]

    def notify(self, title: str, message: str, event_type: str = "info", repo_path: str = None) -> None:
        record = {
            "id": f"notif_{int(time.time()*1000)}",
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "title": title,
            "message": message,
            "type": event_type,  # 'info', 'warning', 'commit', 'remote_update', 'alert'
            "repo_path": repo_path
        }
        self._history.append(record)

        # Notify active listeners (e.g. WebSocket connections)
        for cb in self._listeners:
            try:
                cb(record)
            except Exception:
                pass

        # Send cross-platform Native Desktop Notification asynchronously
        threading.Thread(target=self._send_desktop_notification, args=(title, message), daemon=True).start()

    def _send_desktop_notification(self, title: str, message: str) -> None:
        """Dispatches desktop notification according to host OS"""
        try:
            if sys.platform == "win32":
                self._send_windows_toast(title, message)
            elif sys.platform == "darwin":
                self._send_macos_notification(title, message)
            else:
                self._send_linux_notification(title, message)
        except Exception:
            pass

    def _send_windows_toast(self, title: str, message: str) -> None:
        """Sends native Windows 10/11 Toast notification or NotifyIcon Balloon fallback"""
        import base64

        clean_title = title.replace('"', '""').replace("'", "''").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        clean_msg = message.replace('"', '""').replace("'", "''").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        ps_code = f"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'SilentlyContinue'
$title = "{clean_title}"
$msg = "{clean_msg}"

$shown = $false
try {{
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $template = "<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$msg</text></binding></visual></toast>"
    $xml.LoadXml($template)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    
    # Try standard Windows PowerShell AUMID (universally permitted by Windows 10/11)
    $appId = '{{1AC14E77-02E7-4E5D-B744-24660D505C7C}}\\WindowsPowerShell\\v1.0\\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    $shown = $true
}} catch {{
    $shown = $false
}}

# If Modern Toast failed, fallback to NotifyIcon Balloon Tip (guaranteed to appear in system tray/action center)
if (-not $shown) {{
    try {{
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Shield
        $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
        $notify.BalloonTipTitle = $title
        $notify.BalloonTipText = $msg
        $notify.Visible = $true
        $notify.ShowBalloonTip(4000)
        Start-Sleep -Milliseconds 1500
        $notify.Dispose()
    }} catch {{}}
}}
"""
        try:
            encoded = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=6,
                capture_output=True
            )
        except Exception:
            pass

    def _send_macos_notification(self, title: str, message: str) -> None:
        """Sends native macOS notification center alert via osascript"""
        # Escape quotes for AppleScript string literal
        safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
        safe_msg = message.replace('\\', '\\\\').replace('"', '\\"')
        apple_script = f'display notification "{safe_msg}" with title "{safe_title}" sound name "default"'
        try:
            subprocess.run(
                ["osascript", "-e", apple_script],
                timeout=5,
                capture_output=True
            )
        except Exception:
            pass

    def _send_linux_notification(self, title: str, message: str) -> None:
        """Sends FreeDesktop desktop notification via notify-send"""
        try:
            # Check if notify-send is available in PATH
            subprocess.run(
                ["notify-send", "-a", "GitSentinel", title, message],
                timeout=5,
                capture_output=True
            )
        except Exception:
            pass

notifier = Notifier()
