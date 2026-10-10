import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .config import config_manager
from .repo_manager import repo_manager
from .key_manager import key_manager
from .security_scanner import SecurityScanner
from .notifier import notifier
from .background_watcher import background_watcher

app = FastAPI(title="GitSentinel API", version="1.0.0")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Forward notifier events to WebSocket
def on_notification_event(record: Dict[str, Any]):
    asyncio.run_coroutine_threadsafe(
        ws_manager.broadcast({"type": "notification", "data": record}),
        app.state.loop
    )

notifier.add_listener(on_notification_event)

@app.on_event("startup")
async def startup_event():
    app.state.loop = asyncio.get_event_loop()
    background_watcher.start()
    # Scan repos in background on startup
    asyncio.create_task(async_initial_scan())

async def async_initial_scan():
    await asyncio.to_thread(repo_manager.scan_directories)
    await asyncio.to_thread(repo_manager.sync_sentinel_runtime)
    if config_manager.get("global_intercept", False):
        await asyncio.to_thread(repo_manager.set_global_hooks, True)

@app.on_event("shutdown")
def shutdown_event():
    background_watcher.stop()

# --- Repository Endpoints ---

@app.get("/api/repos")
async def list_repos():
    if not repo_manager.cached_repos:
        repos = await asyncio.to_thread(repo_manager.scan_directories)
    else:
        repos = list(repo_manager.cached_repos.values())
    return {
        "repos": repos,
        "global_hooks_enabled": repo_manager.is_global_hooks_enabled(),
        "total": len(repos)
    }

@app.post("/api/repos/scan")
async def rescan_repos():
    repos = await asyncio.to_thread(repo_manager.scan_directories)
    return {
        "repos": repos,
        "global_hooks_enabled": repo_manager.is_global_hooks_enabled(),
        "total": len(repos)
    }

class AddRepoRequest(BaseModel):
    path: str

@app.post("/api/repos/manual")
async def add_manual_repo(req: AddRepoRequest):
    p = os.path.abspath(req.path)
    if not os.path.isdir(os.path.join(p, ".git")):
        raise HTTPException(status_code=400, detail="该路径不是有效的 Git 仓库（缺少 .git 目录）")
    
    manuals = config_manager.get("manual_repos", [])
    if p not in manuals:
        manuals.append(p)
        config_manager.set("manual_repos", manuals)

    status = repo_manager.get_repo_status(p)
    return {"success": True, "repo": status}

@app.get("/api/repos/{repo_id}")
async def get_repo(repo_id: str):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    updated = repo_manager.get_repo_status(repo["path"])
    return {"repo": updated}

@app.post("/api/repos/{repo_id}/fetch")
async def fetch_repo(repo_id: str):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    res = await asyncio.to_thread(repo_manager.git_fetch, repo["path"])
    updated = repo_manager.get_repo_status(repo["path"])
    return {"result": res, "repo": updated}

@app.post("/api/repos/{repo_id}/pull")
async def pull_repo(repo_id: str):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    res = await asyncio.to_thread(repo_manager.git_pull, repo["path"])
    updated = repo_manager.get_repo_status(repo["path"])
    return {"result": res, "repo": updated}

@app.post("/api/repos/{repo_id}/push")
async def push_repo(repo_id: str):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    res = await asyncio.to_thread(repo_manager.git_push, repo["path"])
    updated = repo_manager.get_repo_status(repo["path"])
    return {"result": res, "repo": updated}

class ToggleHookRequest(BaseModel):
    enabled: bool

@app.post("/api/repos/{repo_id}/hook")
async def toggle_local_hook(repo_id: str, req: ToggleHookRequest):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    if req.enabled:
        repo_manager.install_local_hook(repo["path"])
    else:
        repo_manager.uninstall_local_hook(repo["path"])
    updated = repo_manager.get_repo_status(repo["path"])
    return {"success": True, "repo": updated}

@app.post("/api/repos/{repo_id}/intercept")
async def toggle_intercept(repo_id: str, req: ToggleHookRequest):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    config_manager.update_repo_setting(repo["path"], {"intercept_enabled": req.enabled})
    updated = repo_manager.get_repo_status(repo["path"])
    return {"success": True, "repo": updated}

class BindKeyRequest(BaseModel):
    key_path: str

@app.post("/api/repos/{repo_id}/bind-key")
async def bind_repo_key(repo_id: str, req: BindKeyRequest):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    key_manager.bind_repo_key(repo["path"], req.key_path)
    updated = repo_manager.get_repo_status(repo["path"])
    return {"success": True, "repo": updated}

class OpenActionRequest(BaseModel):
    target: str  # 'explorer', 'terminal', 'vscode'

def _open_file_manager(p: str):
    norm_p = os.path.normpath(p)
    if sys.platform == "win32":
        subprocess.Popen(f'explorer.exe "{norm_p}"', shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", norm_p])
    else:
        subprocess.Popen(["xdg-open", norm_p])

def _open_code_editor(p: str):
    norm_p = os.path.normpath(p)
    try:
        subprocess.Popen(["code", norm_p], shell=(sys.platform == "win32"))
    except Exception:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Visual Studio Code", norm_p])

def _open_terminal(p: str):
    norm_p = os.path.normpath(p)
    if sys.platform == "win32":
        if shutil.which("wt"):
            subprocess.Popen(f'wt.exe -d "{norm_p}"', shell=True)
        else:
            subprocess.Popen(f'start cmd /K "cd /d {norm_p}"', shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "Terminal", norm_p])
    else:
        terminals = [
            ["x-terminal-emulator"],
            ["gnome-terminal", f"--working-directory={norm_p}"],
            ["konsole", f"--workdir={norm_p}"],
            ["xfce4-terminal", f"--working-directory={norm_p}"],
            ["alacritty", "--working-directory", norm_p],
            ["kitty", "-d", norm_p],
            ["xterm", "-e", f"cd '{norm_p}' && bash"]
        ]
        launched = False
        for term_cmd in terminals:
            if shutil.which(term_cmd[0]):
                subprocess.Popen(term_cmd)
                launched = True
                break
        if not launched:
            subprocess.Popen(["xterm", "-e", f"cd '{norm_p}' && bash"])

@app.post("/api/repos/{repo_id}/open")
async def open_repo_in_system(repo_id: str, req: OpenActionRequest):
    repo = repo_manager.cached_repos.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="仓库未找到")
    p = repo["path"]

    if req.target == "explorer":
        _open_file_manager(p)
    elif req.target == "vscode":
        _open_code_editor(p)
    elif req.target == "terminal":
        _open_terminal(p)
    return {"success": True}

# --- SSH Key & Credential Endpoints ---

@app.get("/api/keys")
async def list_keys():
    keys = key_manager.list_keys()
    user_cfg = key_manager.get_git_user_config()
    return {
        "keys": keys,
        "git_user": user_cfg,
        "ssh_dir": str(key_manager.ssh_dir)
    }

class GenerateKeyRequest(BaseModel):
    name: str
    key_type: str = "ed25519"
    comment: str = ""
    passphrase: str = ""

@app.post("/api/keys/generate")
async def generate_key(req: GenerateKeyRequest):
    try:
        new_key = key_manager.generate_key(
            name=req.name,
            key_type=req.key_type,
            comment=req.comment,
            passphrase=req.passphrase
        )
        return {"success": True, "key": new_key}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class TestConnectionRequest(BaseModel):
    host: str
    key_path: Optional[str] = None

@app.post("/api/keys/test")
async def test_connection(req: TestConnectionRequest):
    res = await asyncio.to_thread(key_manager.test_connection, req.host, req.key_path)
    return res

class ApplyGlobalIdentityRequest(BaseModel):
    name: str
    email: str

class SetGitUserRequest(BaseModel):
    user_name: str
    user_email: str
    is_global: bool = True
    repo_path: Optional[str] = None

@app.post("/api/git/user")
async def set_git_user(req: SetGitUserRequest):
    try:
        key_manager.set_git_user_config(
            user_name=req.user_name,
            user_email=req.user_email,
            is_global=req.is_global,
            repo_path=req.repo_path
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ApplyRepoIdentityRequest(BaseModel):
    repo_path: str
    name: str
    email: str

class ResetRepoIdentityRequest(BaseModel):
    repo_path: str

@app.get("/api/git/identities")
async def get_all_git_identities():
    repos = list(repo_manager.cached_repos.values())
    if not repos:
        repos = await asyncio.to_thread(repo_manager.scan_directories)
    identities_data = await asyncio.to_thread(key_manager.get_all_git_identities, repos)
    return identities_data

@app.post("/api/git/identities/apply-global")
async def apply_global_identity(req: ApplyGlobalIdentityRequest):
    try:
        key_manager.set_git_user_config(user_name=req.name, user_email=req.email, is_global=True)
        return {"success": True, "name": req.name, "email": req.email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/git/identities/apply-repo")
async def apply_repo_identity(req: ApplyRepoIdentityRequest):
    try:
        key_manager.set_git_user_config(user_name=req.name, user_email=req.email, is_global=False, repo_path=req.repo_path)
        repo_manager.get_repo_status(req.repo_path)
        return {"success": True, "repo_path": req.repo_path, "name": req.name, "email": req.email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/git/identities/reset-repo")
async def reset_repo_identity(req: ResetRepoIdentityRequest):
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.run(["git", "config", "--local", "--unset", "user.name"], cwd=req.repo_path, capture_output=True, creationflags=flags)
        subprocess.run(["git", "config", "--local", "--unset", "user.email"], cwd=req.repo_path, capture_output=True, creationflags=flags)
        repo_manager.get_repo_status(req.repo_path)
        return {"success": True, "repo_path": req.repo_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class UpdateScanPathsRequest(BaseModel):
    monitored_paths: List[str]
    scan_depth: int

@app.get("/api/scan/paths")
async def get_scan_paths():
    return {
        "monitored_paths": config_manager.get("monitored_paths", []),
        "scan_depth": config_manager.get("scan_depth", 5)
    }

@app.post("/api/scan/paths")
async def update_scan_paths(req: UpdateScanPathsRequest):
    config_manager.set("monitored_paths", req.monitored_paths)
    config_manager.set("scan_depth", req.scan_depth)
    repos = await asyncio.to_thread(repo_manager.scan_directories)
    return {"success": True, "total_repos": len(repos), "repos": repos}

# --- Global Hook & Interceptor Control ---

@app.post("/api/hooks/global")
async def toggle_global_hooks(req: ToggleHookRequest):
    res = repo_manager.set_global_hooks(req.enabled)
    notifier.notify(
        title="🛡️ 全局拦截模式状态变更",
        message="全局 Git 提交前拦截已开启" if req.enabled else "全局 Git 提交前拦截已关闭",
        event_type="info"
    )
    return {"success": res, "global_hooks_enabled": repo_manager.is_global_hooks_enabled()}


# --- Notifications Endpoints ---

@app.get("/api/notifications")
async def get_notifications():
    return {"notifications": notifier.get_history(100)}

@app.post("/api/notifications/test-toast")
async def test_toast_notification():
    notifier.notify(
        title="🔔 GitSentinel 桌面提醒测试",
        message="Windows 原生 Toast 通知与 Git 提交/更新提醒引擎工作正常！",
        event_type="info"
    )
    return {"success": True}

# --- Settings & Security Rules ---

@app.get("/api/settings")
async def get_settings():
    return config_manager.get_all()

@app.post("/api/settings")
async def update_settings(data: Dict[str, Any]):
    config_manager.save(data)
    return {"success": True, "settings": config_manager.get_all()}

# --- WebSocket ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keepalive / ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# --- Frontend Static Files ---
static_dir = Path(__file__).parent.parent / "frontend" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def serve_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"message": "GitSentinel backend active. UI file not found."})
