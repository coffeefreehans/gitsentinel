import os
import subprocess
import threading
import time
from typing import Dict, Set

from .config import config_manager
from .notifier import notifier

class BackgroundWatcher:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread = None
        self._last_notified_behind: Dict[str, int] = {}
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()

    def trigger_check_now(self):
        threading.Thread(target=self._check_all_repos, kwargs={"force": True}, daemon=True).start()

    def _run_loop(self):
        # Allow system to finish initial startup
        time.sleep(30)
        while not self._stop_event.is_set():
            interval = config_manager.get("check_interval_seconds", 600)
            auto_fetch = config_manager.get("auto_fetch_remote", False)
            if interval > 0 and auto_fetch:
                self._check_all_repos(force=False)
            # Wait interval or until stop
            self._stop_event.wait(timeout=max(30, interval))

    def _check_all_repos(self, force: bool = False):
        from .repo_manager import repo_manager

        repos = repo_manager.cached_repos.values()
        if not repos:
            repo_manager.scan_directories()
            repos = repo_manager.cached_repos.values()

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "never"
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

        for repo in list(repos):
            if self._stop_event.is_set():
                break

            repo_path = repo.get("path")
            repo_name = repo.get("name")
            if not repo_path or not os.path.exists(repo_path) or not repo.get("has_remote"):
                continue

            try:
                # Fetch remote updates completely silently without any interactive prompt or window popup
                subprocess.run(
                    ["git", "-c", "core.askPass=", "fetch", "--quiet", "--no-tags"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=8,
                    env=env,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                # Check behind count
                res = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD..@{u}"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=env,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if res.returncode == 0 and res.stdout.strip().isdigit():
                    behind_count = int(res.stdout.strip())
                    prev_behind = self._last_notified_behind.get(repo_path, 0)

                    if behind_count > 0 and behind_count != prev_behind:
                        self._last_notified_behind[repo_path] = behind_count
                        # Fire desktop toast & UI notification
                        notifier.notify(
                            title=f"🔔 仓库 [{repo_name}] 发现远程更新",
                            message=f"远程分支有 {behind_count} 个新提交尚未同步，请及时 Pull 拉取！",
                            event_type="remote_update",
                            repo_path=repo_path
                        )
                    elif behind_count == 0:
                        self._last_notified_behind[repo_path] = 0

            except Exception:
                continue

background_watcher = BackgroundWatcher()
