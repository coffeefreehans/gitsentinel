import argparse
import os
import re
import sys
import time
import subprocess
from pathlib import Path

# Add project root to sys.path so we can import backend modules
project_root = Path(__file__).parent.parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.config import config_manager
from backend.security_scanner import SecurityScanner
from backend.notifier import notifier

def get_git_info(repo_dir: str, hook_type: str = "commit", push_stdin_lines: list = None):
    def _run(args):
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return res.stdout.strip()
        except Exception:
            return ""

    branch = _run(["branch", "--show-current"]) or "detached"
    is_delete = False

    if hook_type == "push":
        zero_sha = "0000000000000000000000000000000000000000"
        diff_range = ""

        if push_stdin_lines:
            all_deletes = True
            ranges = []
            for line in push_stdin_lines:
                parts = line.split()
                if len(parts) >= 4:
                    l_ref, l_sha, r_ref, r_sha = parts[0], parts[1], parts[2], parts[3]
                    if l_sha == zero_sha:
                        # Deleting a remote branch
                        continue
                    all_deletes = False
                    if r_sha == zero_sha:
                        # Pushing a brand-new branch to remote
                        revs = _run(["rev-list", l_sha, "--not", "--remotes"]).splitlines()
                        if revs:
                            oldest = revs[-1].strip()
                            parent = _run(["rev-parse", f"{oldest}^"])
                            if parent:
                                ranges.append(f"{parent}..{l_sha}")
                            else:
                                ranges.append(f"4b825dc642cb6eb9a060e54bf8d69288fbee4904..{l_sha}")
                        else:
                            parent = _run(["rev-parse", f"{l_sha}^"])
                            if parent:
                                ranges.append(f"{parent}..{l_sha}")
                            else:
                                ranges.append(f"4b825dc642cb6eb9a060e54bf8d69288fbee4904..{l_sha}")
                    else:
                        ranges.append(f"{r_sha}..{l_sha}")
                elif len(parts) == 2:
                    ranges.append(f"{parts[1]}..{parts[0]}")

            if all_deletes and push_stdin_lines:
                return {
                    "branch": branch,
                    "staged_files": [],
                    "diff_stat": "远端分支删除操作，无新增文件上传",
                    "diff_text": "",
                    "is_delete": True
                }

            if ranges:
                diff_range = ranges[0]

        if not diff_range:
            # Fallback when stdin is empty (interactive run, test mode, or standard push)
            upstream = _run(["rev-parse", "--abbrev-ref", "@{u}"])
            if upstream:
                diff_range = f"{upstream}..HEAD"
            else:
                diff_range = "HEAD~1..HEAD"

        status_raw = _run(["diff", "--name-status", diff_range])
        diff_stat = _run(["diff", "--stat", diff_range])
        diff_text = _run(["diff", diff_range])

        # If diff_range produced nothing, try unpushed commits check
        if not status_raw:
            unpushed = _run(["log", "--oneline", "@{u}..HEAD"])
            if unpushed:
                status_raw = _run(["diff", "--name-status", "@{u}..HEAD"])
                diff_stat = _run(["diff", "--stat", "@{u}..HEAD"])
                diff_text = _run(["diff", "@{u}..HEAD"])

        # If still empty (e.g. single root commit), diff against empty tree
        if not status_raw:
            status_raw = _run(["diff-tree", "-r", "--no-commit-id", "--name-status", "HEAD"])
            diff_stat = _run(["show", "--stat", "--oneline", "HEAD"])
            diff_text = _run(["show", "HEAD"])

    else:
        # Pre-commit: diff --cached (staged changes)
        status_raw = _run(["diff", "--cached", "--name-status"])
        diff_stat = _run(["diff", "--cached", "--stat"])
        diff_text = _run(["diff", "--cached"])

    files = []
    for line in status_raw.splitlines():
        if line.strip():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append({"status": parts[0].strip(), "file": parts[1].strip()})
            else:
                files.append({"status": "M", "file": line.strip()})

    return {
        "branch": branch,
        "staged_files": files,
        "diff_stat": diff_stat,
        "diff_text": diff_text,
        "is_delete": is_delete
    }

def run_tkinter_dialog(repo_name: str, repo_dir: str, git_info: dict, scan_result: dict, hook_type: str = "commit") -> bool:
    import tkinter as tk
    from tkinter import ttk, font

    confirmed = [False]
    is_push = (hook_type == "push")
    action_name = "上传" if is_push else "提交"
    cmd_name = "git push" if is_push else "git commit"
    has_issues = bool(scan_result.get("findings"))

    root = tk.Tk()
    root.title(f"🛡️ GitSentinel {action_name}拦截确认 - {repo_name} ({cmd_name})")
    root.geometry("860x680")
    root.minsize(720, 540)
    root.configure(bg="#0f172a")

    # Center window on screen
    root.update_idletasks()
    w = 860
    h = 680
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, int((sw - w) / 2))
    y = max(0, int((sh - h) / 2))
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Set always on top & focus
    root.attributes("-topmost", True)
    root.after(100, lambda: root.focus_force())

    # Styling constants
    BG_DARK = "#0f172a"
    BG_CARD = "#1e293b"
    BG_CARD_HOVER = "#334155"
    FG_TEXT = "#f8fafc"
    FG_MUTED = "#94a3b8"
    COLOR_PRIMARY = "#38bdf8"
    COLOR_SUCCESS = "#10b981"
    COLOR_DANGER = "#ef4444"
    COLOR_WARNING = "#f59e0b"

    # Cross-platform font definitions
    if sys.platform == "darwin":
        ui_family = "PingFang SC"
        code_family = "Menlo"
    elif sys.platform == "win32":
        ui_family = "Microsoft YaHei UI"
        code_family = "Consolas"
    else:
        ui_family = "DejaVu Sans"
        code_family = "DejaVu Sans Mono"

    title_font = font.Font(family=ui_family, size=13, weight="bold")
    header_font = font.Font(family=ui_family, size=10, weight="bold")
    normal_font = font.Font(family=ui_family, size=9)
    code_font = font.Font(family=code_family, size=9)
    badge_font = font.Font(family=ui_family, size=8, weight="bold")

    # 1. Top Header Frame
    header_frame = tk.Frame(root, bg=BG_CARD, padx=16, pady=12)
    header_frame.pack(fill="x", padx=14, pady=(14, 8))

    top_row = tk.Frame(header_frame, bg=BG_CARD)
    top_row.pack(fill="x")

    lbl_title = tk.Label(
        top_row,
        text=f"🛡️ GitSentinel 代码{action_name}安全拦截审核 ({cmd_name})",
        font=title_font,
        fg=COLOR_PRIMARY,
        bg=BG_CARD
    )
    lbl_title.pack(side="left")

    # Badges
    badge_frame = tk.Frame(top_row, bg=BG_CARD)
    badge_frame.pack(side="right")

    branch_badge = tk.Label(
        badge_frame,
        text=f" 🌿 {git_info['branch']} ",
        font=badge_font,
        fg="#ffffff",
        bg="#0284c7",
        padx=6,
        pady=2
    )
    branch_badge.pack(side="left", padx=4)

    type_badge = tk.Label(
        badge_frame,
        text=f" 🚀 {action_name}拦截 " if is_push else f" 💾 {action_name}拦截 ",
        font=badge_font,
        fg="#ffffff",
        bg="#6366f1",
        padx=6,
        pady=2
    )
    type_badge.pack(side="left", padx=4)

    if has_issues:
        status_color = COLOR_DANGER if scan_result["status"] == "critical" else COLOR_WARNING
        status_text = f" ⚠️ 发现 {scan_result['total_issues']} 项敏感风险 "
    else:
        status_color = COLOR_SUCCESS
        status_text = " 🟢 安全审核通过 "

    sec_badge = tk.Label(
        badge_frame,
        text=status_text,
        font=badge_font,
        fg="#ffffff",
        bg=status_color,
        padx=6,
        pady=2
    )
    sec_badge.pack(side="left", padx=4)

    # Repo Path and Summary
    repo_info_lbl = tk.Label(
        header_frame,
        text=f"仓库目录: {repo_name}  ({repo_dir})",
        font=normal_font,
        fg=FG_MUTED,
        bg=BG_CARD
    )
    repo_info_lbl.pack(anchor="w", pady=(4, 0))

    # 2. Prominent Status Prompt Banner: Explicitly inform user whether sensitive files exist!
    if has_issues:
        # RED ALERT BANNER: Sensitive files / secrets detected
        alert_bg = "#380b0b"
        alert_border = COLOR_DANGER
        alert_frame = tk.Frame(root, bg=alert_bg, highlightbackground=alert_border, highlightthickness=2, padx=14, pady=10)
        alert_frame.pack(fill="x", padx=14, pady=(0, 6))

        lbl_alert_title = tk.Label(
            alert_frame,
            text=f"🔴 拦截预警：检测到 {len(scan_result['findings'])} 个高危敏感文件 / 机密泄露风险！",
            font=header_font,
            fg="#fca5a5",
            bg=alert_bg
        )
        lbl_alert_title.pack(anchor="w")

        lbl_alert_desc = tk.Label(
            alert_frame,
            text=f"系统在本次待{action_name}的代码中发现了敏感凭据或机密配置文件。若继续{action_name}到远程平台，极易造成账号泄露与安全事故！\n👉 强烈建议：点击下方【⛔ 拦截阻止】，立即阻止本次代码{action_name}并清理敏感文件；如确系测试数据，请勾选下方确认后放行。",
            font=normal_font,
            fg="#fecaca",
            bg=alert_bg,
            justify="left"
        )
        lbl_alert_desc.pack(anchor="w", pady=(4, 6))

        for f in scan_result["findings"][:4]:
            f_row = tk.Frame(alert_frame, bg=alert_bg)
            f_row.pack(fill="x", pady=1)
            lbl_tag = tk.Label(f_row, text=f" [{f['file']}] ", font=badge_font, fg="#ffffff", bg="#b91c1c", padx=4, pady=1)
            lbl_tag.pack(side="left", padx=(0, 6))
            lbl_item = tk.Label(
                f_row,
                text=f"{f['title']} - {f['description']}",
                font=normal_font,
                fg="#fecaca",
                bg=alert_bg,
                wraplength=720,
                justify="left"
            )
            lbl_item.pack(side="left", fill="x")
    else:
        # GREEN SAFE BANNER: Clean & Verified
        safe_bg = "#052e16"
        safe_border = COLOR_SUCCESS
        safe_frame = tk.Frame(root, bg=safe_bg, highlightbackground=safe_border, highlightthickness=2, padx=14, pady=10)
        safe_frame.pack(fill="x", padx=14, pady=(0, 6))

        lbl_safe_title = tk.Label(
            safe_frame,
            text="🟢 安全审核通过：未检测到任何敏感文件或危险密钥",
            font=header_font,
            fg="#6ee7b7",
            bg=safe_bg
        )
        lbl_safe_title.pack(anchor="w")

        lbl_safe_desc = tk.Label(
            safe_frame,
            text=f"已对本次待{action_name}的全部变动文件及 Diff 代码完成安全合规扫描，未发现 API Key、私钥证书或高危敏感配置文件。\n✅ 变动内容安全合规，请点击下方【🟢 确认放行】继续完成本次代码{action_name}。",
            font=normal_font,
            fg="#a7f3d0",
            bg=safe_bg,
            justify="left"
        )
        lbl_safe_desc.pack(anchor="w", pady=(4, 0))

    # 3. Notebook Tabs (Files / Diff / Stat)
    style = ttk.Style()
    style.theme_use("default")
    style.configure("TNotebook", background=BG_DARK, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_MUTED, padding=[12, 6], font=normal_font)
    style.map("TNotebook.Tab", background=[("selected", BG_CARD_HOVER)], foreground=[("selected", FG_TEXT)])

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=14, pady=6)

    # Tab 1: Files List
    files_tab = tk.Frame(notebook, bg=BG_CARD)
    notebook.add(files_tab, text=f" 📋 待{action_name}文件清单 ({len(git_info['staged_files'])}) ")

    files_list_frame = tk.Frame(files_tab, bg=BG_CARD, padx=10, pady=10)
    files_list_frame.pack(fill="both", expand=True)

    files_canvas = tk.Canvas(files_list_frame, bg=BG_CARD, highlightthickness=0)
    scrollbar_files = tk.Scrollbar(files_list_frame, orient="vertical", command=files_canvas.yview)
    files_inner = tk.Frame(files_canvas, bg=BG_CARD)

    files_inner.bind("<Configure>", lambda e: files_canvas.configure(scrollregion=files_canvas.bbox("all")))
    files_canvas.create_window((0, 0), window=files_inner, anchor="nw")
    files_canvas.configure(yscrollcommand=scrollbar_files.set)

    files_canvas.pack(side="left", fill="both", expand=True)
    scrollbar_files.pack(side="right", fill="y")

    status_map = {
        "A": ("新增", COLOR_SUCCESS),
        "M": ("修改", COLOR_PRIMARY),
        "D": ("删除", COLOR_DANGER),
        "R": ("重命名", COLOR_WARNING)
    }

    if not git_info["staged_files"]:
        lbl_empty = tk.Label(files_inner, text=f"本次无任何待{action_name}变动文件", font=normal_font, fg=FG_MUTED, bg=BG_CARD)
        lbl_empty.pack(anchor="w", padx=8, pady=8)
    else:
        for item in git_info["staged_files"]:
            status_char = item["status"]
            st_text, st_color = status_map.get(status_char, (status_char, FG_MUTED))
            row = tk.Frame(files_inner, bg=BG_CARD, pady=3)
            row.pack(fill="x", expand=True)

            badge = tk.Label(row, text=f" {st_text} ", font=badge_font, fg="#ffffff", bg=st_color, width=6)
            badge.pack(side="left", padx=(4, 8))

            file_lbl = tk.Label(row, text=item["file"], font=code_font, fg=FG_TEXT, bg=BG_CARD)
            file_lbl.pack(side="left")

    # Tab 2: Diff Preview
    diff_tab = tk.Frame(notebook, bg=BG_CARD)
    notebook.add(diff_tab, text=" 🔍 代码差异 Diff 预览 ")

    diff_text_widget = tk.Text(
        diff_tab,
        bg="#090d16",
        fg=FG_TEXT,
        insertbackground=FG_TEXT,
        font=code_font,
        wrap="none",
        padx=10,
        pady=8,
        highlightthickness=0
    )
    diff_scroll_y = tk.Scrollbar(diff_tab, orient="vertical", command=diff_text_widget.yview)
    diff_scroll_x = tk.Scrollbar(diff_tab, orient="horizontal", command=diff_text_widget.xview)
    diff_text_widget.configure(yscrollcommand=diff_scroll_y.set, xscrollcommand=diff_scroll_x.set)

    diff_scroll_y.pack(side="right", fill="y")
    diff_scroll_x.pack(side="bottom", fill="x")
    diff_text_widget.pack(side="left", fill="both", expand=True)

    # Configure Diff Syntax Highlighting tags
    diff_text_widget.tag_configure("add", foreground="#4ade80", background="#064e3b")
    diff_text_widget.tag_configure("delete", foreground="#f87171", background="#450a0a")
    diff_text_widget.tag_configure("header", foreground="#38bdf8", font=font.Font(family="Consolas", size=9, weight="bold"))
    diff_text_widget.tag_configure("meta", foreground="#94a3b8")

    diff_lines = git_info["diff_text"].splitlines()
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---"):
            diff_text_widget.insert("end", line + "\n", "meta")
        elif line.startswith("+"):
            diff_text_widget.insert("end", line + "\n", "add")
        elif line.startswith("-"):
            diff_text_widget.insert("end", line + "\n", "delete")
        elif line.startswith("@@"):
            diff_text_widget.insert("end", line + "\n", "header")
        else:
            diff_text_widget.insert("end", line + "\n")
    diff_text_widget.configure(state="disabled")

    # Tab 3: Git Stat Summary
    stat_tab = tk.Frame(notebook, bg=BG_CARD)
    notebook.add(stat_tab, text=" 📊 变动统计 Stat ")

    stat_text_widget = tk.Text(
        stat_tab,
        bg="#090d16",
        fg=FG_TEXT,
        font=code_font,
        padx=12,
        pady=10,
        highlightthickness=0
    )
    stat_text_widget.insert("end", git_info["diff_stat"] or "无统计数据")
    stat_text_widget.configure(state="disabled")
    stat_text_widget.pack(fill="both", expand=True)

    # 4. Bottom Actions Frame: Explicitly provides "放行" and "拦截" buttons!
    bottom_frame = tk.Frame(root, bg=BG_DARK, pady=10, padx=14)
    bottom_frame.pack(fill="x")

    # Risk confirmation checkbox (only if sensitive issues exist)
    force_var = tk.BooleanVar(value=not has_issues)
    if has_issues:
        chk_force = tk.Checkbutton(
            bottom_frame,
            text=f"我已知晓上述敏感文件/密钥泄露风险，确认仍要强制放行本次{action_name}",
            variable=force_var,
            font=normal_font,
            fg="#f87171",
            bg=BG_DARK,
            selectcolor=BG_CARD,
            activebackground=BG_DARK,
            activeforeground="#f87171",
            command=lambda: update_confirm_btn()
        )
        chk_force.pack(anchor="w", pady=(0, 8))

    btn_row = tk.Frame(bottom_frame, bg=BG_DARK)
    btn_row.pack(fill="x")

    lbl_hint = tk.Label(
        btn_row,
        text=f"快捷键: [Esc] 拦截阻止此次{action_name}   [Enter] 确认放行继续{action_name}",
        font=normal_font,
        fg=FG_MUTED,
        bg=BG_DARK
    )
    lbl_hint.pack(side="left")

    def on_abort():
        confirmed[0] = False
        root.destroy()

    def on_proceed():
        if has_issues and not force_var.get():
            return
        confirmed[0] = True
        root.destroy()

    # BUTTON 1: ⛔ 拦截 (阻止上传/提交) - Exits with code 1
    btn_abort = tk.Button(
        btn_row,
        text=f" ⛔ 拦截阻止 (阻止此次{action_name}) ",
        font=header_font,
        fg="#ffffff",
        bg=COLOR_DANGER,
        activebackground="#b91c1c",
        activeforeground="#ffffff",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2",
        command=on_abort
    )
    btn_abort.pack(side="right", padx=(10, 0))

    # BUTTON 2: 🟢 放行 (继续上传/提交) - Exits with code 0
    btn_proceed = tk.Button(
        btn_row,
        text=f" 🟢 确认放行 (继续本次{action_name}) ",
        font=header_font,
        fg="#ffffff",
        bg=COLOR_SUCCESS,
        activebackground="#047857",
        activeforeground="#ffffff",
        relief="flat",
        padx=18,
        pady=8,
        cursor="hand2",
        command=on_proceed
    )
    btn_proceed.pack(side="right")

    def update_confirm_btn():
        if has_issues and not force_var.get():
            btn_proceed.configure(
                state="disabled",
                bg="#334155",
                text=f" 🟢 确认放行 (需先勾选风险) "
            )
        else:
            btn_proceed.configure(
                state="normal",
                bg=COLOR_SUCCESS,
                text=f" 🟢 确认放行 (继续本次{action_name}) "
            )

    update_confirm_btn()

    # Bind Hotkeys
    root.bind("<Escape>", lambda e: on_abort())
    root.bind("<Return>", lambda e: on_proceed() if btn_proceed["state"] != "disabled" else None)

    root.mainloop()
    return confirmed[0]

def normalize_repo_dir(raw_path: str) -> str:
    if not raw_path:
        raw_path = os.getcwd()
    
    # Normalize Git Bash / MSYS2 paths on Windows like /d/Projects/... or /c/Users/...
    if os.name == 'nt' and re.match(r'^/[a-zA-Z]/', raw_path):
        raw_path = re.sub(r'^/([a-zA-Z])/', r'\1:/', raw_path)

    if not os.path.exists(raw_path):
        try:
            res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                top = res.stdout.strip()
                if os.name == 'nt' and re.match(r'^/[a-zA-Z]/', top):
                    top = re.sub(r'^/([a-zA-Z])/', r'\1:/', top)
                if os.path.exists(top):
                    return os.path.normpath(top)
        except Exception:
            pass
        return os.path.normpath(os.getcwd())
    return os.path.normpath(raw_path)

def log_interceptor(msg: str):
    try:
        log_dir = Path.home() / ".git-sentinel"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "interceptor.log", "a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="GitSentinel Git Interceptor")
    parser.add_argument("--repo-dir", default=os.getcwd(), help="Repository root directory")
    parser.add_argument("--hook-type", default="commit", choices=["commit", "push"], help="Hook type: commit or push")
    parser.add_argument("--global-hook", action="store_true", help="Invoked as a global git hook")
    args, unknown = parser.parse_known_args()

    repo_dir = normalize_repo_dir(args.repo_dir)
    repo_name = os.path.basename(repo_dir) or "GitRepository"
    hook_type = args.hook_type
    action_name = "上传" if hook_type == "push" else "提交"
    cmd_name = "git push" if hook_type == "push" else "git commit"
    log_interceptor(f"Hook invoked for: {repo_name} (path: {repo_dir}, type: {hook_type})")

    # 1. Check if user set bypass environment variable
    if os.environ.get("GIT_SENTINEL_SKIP") == "1":
        log_interceptor("Bypassed via GIT_SENTINEL_SKIP=1")
        sys.exit(0)

    # 2. Check if global hook is active, verify if this specific repo has intercept enabled
    repo_cfg = config_manager.get_repo_setting(repo_dir)
    if not repo_cfg.get("intercept_enabled", True):
        log_interceptor(f"Bypassed: repo '{repo_name}' intercept_enabled=False")
        sys.exit(0)

    # 3. Read stdin if hook_type is push
    push_stdin_lines = []
    if hook_type == "push":
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
                push_stdin_lines = [l.strip() for l in raw.splitlines() if l.strip()]
        except Exception:
            pass

    # 4. Retrieve Git info based on hook type
    git_info = get_git_info(repo_dir, hook_type=hook_type, push_stdin_lines=push_stdin_lines)

    # If deleting branch on remote, allow immediately without blocking
    if git_info.get("is_delete"):
        log_interceptor(f"Delete branch operation in {repo_name}, exiting 0")
        sys.exit(0)

    # If no changed files, exit 0 immediately
    if not git_info["staged_files"]:
        log_interceptor(f"No changed files in {repo_name} for {hook_type}, exiting 0")
        sys.exit(0)

    # 5. Run Security Scanner
    scanner = SecurityScanner(
        sensitive_files=config_manager.get("security_rules", {}).get("sensitive_files"),
        secret_patterns=config_manager.get("security_rules", {}).get("secret_patterns")
    )
    changed_names = [item["file"] for item in git_info["staged_files"]]
    scan_result = scanner.run_full_scan(changed_names, git_info["diff_text"])
    log_interceptor(f"Files: {len(changed_names)}, scanner result: {scan_result['status']}")

    # Notify UI about intercepted attempt
    try:
        notifier.notify(
            title=f"🛡️ 拦截到代码{action_name}请求: {repo_name}",
            message=f"分支: {git_info['branch']} | 变动文件: {len(git_info['staged_files'])} | 风险状态: {'🔴 存在高危敏感文件' if scan_result['findings'] else '🟢 安全审核通过'}",
            event_type="alert",
            repo_path=repo_dir
        )
    except Exception:
        pass

    # 6. Check Headless automation flags (useful for automated testing or non-GUI CI)
    if os.environ.get("GIT_SENTINEL_HEADLESS") == "1":
        if os.environ.get("GIT_SENTINEL_AUTO_APPROVE") == "1":
            print(f">>> [GitSentinel] Headless 自动测试通过，放行{action_name}。({cmd_name} proceeds)")
            sys.exit(0)
        else:
            print(f">>> [GitSentinel] Headless 自动拦截阻止！({cmd_name} aborted)")
            sys.exit(1)

    # 7. Launch interactive confirmation dialog
    try:
        allowed = run_tkinter_dialog(repo_name, repo_dir, git_info, scan_result, hook_type=hook_type)
        if allowed:
            print(f">>> [GitSentinel] 审核通过，已放行本次代码{action_name}。({cmd_name} 继续执行)")
            sys.exit(0)
        else:
            print(f">>> [GitSentinel] 操作已被用户拦截阻止！({cmd_name} 已终止，退出代码 1)")
            sys.exit(1)
    except Exception as e:
        # If GUI failed to load (e.g. headless environment or no DISPLAY), fallback to terminal prompt
        print(f"\n[GitSentinel] GUI 弹窗启动异常 ({e})，切换为终端交互确认模式：")
        print(f"仓库: {repo_name} | 分支: {git_info['branch']} | 变动文件: {len(changed_names)}")
        if scan_result["findings"]:
            print(f"🔴 拦截警告：检测到 {len(scan_result['findings'])} 项安全隐患！")
            for f in scan_result["findings"]:
                print(f"   - [{f['file']}] {f['title']}")
        else:
            print("🟢 安全审核通过：未检测到任何敏感文件或危险密钥。")
        try:
            choice = input(f"是否确认放行此次{action_name}？ (y=放行继续 / N=拦截阻止): ").strip().lower()
            if choice == "y":
                print(f">>> [GitSentinel] 终端确认放行本次{action_name}。")
                sys.exit(0)
            else:
                print(f">>> [GitSentinel] 操作已被用户拦截阻止！({cmd_name} 已终止)")
                sys.exit(1)
        except Exception:
            sys.exit(1)

if __name__ == "__main__":
    main()
