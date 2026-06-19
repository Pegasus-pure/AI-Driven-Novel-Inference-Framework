# -*- coding: utf-8 -*-
"""MaNA v4 — 统一默认值模块

集中管理各模块共享的默认配置（如默认选择项、默认行为等），
消除代码中散落的硬编码兜底值。
"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════
# 默认选择项
# ═══════════════════════════════════════════════════════

DEFAULT_CHOICES: list[dict[str, Any]] = [
    {"id": "c1", "text": "仔细观察周围环境", "hint": "了解你身处何方", "next_scene_hint": "observe_surroundings"},
    {"id": "c2", "text": "检查自己的状态和记忆", "hint": "弄清楚你是谁", "next_scene_hint": "self_examination"},
    {"id": "c3", "text": "向前迈出一步探索", "hint": "主动探索未知世界", "next_scene_hint": "step_forward"},
]


def get_default_choices(min_count: int = 2) -> list[dict[str, Any]]:
    """获取默认 choices，补齐到至少 min_count 个。

    Args:
        min_count: 最少返回的选项数量（默认 2）

    Returns:
        choices 列表，每个包含 id / text / hint / next_scene_hint
    """
    choices = list(DEFAULT_CHOICES)
    fallback_idx = 1
    while len(choices) < min_count:
        fallback_idx += 1
        choices.append({
            "id": f"c{len(choices) + 1}",
            "text": "继续前进",
            "hint": "推进剧情",
            "next_scene_hint": "proceed",
        })
    return choices
