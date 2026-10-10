import hashlib
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import config_manager
from .key_manager import key_manager

class RepoManager:
    def __init__(self):
        self.cached_repos: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def get_repo_id(path: str) -> str:
        norm = os.path.normpath(path).lower()
        return hashlib.md5(norm.encode("utf-8")).hexdigest()[:12]

    def scan_directories(self) -> List[Dict[str, Any]]:
        monitored_paths = config_manager.get("monitored_paths", [str(Path.home())])
        scan_depth = config_manager.get("scan_depth", 6)
        manual_repos = config_manager.get("manual_repos", [])

        found_paths = set()

        # Add manual repos
        for p in manual_repos:
            if os.path.exists(os.path.join(p, ".git")):
                found_paths.add(os.path.normpath(p))

        ignore_dirs = {
            "node_modules", ".vscode", ".idea", "venv", ".venv", "env",
            "__pycache__", "dist", "build", "target", "bin", "obj", "out",
            "appdata", ".cache", "windows", "program files", "program files (x86)",
            "programdata", "$recycle.bin", "system volume information",
            ".npm", ".cargo", ".rustup", ".nuget", ".gradle", ".m2", ".android",
            ".gemini", "downloads", "templates", "leidian", "ndk-r27b-extract",
            "mineradiocache", ".pnpm-store", ".deploy", "temp",
            ".marketplace-plugin-source-staging"
        }

        # Scan monitored directories
        for base in monitored_paths:
            if not os.path.exists(base):
                continue
            base_norm = os.path.normpath(base)
            base_parts_len = len(Path(base_norm).parts)

            for root, dirs, files in os.walk(base_norm, topdown=True):
                current_parts_len = len(Path(root).parts)
                depth = current_parts_len - base_parts_len

                # Check if current directory is a git repo
                if ".git" in dirs:
                    found_paths.add(os.path.normpath(root))
                    # Remove .git so we do not traverse internal git object database
                    # but DO NOT clear dirs, allowing nested projects/monorepos to be discovered
                    dirs.remove(".git")

                if depth >= scan_depth:
                    dirs.clear()  # Stop going deeper
                    continue

                # Prune common heavy, system or cache directories
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in ignore_dirs and not d.startswith("$")
                ]

        # Use ThreadPoolExecutor to query repository status in parallel for high speed
        results = []
        with ThreadPoolExecutor(max_workers=16) as executor:
            raw_results = list(executor.map(self.get_repo_status, sorted(list(found_paths))))

        for status in raw_results:
            if status:
                results.append(status)
                self.cached_repos[status["id"]] = status

        return results

    def get_repo_status(self, repo_path: str) -> Optional[Dict[str, Any]]:
        norm_path = os.path.normpath(repo_path)
        git_dir = os.path.join(norm_path, ".git")
        if not os.path.exists(git_dir):
            return None

        repo_id = self.get_repo_id(norm_path)
        repo_name = os.path.basename(norm_path)

        def _run_git(args: List[str], timeout: int = 6) -> str:
            try:
                res = subprocess.run(
                    ["git"] + args,
                    cwd=norm_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                return (res.stdout or "").strip()
            except Exception:
                return ""

        # 1. Query porcelain branch and working tree status in one combined call
        res_st = _run_git(["status", "--porcelain", "-b"], timeout=6)
        st_lines = res_st.splitlines() if res_st else []

        branch = ""
        tracking = ""
        ahead = 0
        behind = 0
        staged_files = []
        unstaged_files = []
        untracked_files = []

        if st_lines:
            header = st_lines[0]
            if header.startswith("## "):
                hdr = header[3:]
                if "No commits yet on " in hdr:
                    branch = hdr.replace("No commits yet on ", "").strip()
                elif "Initial commit on " in hdr:
                    branch = hdr.replace("Initial commit on ", "").strip()
                elif "HEAD (no branch)" in hdr:
                    head_commit = _run_git(["rev-parse", "--short", "HEAD"])
                    branch = f"HEAD ({head_commit})" if head_commit else "detached"
                else:
                    parts = hdr.split("...")
                    branch = parts[0].strip()
                    if len(parts) > 1:
                        rem_part = parts[1]
                        m = re.match(r'([^\s]+)(?:\s*\[(.*)\])?', rem_part)
                        if m:
                            tracking = m.group(1)
                            counts = m.group(2) or ""
                            ma = re.search(r'ahead (\d+)', counts)
                            mb = re.search(r'behind (\d+)', counts)
                            if ma:
                                ahead = int(ma.group(1))
                            if mb:
                                behind = int(mb.group(1))

            for line in st_lines[1:]:
                if len(line) < 3:
                    continue
                idx = line[0]
                wt = line[1]
                file_name = line[3:].strip()
                if idx in ["M", "A", "D", "R", "C"]:
                    staged_files.append({"status": idx, "file": file_name})
                if wt in ["M", "D"]:
                    unstaged_files.append({"status": wt, "file": file_name})
                if idx == "?" and wt == "?":
                    untracked_files.append(file_name)

        if not branch:
            branch = _run_git(["branch", "--show-current"])
            if not branch:
                head_commit = _run_git(["rev-parse", "--short", "HEAD"])
                branch = f"HEAD ({head_commit})" if head_commit else "empty"

        # 2. Last commit
        last_commit_raw = _run_git(["log", "-1", "--format=%H%n%h%n%an%n%ae%n%ar%n%s"], timeout=5)
        last_commit = None
        if last_commit_raw:
            parts = last_commit_raw.splitlines()
            if len(parts) >= 6:
                last_commit = {
                    "full_hash": parts[0],
                    "short_hash": parts[1],
                    "author_name": parts[2],
                    "author_email": parts[3],
                    "relative_date": parts[4],
                    "message": parts[5]
                }

        # 3. Read remotes (try fast reading .git/config first)
        remotes = []
        cfg_path = os.path.join(norm_path, ".git", "config")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m_remotes = re.findall(r'\[remote "([^"]+)"\][^\[]*?url\s*=\s*([^\r\n]+)', content)
                for rname, rurl in m_remotes:
                    remotes.append({"name": rname, "url": rurl.strip()})
            except Exception:
                pass

        if not remotes:
            remotes_raw = _run_git(["remote", "-v"], timeout=5)
            remote_names = set()
            for line in remotes_raw.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] not in remote_names:
                    remote_names.add(parts[0])
                    remotes.append({"name": parts[0], "url": parts[1]})

        # 4. Check Sentinel Hook installation
        pre_commit_file = os.path.join(norm_path, ".git", "hooks", "pre-commit")
        pre_push_file = os.path.join(norm_path, ".git", "hooks", "pre-push")
        has_hook = False
        for h_file in [pre_commit_file, pre_push_file]:
            if os.path.exists(h_file):
                try:
                    with open(h_file, "r", encoding="utf-8", errors="ignore") as f:
                        if "GitSentinel" in f.read():
                            has_hook = True
                            break
                except Exception:
                    pass

        # 5. Bound SSH key and settings
        bound_key = key_manager.get_repo_bound_key(norm_path)
        repo_setting = config_manager.get_repo_setting(norm_path)

        data = {
            "id": repo_id,
            "name": repo_name,
            "path": norm_path,
            "branch": branch,
            "branches": [branch] if branch else [],
            "remotes": remotes,
            "has_remote": len(remotes) > 0,
            "tracking_branch": tracking,
            "ahead": ahead,
            "behind": behind,
            "staged_count": len(staged_files),
            "unstaged_count": len(unstaged_files),
            "untracked_count": len(untracked_files),
            "staged_files": staged_files,
            "is_clean": len(staged_files) == 0 and len(unstaged_files) == 0 and len(untracked_files) == 0,
            "last_commit": last_commit,
            "has_local_hook": has_hook,
            "is_intercept_enabled": repo_setting.get("intercept_enabled", True),
            "bound_ssh_key": bound_key
        }

        self.cached_repos[repo_id] = data
        return data

    def git_fetch(self, repo_path: str) -> Dict[str, Any]:
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GCM_INTERACTIVE"] = "never"
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
            res = subprocess.run(
                ["git", "-c", "core.askPass=", "fetch", "--all", "--prune"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                env=env,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return {
                "success": res.returncode == 0,
                "output": (res.stdout or "") + (res.stderr or "")
            }
        except Exception as e:
            return {"success": False, "output": str(e)}

    def git_pull(self, repo_path: str) -> Dict[str, Any]:
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GCM_INTERACTIVE"] = "never"
            env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes"
            res = subprocess.run(
                ["git", "-c", "core.askPass=", "pull"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                env=env,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return {
                "success": res.returncode == 0,
                "output": (res.stdout or "") + (res.stderr or "")
            }
        except Exception as e:
            return {"success": False, "output": str(e)}

    def git_push(self, repo_path: str) -> Dict[str, Any]:
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            res = subprocess.run(
                ["git", "push"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return {
                "success": res.returncode == 0,
                "output": (res.stdout or "") + (res.stderr or "")
            }
        except Exception as e:
            return {"success": False, "output": str(e)}

    def sync_sentinel_runtime(self) -> Path:
        """Copies runtime scripts to ~/.git-sentinel so hooks work independently and permanently"""
        sentinel_home = Path.home() / ".git-sentinel"
        sentinel_home.mkdir(parents=True, exist_ok=True)
        interceptor_dir = sentinel_home / "interceptor"
        backend_dir = sentinel_home / "backend"
        hooks_dir = sentinel_home / "hooks"
        for d in [interceptor_dir, backend_dir, hooks_dir]:
            d.mkdir(parents=True, exist_ok=True)

        project_root = Path(__file__).parent.parent.resolve()
        
        # Copy interceptor script
        src_interceptor = project_root / "interceptor" / "interceptor_gui.py"
        if src_interceptor.exists():
            shutil.copy2(src_interceptor, interceptor_dir / "interceptor_gui.py")

        # Copy backend files
        for f in ["config.py", "security_scanner.py", "notifier.py", "scan_rules.json"]:
            src_f = project_root / "backend" / f
            if src_f.exists():
                shutil.copy2(src_f, backend_dir / f)

        # Ensure __init__.py exists
        (interceptor_dir / "__init__.py").touch()
        (backend_dir / "__init__.py").touch()
        (sentinel_home / "__init__.py").touch()

        return hooks_dir

    def install_local_hook(self, repo_path: str) -> bool:
        """Installs pre-commit, pre-push, and post-commit hooks into the repository"""
        hooks_dir = os.path.join(repo_path, ".git", "hooks")
        os.makedirs(hooks_dir, exist_ok=True)
        self.sync_sentinel_runtime()
        
        sentinel_home = (Path.home() / ".git-sentinel").resolve().as_posix()
        app_exe = sys.executable.replace("\\", "/") if getattr(sys, "frozen", False) else ""

        pre_commit_content = f"""#!/bin/sh
# GitSentinel Pre-Commit Interceptor Hook
if [ "$GIT_SENTINEL_SKIP" = "1" ]; then
    exit 0
fi

REPO_DIR="$PWD"
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"
SCRIPT="$SENTINEL_HOME/interceptor/interceptor_gui.py"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" intercept --repo-dir "$REPO_DIR" --hook-type commit "$@"
    exit $?
fi

if command -v python >/dev/null 2>&1; then
    python "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit "$@"
    exit $?
elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit "$@"
    exit $?
elif command -v py >/dev/null 2>&1; then
    py "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit "$@"
    exit $?
fi

exit 0
"""
        pre_commit_file = os.path.join(hooks_dir, "pre-commit")
        with open(pre_commit_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(pre_commit_content)

        pre_push_content = f"""#!/bin/sh
# GitSentinel Pre-Push Interceptor Hook
if [ "$GIT_SENTINEL_SKIP" = "1" ]; then
    exit 0
fi

REPO_DIR="$PWD"
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"
SCRIPT="$SENTINEL_HOME/interceptor/interceptor_gui.py"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" intercept --repo-dir "$REPO_DIR" --hook-type push "$@"
    exit $?
fi

if command -v python >/dev/null 2>&1; then
    python "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push "$@"
    exit $?
elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push "$@"
    exit $?
elif command -v py >/dev/null 2>&1; then
    py "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push "$@"
    exit $?
fi

exit 0
"""
        pre_push_file = os.path.join(hooks_dir, "pre-push")
        with open(pre_push_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(pre_push_content)

        post_commit_content = f"""#!/bin/sh
# GitSentinel Post-Commit Notification Hook
REPO_NAME=$(basename "$PWD")
COMMIT_MSG=$(git log -1 --pretty=%s 2>/dev/null)
COMMIT_HASH=$(git log -1 --pretty=%h 2>/dev/null)
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" post-commit-notify "$REPO_NAME" "$COMMIT_HASH" "$COMMIT_MSG" "$PWD" >/dev/null 2>&1 &
elif command -v python >/dev/null 2>&1; then
    python -c "import sys; sys.path.insert(0, '$SENTINEL_HOME'); from backend.notifier import notifier; notifier.notify('✅ Git 提交完成', f'[{{sys.argv[1]}}] {{sys.argv[2]}}: {{sys.argv[3]}}\', event_type='commit', repo_path=sys.argv[4])" "$REPO_NAME" "$COMMIT_HASH" "$COMMIT_MSG" "$PWD" >/dev/null 2>&1 &
fi
exit 0
"""
        post_commit_file = os.path.join(hooks_dir, "post-commit")
        with open(post_commit_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(post_commit_content)

        # Grant executable permission on Unix (macOS / Linux)
        for h in [pre_commit_file, pre_push_file, post_commit_file]:
            try:
                os.chmod(h, 0o755)
            except Exception:
                pass

        return True

    def uninstall_local_hook(self, repo_path: str) -> bool:
        hooks_dir = os.path.join(repo_path, ".git", "hooks")
        for h in ["pre-commit", "pre-push", "post-commit"]:
            p = os.path.join(hooks_dir, h)
            if os.path.exists(p):
                try:
                    content = ""
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if "GitSentinel" in content:
                        os.remove(p)
                except Exception:
                    pass
        return True

    def set_global_hooks(self, enabled: bool) -> bool:
        """Enables or disables GitSentinel as the global hooksPath (~/.git-sentinel/hooks)"""
        hooks_dir = self.sync_sentinel_runtime()

        if enabled:
            sentinel_home = (Path.home() / ".git-sentinel").resolve().as_posix()
            app_exe = sys.executable.replace("\\", "/") if getattr(sys, "frozen", False) else ""

            pre_cmd = f"""#!/bin/sh
# GitSentinel Global Pre-Commit Interceptor Hook
if [ "$GIT_SENTINEL_SKIP" = "1" ]; then
    exit 0
fi

REPO_DIR="$PWD"
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"
SCRIPT="$SENTINEL_HOME/interceptor/interceptor_gui.py"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" intercept --repo-dir "$REPO_DIR" --hook-type commit --global-hook "$@"
    exit $?
fi

if command -v python >/dev/null 2>&1; then
    python "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit --global-hook "$@"
    exit $?
elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit --global-hook "$@"
    exit $?
elif command -v py >/dev/null 2>&1; then
    py "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type commit --global-hook "$@"
    exit $?
fi

exit 0
"""
            pre_commit_script = hooks_dir / "pre-commit"
            with open(pre_commit_script, "w", encoding="utf-8", newline="\n") as f:
                f.write(pre_cmd)

            pre_push_cmd = f"""#!/bin/sh
# GitSentinel Global Pre-Push Interceptor Hook
if [ "$GIT_SENTINEL_SKIP" = "1" ]; then
    exit 0
fi

REPO_DIR="$PWD"
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"
SCRIPT="$SENTINEL_HOME/interceptor/interceptor_gui.py"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" intercept --repo-dir "$REPO_DIR" --hook-type push --global-hook "$@"
    exit $?
fi

if command -v python >/dev/null 2>&1; then
    python "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push --global-hook "$@"
    exit $?
elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push --global-hook "$@"
    exit $?
elif command -v py >/dev/null 2>&1; then
    py "$SCRIPT" --repo-dir "$REPO_DIR" --hook-type push --global-hook "$@"
    exit $?
fi

exit 0
"""
            pre_push_script = hooks_dir / "pre-push"
            with open(pre_push_script, "w", encoding="utf-8", newline="\n") as f:
                f.write(pre_push_cmd)

            post_cmd = f"""#!/bin/sh
# GitSentinel Global Post-Commit Notification Hook
REPO_NAME=$(basename "$PWD")
COMMIT_MSG=$(git log -1 --pretty=%s 2>/dev/null)
COMMIT_HASH=$(git log -1 --pretty=%h 2>/dev/null)
APP_EXE="{app_exe}"
SENTINEL_HOME="{sentinel_home}"

if [ -n "$APP_EXE" ] && [ -f "$APP_EXE" ]; then
    "$APP_EXE" post-commit-notify "$REPO_NAME" "$COMMIT_HASH" "$COMMIT_MSG" "$PWD" >/dev/null 2>&1 &
elif command -v python >/dev/null 2>&1; then
    python -c "import sys; sys.path.insert(0, '$SENTINEL_HOME'); from backend.notifier import notifier; notifier.notify('✅ Git 提交完成', f'[{{sys.argv[1]}}] {{sys.argv[2]}}: {{sys.argv[3]}}\', event_type='commit', repo_path=sys.argv[4])" "$REPO_NAME" "$COMMIT_HASH" "$COMMIT_MSG" "$PWD" >/dev/null 2>&1 &
fi
exit 0
"""
            post_commit_script = hooks_dir / "post-commit"
            with open(post_commit_script, "w", encoding="utf-8", newline="\n") as f:
                f.write(post_cmd)

            for h in [pre_commit_script, pre_push_script, post_commit_script]:
                try:
                    os.chmod(h, 0o755)
                except Exception:
                    pass

            # Configure git global core.hooksPath
            hooks_dir_str = str(hooks_dir).replace("\\", "/")
            res = subprocess.run(
                ["git", "config", "--global", "core.hooksPath", hooks_dir_str],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            config_manager.set("global_intercept", True)
            return res.returncode == 0
        else:
            # Unset git global core.hooksPath
            subprocess.run(
                ["git", "config", "--global", "--unset", "core.hooksPath"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            config_manager.set("global_intercept", False)
            return True

    def is_global_hooks_enabled(self) -> bool:
        try:
            res = subprocess.run(
                ["git", "config", "--global", "--get", "core.hooksPath"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            val = res.stdout.strip().replace("\\", "/").lower()
            if not val:
                return False
            # Check if it points to sentinel hooks or has git-sentinel in path
            return "git-sentinel" in val or "hooks" in val
        except Exception:
            return False

repo_manager = RepoManager()
