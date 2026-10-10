import os
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

SSH_DIR = Path.home() / ".ssh"

class KeyManager:
    def __init__(self):
        SSH_DIR.mkdir(parents=True, exist_ok=True)
        self.ssh_dir = SSH_DIR

    def list_keys(self) -> List[Dict[str, Any]]:
        keys = []
        if not self.ssh_dir.exists():
            return keys

        # Scan for .pub files
        pub_files = list(self.ssh_dir.glob("*.pub"))
        for pub_path in pub_files:
            priv_path = pub_path.with_suffix("")
            has_private = priv_path.exists()
            
            key_info = self._parse_key(pub_path, priv_path if has_private else None)
            keys.append(key_info)

        # Also check for private keys that don't have .pub files
        for priv_file in self.ssh_dir.iterdir():
            if priv_file.is_file() and not priv_file.name.endswith(".pub") and priv_file.name not in ["known_hosts", "known_hosts.old", "config"]:
                # Check if this looks like a private key
                try:
                    with open(priv_file, "r", encoding="utf-8", errors="ignore") as f:
                        header = f.readline()
                        if "PRIVATE KEY" in header:
                            pub_file = priv_file.with_suffix(".pub")
                            if not pub_file.exists():
                                # Try generating or inspecting
                                keys.append({
                                    "name": priv_file.name,
                                    "private_path": str(priv_file),
                                    "public_path": "",
                                    "has_private": True,
                                    "has_public": False,
                                    "type": "Unknown",
                                    "size": 0,
                                    "fingerprint": "No .pub file found",
                                    "comment": "",
                                    "public_key": ""
                                })
                except Exception:
                    pass

        return keys

    def _parse_key(self, pub_path: Path, priv_path: Optional[Path]) -> Dict[str, Any]:
        info = {
            "name": pub_path.stem,
            "private_path": str(priv_path) if priv_path else "",
            "public_path": str(pub_path),
            "has_private": priv_path is not None,
            "has_public": True,
            "type": "RSA",
            "size": 0,
            "fingerprint": "",
            "comment": "",
            "public_key": ""
        }

        try:
            with open(pub_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
                info["public_key"] = content
                parts = content.split()
                if len(parts) >= 2:
                    algo = parts[0]
                    if "ed25519" in algo:
                        info["type"] = "Ed25519"
                    elif "rsa" in algo:
                        info["type"] = "RSA"
                    elif "ecdsa" in algo:
                        info["type"] = "ECDSA"
                    else:
                        info["type"] = algo
                if len(parts) >= 3:
                    info["comment"] = " ".join(parts[2:])
        except Exception:
            pass

        # Use ssh-keygen to parse fingerprint and size accurately
        try:
            res = subprocess.run(
                ["ssh-keygen", "-l", "-f", str(pub_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if res.returncode == 0 and res.stdout.strip():
                # Format: 256 SHA256:xxxx comment (ED25519) or 4096 SHA256:xxxx comment (RSA)
                line = res.stdout.strip().splitlines()[0]
                m = re.match(r"^(\d+)\s+([A-Za-z0-9+/=:]+)\s+(.*?)\s+\((.*?)\)$", line)
                if m:
                    info["size"] = int(m.group(1))
                    info["fingerprint"] = m.group(2)
                    if not info["comment"]:
                        info["comment"] = m.group(3)
                    info["type"] = m.group(4)
                else:
                    parts = line.split()
                    if len(parts) >= 2:
                        info["size"] = int(parts[0]) if parts[0].isdigit() else 0
                        info["fingerprint"] = parts[1]
        except Exception:
            pass

        return info

    def generate_key(self, name: str, key_type: str = "ed25519", comment: str = "", passphrase: str = "") -> Dict[str, Any]:
        key_path = self.ssh_dir / name
        if key_path.exists() or (self.ssh_dir / f"{name}.pub").exists():
            raise FileExistsError(f"密钥名称 `{name}` 已存在，请使用其他名称！")

        cmd = ["ssh-keygen", "-t", key_type, "-f", str(key_path), "-N", passphrase]
        if comment:
            cmd.extend(["-C", comment])

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if res.returncode != 0:
            raise RuntimeError(f"生成密钥失败: {res.stderr or res.stdout}")

        return self._parse_key(self.ssh_dir / f"{name}.pub", key_path)

    def test_connection(self, host: str, key_path: Optional[str] = None) -> Dict[str, Any]:
        """Tests SSH connection to Git hosting services (e.g. github.com, gitlab.com, gitee.com)"""
        git_hosts = {
            "github": "git@github.com",
            "gitlab": "git@gitlab.com",
            "gitee": "git@gitee.com",
            "coding": "git@e.coding.net"
        }
        target = git_hosts.get(host.lower(), host)
        if "@" not in target:
            target = f"git@{target}"

        cmd = ["ssh", "-Tv", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=7"]
        if key_path and os.path.exists(key_path):
            cmd.extend(["-i", key_path, "-o", "IdentitiesOnly=yes"])
        cmd.append(target)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            output = res.stderr + "\n" + res.stdout

            # Analyze output for known authentication success messages
            # GitHub: "Hi username! You've successfully authenticated"
            # GitLab: "Welcome to GitLab, @username!"
            # Gitee: "Hi username! You've successfully authenticated"
            success = False
            username = ""
            message = ""

            gh_match = re.search(r"Hi\s+([a-zA-Z0-9_-]+)! You've successfully authenticated", output)
            gl_match = re.search(r"Welcome to GitLab,\s*@?([a-zA-Z0-9_-]+)!", output)
            gitee_match = re.search(r"Hi\s+([a-zA-Z0-9_-]+).*! You've successfully authenticated", output)

            if gh_match:
                success = True
                username = gh_match.group(1)
                message = f"成功通过 GitHub 身份认证！当前账户: {username}"
            elif gl_match:
                success = True
                username = gl_match.group(1)
                message = f"成功通过 GitLab 身份认证！当前账户: {username}"
            elif gitee_match:
                success = True
                username = gitee_match.group(1)
                message = f"成功通过 Gitee 身份认证！当前账户: {username}"
            elif "successfully authenticated" in output.lower() or "welcome" in output.lower():
                success = True
                message = "SSH 握手与身份验证成功！"
            elif "permission denied" in output.lower():
                success = False
                message = "身份认证失败 (Permission Denied)。请确认公钥已正确添加到平台并开启了相应权限。"
            elif "connection timed out" in output.lower() or "could not resolve hostname" in output.lower():
                success = False
                message = f"网络连接超时或无法解析主机: {target}。"
            else:
                success = res.returncode == 1  # ssh -T returns 1 on git hosts because no interactive shell is offered
                message = "已连接到服务器，但未识别到标准用户名问候语。"

            return {
                "success": success,
                "target": target,
                "username": username,
                "message": message,
                "raw_output": output[-1000:]
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "target": target,
                "username": "",
                "message": f"连接 {target} 超时（7秒），请检查网络或代理。",
                "raw_output": "Timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "target": target,
                "username": "",
                "message": f"执行错误: {str(e)}",
                "raw_output": str(e)
            }

    def bind_repo_key(self, repo_path: str, key_path: str) -> None:
        """Configures git core.sshCommand for this specific repository"""
        if not key_path:
            # Unbind
            subprocess.run(
                ["git", "config", "--unset", "core.sshCommand"],
                cwd=repo_path,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return

        norm_key = key_path.replace("\\", "/")
        ssh_cmd = f"ssh -i \"{norm_key}\" -o IdentitiesOnly=yes -F /dev/null"
        subprocess.run(
            ["git", "config", "core.sshCommand", ssh_cmd],
            cwd=repo_path,
            check=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )

    def get_repo_bound_key(self, repo_path: str) -> str:
        try:
            res = subprocess.run(
                ["git", "config", "--get", "core.sshCommand"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            cmd = res.stdout.strip()
            # Extract key path from: ssh -i "C:/path/key" ...
            m = re.search(r'-i\s+"?([^"\s]+)"?', cmd)
            if m:
                return m.group(1)
            return cmd
        except Exception:
            return ""

    def get_git_user_config(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """Reads global and local git username/email"""
        def _get_cfg(args, cwd=None):
            try:
                res = subprocess.run(
                    ["git", "config"] + args,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                return res.stdout.strip()
            except Exception:
                return ""

        global_name = _get_cfg(["--global", "user.name"])
        global_email = _get_cfg(["--global", "user.email"])
        local_name = _get_cfg(["--local", "user.name"], cwd=repo_path) if repo_path else ""
        local_email = _get_cfg(["--local", "user.email"], cwd=repo_path) if repo_path else ""

        return {
            "global_user_name": global_name,
            "global_user_email": global_email,
            "local_user_name": local_name,
            "local_user_email": local_email
        }

    def set_git_user_config(self, user_name: str, user_email: str, is_global: bool = True, repo_path: Optional[str] = None) -> None:
        target = ["--global"] if is_global else ["--local"]
        cwd = None if is_global else repo_path
        if user_name:
            subprocess.run(["git", "config"] + target + ["user.name", user_name], cwd=cwd, check=True)
        if user_email:
            subprocess.run(["git", "config"] + target + ["user.email", user_email], cwd=cwd, check=True)

    def get_ssh_config_hosts(self) -> List[Dict[str, Any]]:
        """Parses ~/.ssh/config for configured SSH hosts and aliases"""
        ssh_config_path = self.ssh_dir / "config"
        if not ssh_config_path.exists():
            return []

        hosts = []
        try:
            current_host = None
            with open(ssh_config_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(None, 1)
                    if len(parts) < 2:
                        continue
                    key, val = parts[0].lower(), parts[1].strip()
                    if key == "host":
                        if current_host:
                            hosts.append(current_host)
                        current_host = {
                            "host": val,
                            "hostname": val,
                            "user": "git",
                            "identity_file": ""
                        }
                    elif current_host:
                        if key == "hostname":
                            current_host["hostname"] = val
                        elif key == "user":
                            current_host["user"] = val
                        elif key == "identityfile":
                            current_host["identity_file"] = val
            if current_host:
                hosts.append(current_host)
        except Exception:
            pass
        return hosts

    def get_all_git_identities(self, repos: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Discovers and aggregates all active Git author identities across global, local configs and commit histories"""
        global_cfg = self.get_git_user_config()
        g_name = global_cfg.get("global_user_name", "").strip()
        g_email = global_cfg.get("global_user_email", "").strip()

        identities_map: Dict[tuple, Dict[str, Any]] = {}

        # 1. Include global identity if configured
        if g_name or g_email:
            identities_map[(g_name, g_email.lower())] = {
                "name": g_name,
                "email": g_email,
                "is_global": True,
                "local_repos": [],
                "author_repos": [],
                "commit_count": 0,
                "role_badges": ["全局默认 (Global)"]
            }

        # 2. Iterate through repositories to inspect local configs and commit history
        repo_list = repos or []
        for r in repo_list:
            r_path = r.get("path")
            r_name = r.get("name") or os.path.basename(r_path or "")
            if not r_path or not os.path.exists(r_path):
                continue

            # Check local git config
            try:
                res_n = subprocess.run(["git", "config", "--local", "user.name"], cwd=r_path, capture_output=True, text=True, timeout=3)
                loc_n = res_n.stdout.strip()
                res_e = subprocess.run(["git", "config", "--local", "user.email"], cwd=r_path, capture_output=True, text=True, timeout=3)
                loc_e = res_e.stdout.strip()
                if loc_n or loc_e:
                    k = (loc_n, loc_e.lower())
                    if k not in identities_map:
                        identities_map[k] = {
                            "name": loc_n,
                            "email": loc_e,
                            "is_global": (loc_n == g_name and loc_e.lower() == g_email.lower()),
                            "local_repos": [],
                            "author_repos": [],
                            "commit_count": 0,
                            "role_badges": []
                        }
                    if r_name not in identities_map[k]["local_repos"]:
                        identities_map[k]["local_repos"].append(r_name)
                    if "仓库专属 (Local)" not in identities_map[k]["role_badges"]:
                        identities_map[k]["role_badges"].append("仓库专属 (Local)")
            except Exception:
                pass

            # Inspect recent commit author logs
            try:
                res_log = subprocess.run(
                    ["git", "log", "-n", "30", "--format=%an|%ae"],
                    cwd=r_path,
                    capture_output=True,
                    text=True,
                    timeout=4,
                    encoding="utf-8",
                    errors="ignore"
                )
                if res_log.returncode == 0:
                    for line in res_log.stdout.splitlines():
                        if "|" in line:
                            parts = line.split("|", 1)
                            aname, aemail = parts[0].strip(), parts[1].strip()
                            if not aname and not aemail:
                                continue
                            k = (aname, aemail.lower())
                            if k not in identities_map:
                                identities_map[k] = {
                                    "name": aname,
                                    "email": aemail,
                                    "is_global": (aname == g_name and aemail.lower() == g_email.lower()),
                                    "local_repos": [],
                                    "author_repos": [],
                                    "commit_count": 0,
                                    "role_badges": []
                                }
                            if r_name not in identities_map[k]["author_repos"]:
                                identities_map[k]["author_repos"].append(r_name)
                            identities_map[k]["commit_count"] += 1
                            if "代码提交作者 (Author)" not in identities_map[k]["role_badges"] and not identities_map[k]["is_global"] and not identities_map[k]["local_repos"]:
                                identities_map[k]["role_badges"].append("代码提交作者 (Author)")
            except Exception:
                pass

        # Convert to sorted list
        all_list = list(identities_map.values())
        # Sort: global first, then by total repos involved descending
        all_list.sort(key=lambda x: (not x["is_global"], - (len(x["local_repos"]) * 2 + len(x["author_repos"])), x["name"]))

        return {
            "global_user": {
                "name": g_name,
                "email": g_email
            },
            "total_identities": len(all_list),
            "identities": all_list,
            "ssh_hosts": self.get_ssh_config_hosts()
        }

key_manager = KeyManager()
