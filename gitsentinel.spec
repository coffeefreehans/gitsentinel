# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None
project_root = Path('.').resolve()

# Determine platform icon
if sys.platform == 'win32':
    icon_file = str(project_root / 'assets' / 'icon.ico')
else:
    icon_file = str(project_root / 'assets' / 'icon.png')

datas = [
    ('frontend/static', 'frontend/static'),
    ('assets', 'assets'),
    ('interceptor', 'interceptor'),
    ('backend', 'backend'),
]

hidden_imports = [
    # Uvicorn
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    # FastAPI & Starlette
    'fastapi',
    'fastapi.staticfiles',
    'fastapi.responses',
    'starlette',
    'starlette.staticfiles',
    'starlette.routing',
    'websockets',
    # PyWebview
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'webview.platforms.cocoa',
    'webview.platforms.gtk',
    # Tray & GUI
    'pystray',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'tkinter',
    'tkinter.ttk',
    'tkinter.font',
    'tkinter.messagebox',
    # Security & SSH
    'cryptography',
    'paramiko',
]

a = Analysis(
    ['sentinel.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GitSentinel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed desktop application (no console popup)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GitSentinel',
)

# On macOS, generate .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='GitSentinel.app',
        icon=icon_file if os.path.exists(icon_file) else None,
        bundle_identifier='com.gitsentinel.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'LSUIElement': False,
            'CFBundlePackageType': 'APPL',
            'CFBundleSignature': '????',
            'LSMinimumSystemVersion': '10.13.0',
        },
    )
