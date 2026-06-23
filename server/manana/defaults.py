# -*- coding: utf-8 -*-
"""MaNA v4 — 统一默认值模块

集中管理各模块共享的默认配置（如默认选择项、默认行为等），
消除代码中散落的硬编码兜底值。
"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════
# 默认选择项（灵魂附生模式：二级选择结构）
# ═══════════════════════════════════════════════════════

_SOUL_DEFAULTS: dict[str, list[dict[str, Any]]] = {
    "authentic": [
        {"id": "auth_1", "text": "按自己的方式行动", "hint": "展现真实性格", "next_scene_hint": "本我行动"},
        {"id": "auth_2", "text": "说出真心话", "hint": "不再伪装", "next_scene_hint": "真情流露"},
        {"id": "auth_3", "text": "主动探索未知", "hint": "跟随直觉", "next_scene_hint": "探索未知"},
    ],
    "conforming": [
        {"id": "conf_1", "text": "模仿原主的口吻", "hint": "维持身份", "next_scene_hint": "维持身份"},
        {"id": "conf_2", "text": "按原主的习惯行事", "hint": "不暴露异常", "next_scene_hint": "融入角色"},
        {"id": "conf_3", "text": "保持沉默观察", "hint": "先了解情况", "next_scene_hint": "静观其变"},
    ],
}


def get_default_choices(min_count: int = 2) -> dict[str, list[dict[str, Any]]]:
    """获取默认 soul_decision（二级选择结构）。

    Args:
        min_count: 最少返回的选项数量（默认 2，保留兼容接口）

    Returns:
        dict 包含 authentic 和 conforming 两个数组
    """
    return dict(_SOUL_DEFAULTS)
