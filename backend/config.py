import json
import os
import sys
import string
from pathlib import Path
from typing import Dict, Any, List

CONFIG_DIR = Path.home() / ".git-sentinel"
CONFIG_FILE = CONFIG_DIR / "config.json"

def get_initial_monitored_paths() -> List[str]:
    paths = []
    home = str(Path.home())
    if home not in paths:
        paths.append(home)
    # User home dev directories
    for sub in ["Desktop", "Documents", "Projects", "code", "workspace", "source", "repos", "dev"]:
        cand = os.path.join(home, sub)
        if os.path.exists(cand) and cand not in paths:
            paths.append(cand)

    # Check all available drives for dev folders or non-C root
    if sys.platform == "win32":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                if letter != "C":
                    try:
                        os.listdir(drive)
                        if drive not in paths:
                            paths.append(drive)
                    except Exception:
                        pass
                else:
                    for sub in ["Projects", "Code", "workspace", "dev", "git", "repos", "src", "Document", "Documents"]:
                        cand = os.path.join(drive, sub)
                        if os.path.exists(cand) and cand not in paths:
                            paths.append(cand)
    else:
        for unix_dir in [
            "/var/www",
            "/opt",
            str(Path.home() / "Projects"),
            str(Path.home() / "Workspace"),
            str(Path.home() / "code"),
            str(Path.home() / "dev")
        ]:
            if os.path.exists(unix_dir) and unix_dir not in paths:
                paths.append(unix_dir)
    return paths

DEFAULT_CONFIG: Dict[str, Any] = {
    "monitored_paths": get_initial_monitored_paths(),
    "scan_depth": 6,
    "check_interval_seconds": 600,
    "global_intercept": False,
    "notifications_enabled": True,
    "desktop_toast_enabled": True,
    "security_rules": {
        "sensitive_files": [
            ".env",
            ".env.*",
            "id_rsa",
            "id_rsa.pub",
            "id_ed25519",
            "id_ed25519.pub",
            "*.pem",
            "*.key",
            "credentials.json",
            "token.txt",
            "secrets.json",
            "*.pfx",
            "*.p12",
            "wp-config.php",
            "secring.gpg"
        ],
        "secret_patterns": [
            {
                "name": "Private Key Header",
                "regex": r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP)? ?PRIVATE KEY",
                "level": "critical"
            },
            {
                "name": "AWS Access Key",
                "regex": r"AKIA[0-9A-Z]{16}",
                "level": "critical"
            },
            {
                "name": "GitHub Token",
                "regex": r"gh[pousr]_[A-Za-z0-9_]{36,}",
                "level": "critical"
            },
            {
                "name": "OpenAI API Key",
                "regex": r"sk-(?:proj-)?[a-zA-Z0-9_-]{20,}",
                "level": "critical"
            },
            {
                "name": "Generic API Secret / Token Assignment",
                "regex": r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
                "level": "warning"
            }
        ]
    },
    "repo_settings": {},
    "manual_repos": []
}

class ConfigManager:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.config_path = CONFIG_FILE
        self._data = self.load()

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            self.save(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # merge with defaults for any missing keys
                for k, v in DEFAULT_CONFIG.items():
                    if k not in data:
                        data[k] = v
                # Auto-enrich missing drives into monitored_paths
                existing_monitored = data.get("monitored_paths", [])
                for p in get_initial_monitored_paths():
                    if p not in existing_monitored:
                        existing_monitored.append(p)
                data["monitored_paths"] = existing_monitored
                if data.get("scan_depth", 3) < 6:
                    data["scan_depth"] = 6
                return data
        except Exception as e:
            print(f"Error loading config, falling back to default: {e}")
            return DEFAULT_CONFIG.copy()

    def save(self, data: Dict[str, Any] = None) -> None:
        if data is not None:
            self._data = data
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def get_all(self) -> Dict[str, Any]:
        return self._data

    def get_repo_setting(self, repo_path: str) -> Dict[str, Any]:
        norm_path = os.path.normpath(repo_path)
        return self._data.get("repo_settings", {}).get(norm_path, {
            "intercept_enabled": True,
            "custom_ssh_key": ""
        })

    def update_repo_setting(self, repo_path: str, settings: Dict[str, Any]) -> None:
        norm_path = os.path.normpath(repo_path)
        if "repo_settings" not in self._data:
            self._data["repo_settings"] = {}
        if norm_path not in self._data["repo_settings"]:
            self._data["repo_settings"][norm_path] = {}
        self._data["repo_settings"][norm_path].update(settings)
        self.save()

config_manager = ConfigManager()
