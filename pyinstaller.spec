# -*- coding: utf-8 -*-
# PyInstaller spec file for AI-Driven-Novel-Inference-Framework
#
# 构建命令: pyinstaller pyinstaller.spec
#
# 产出: dist/AINovelFramework.exe (单文件)
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# 项目目录
_PROJECT_DIR = Path(__file__).resolve().parent

a = Analysis(
    [str(_PROJECT_DIR / 'launcher.py')],
    pathex=[str(_PROJECT_DIR)],
    binaries=[],
    datas=[
        # 静态前端资源
        (str(_PROJECT_DIR / 'static'), 'static'),
        # 配置文件
        (str(_PROJECT_DIR / 'config.yaml'), '.'),
        # 服务端模块
        (str(_PROJECT_DIR / 'server'), 'server'),
    ],
    hiddenimports=[
        'server',
        'server.main',
        'server.game_session',
        'server.world_state',
        'server.save_manager',
        'server.websocket_manager',
        'server.novel_loader',
        'server.manana',
        'server.manana.pipeline',
        'server.manana.agents',
        'server.manana.providers',
        'server.manana.config',
        'server.manana.schema',
        'server.manana.utils',
        'server.manana.base_agent',
        'uvicorn',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'websockets',
        'aiohttp',
        'yaml',
        'asyncio',
        'json',
        'logging',
        'pathlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AINovelFramework',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # 控制台模式（查看日志）；发布时可改为 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(_PROJECT_DIR / 'static' / 'favicon.ico') if (Path(_PROJECT_DIR) / 'static' / 'favicon.ico').exists() else None,
)
