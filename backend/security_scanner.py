import fnmatch
import os
import re
from typing import List, Dict, Any

class SecurityScanner:
    def __init__(self, sensitive_files: List[str] = None, secret_patterns: List[Dict[str, str]] = None):
        self.sensitive_files = sensitive_files or [
            ".env", ".env.*", "id_rsa", "id_rsa.pub", "id_ed25519", "id_ed25519.pub",
            "*.pem", "*.key", "credentials.json", "token.txt", "secrets.json",
            "*.pfx", "*.p12", "wp-config.php", "secring.gpg"
        ]
        self.secret_patterns = secret_patterns or [
            {
                "name": "Private Key Header",
                "regex": r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP)? ?PRIVATE KEY",
                "level": "critical"
            },
            {
                "name": "AWS Access Key ID",
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
                "name": "Generic API Secret Assignment",
                "regex": r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]",
                "level": "warning"
            }
        ]

    def scan_files(self, staged_files: List[str]) -> List[Dict[str, Any]]:
        findings = []
        for file_path in staged_files:
            file_name = os.path.basename(file_path)
            for pattern in self.sensitive_files:
                if fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(file_path, pattern):
                    findings.append({
                        "type": "file_rule",
                        "level": "critical",
                        "file": file_path,
                        "title": f"检测到敏感文件暂存: {file_name}",
                        "description": f"匹配高危文件名规则: `{pattern}`。此类文件通常包含机密配置、密钥或证书，严禁提交到代码仓库！"
                    })
                    break
        return findings

    def scan_diff(self, diff_text: str) -> List[Dict[str, Any]]:
        findings = []
        current_file = ""
        lines = diff_text.splitlines()

        for line in lines:
            if line.startswith("diff --git a/"):
                parts = line.split(" ")
                if len(parts) >= 4:
                    current_file = parts[3].lstrip("b/")
            elif line.startswith("+") and not line.startswith("+++"):
                added_content = line[1:].strip()
                for rule in self.secret_patterns:
                    match = re.search(rule["regex"], added_content)
                    if match:
                        matched_snippet = match.group(0)
                        # Mask snippet for safety
                        if len(matched_snippet) > 8:
                            masked = matched_snippet[:4] + "*" * (len(matched_snippet) - 8) + matched_snippet[-4:]
                        else:
                            masked = matched_snippet[:2] + "****"
                        findings.append({
                            "type": "secret_leak",
                            "level": rule.get("level", "critical"),
                            "file": current_file or "未知文件",
                            "title": f"潜在机密泄露: {rule['name']}",
                            "description": f"在新增代码行中检测到疑似密钥 `{masked}`，匹配规则 `{rule['regex']}`。"
                        })
        return findings

    def run_full_scan(self, staged_files: List[str], diff_text: str) -> Dict[str, Any]:
        file_findings = self.scan_files(staged_files)
        diff_findings = self.scan_diff(diff_text)
        all_findings = file_findings + diff_findings
        
        has_critical = any(f["level"] == "critical" for f in all_findings)
        has_warning = any(f["level"] == "warning" for f in all_findings)

        overall_status = "safe"
        if has_critical:
            overall_status = "critical"
        elif has_warning:
            overall_status = "warning"

        return {
            "status": overall_status,
            "total_issues": len(all_findings),
            "findings": all_findings
        }
