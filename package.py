import os
import sys
import shutil
import zipfile
import tarfile
import subprocess
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

PROJECT_ROOT = Path(__file__).parent.resolve()

def ensure_icons():
    icon_ico = PROJECT_ROOT / "assets" / "icon.ico"
    icon_png = PROJECT_ROOT / "assets" / "icon.png"
    if not icon_ico.exists() or not icon_png.exists():
        print("[Package] Generating application icons...")
        subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "generate_icons.py")], check=True)

def build():
    print(f"=======================================================")
    print(f"  [GitSentinel] 跨平台应用打包构建器")
    print(f"  操作系统: {sys.platform} ({os.name})")
    print(f"=======================================================\n")

    ensure_icons()

    spec_file = PROJECT_ROOT / "gitsentinel.spec"
    if not spec_file.exists():
        print(f"[Error] 找不到打包配置文件: {spec_file}")
        sys.exit(1)

    print(">>> 正在调用 PyInstaller 编译独立桌面应用程序...")
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm"
    ]
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print("[Error] PyInstaller 打包失败！")
        sys.exit(res.returncode)

    dist_dir = PROJECT_ROOT / "dist"
    output_bundle = dist_dir / "GitSentinel"

    # Post-packaging per platform
    if sys.platform == "win32":
        print("\n>>> 正在生成 Windows 便携发布压缩包...")
        zip_path = dist_dir / "GitSentinel-Windows-x64.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(output_bundle):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, output_bundle)
                    zf.write(full_path, arcname=os.path.join("GitSentinel", rel_path))
        print(f"[Success] Windows 应用打包完成: {zip_path} ({os.path.getsize(zip_path) // 1024 // 1024} MB)")

    elif sys.platform == "darwin":
        print("\n>>> 正在生成 macOS 应用程序包...")
        app_path = dist_dir / "GitSentinel.app"
        zip_path = dist_dir / "GitSentinel-macOS-Universal.zip"
        if app_path.exists():
            subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app_path), str(zip_path)])
            print(f"[Success] macOS 应用打包完成: {zip_path}")
        else:
            print(f"[Success] macOS 二进制构建完成于: {output_bundle}")

    else:
        print("\n>>> 正在生成 Linux 桌面快捷方式与发布归档...")
        # Create .desktop file
        desktop_content = """[Desktop Entry]
Name=GitSentinel
Comment=Git 统一管理与安全提交拦截系统
Exec=GitSentinel
Icon=gitsentinel
Terminal=false
Type=Application
Categories=Development;RevisionControl;
"""
        desktop_file = output_bundle / "gitsentinel.desktop"
        with open(desktop_file, "w", encoding="utf-8") as f:
            f.write(desktop_content)

        tar_path = dist_dir / "GitSentinel-Linux-x86_64.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tar:
            tar.add(output_bundle, arcname="GitSentinel")
        print(f"[Success] Linux 应用打包完成: {tar_path} ({os.path.getsize(tar_path) // 1024 // 1024} MB)")

    print("\n[Done] 打包流水线执行完毕！可在 dist/ 目录下获取应用文件。")

if __name__ == "__main__":
    build()
