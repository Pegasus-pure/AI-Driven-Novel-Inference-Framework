# -*- coding: utf-8 -*-
"""AI-Driven-Novel-Inference-Framework — 统一路径定义

集中管理所有模块共享的文件路径，消除硬编码路径字符串。
所有路径使用 pathlib.Path，确保跨平台兼容。
"""

from __future__ import annotations

from pathlib import Path


# 项目根目录（从当前文件位置自动推断：server/paths.py → server/ → 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 顶级目录 ──
NOVEL_DIR = _PROJECT_ROOT / "novel"
SAVES_DIR = _PROJECT_ROOT / "saves"
STATIC_DIR = _PROJECT_ROOT / "static"
DOCS_DIR = _PROJECT_ROOT / "docs"

# ── 配置文件 ──
CONFIG_PATH = _PROJECT_ROOT / "config.yaml"
CONFIG_BACKUP_PATH = _PROJECT_ROOT / "config.yaml.bak"

# ── 辅助函数 ──

def get_novel_path(subpath: str = "") -> Path:
    """获取 novel 目录下的路径。"""
    return NOVEL_DIR / subpath if subpath else NOVEL_DIR


def get_save_path(subpath: str = "") -> Path:
    """获取 saves 目录下的路径。"""
    return SAVES_DIR / subpath if subpath else SAVES_DIR


def get_static_path(subpath: str = "") -> Path:
    """获取 static 目录下的路径。"""
    return STATIC_DIR / subpath if subpath else STATIC_DIR
