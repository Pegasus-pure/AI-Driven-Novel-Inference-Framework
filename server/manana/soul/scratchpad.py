# -*- coding: utf-8 -*-
"""ScratchpadManager — 角色认知笔记管理

FIFO 截断 + 关键事件保留，控制 Token 预算。
"""

from __future__ import annotations

import logging
from typing import Optional

from .soul_state import NPCCognitiveDissonance, ObservationEntry

_log = logging.getLogger("Rain.Scratchpad")


class ScratchpadManager:
    """角色认知笔记管理器"""

    MAX_ENTRIES: int = 20
    """普通观察日志上限"""
    MAX_IMPORTANT: int = 10
    """关键事件上限"""

    def add_observation(
        self,
        state: NPCCognitiveDissonance,
        beat_id: str,
        action_type: str,
        observed_behavior: str,
        npc_reaction: str,
        is_important: bool = False,
    ) -> None:
        """添加一条观察记录

        自动 FIFO 截断。
        """
        entry = ObservationEntry(
            beat_id=beat_id,
            action_type=action_type,
            observed_behavior=observed_behavior,
            npc_reaction=npc_reaction,
            is_important=is_important,
        )
        state.scratchpad.append(entry)

        # FIFO 截断：分离普通和重要事件
        normal = [e for e in state.scratchpad if not e.is_important]
        important = [e for e in state.scratchpad if e.is_important]

        # 按重要性分别截断
        while len(normal) > self.MAX_ENTRIES:
            normal.pop(0)
        while len(important) > self.MAX_IMPORTANT:
            important.pop(0)

        # 合并回 scratchpad
        state.scratchpad = normal + important

    def get_for_motivation(
        self, state: NPCCognitiveDissonance
    ) -> list[ObservationEntry]:
        """获取注入 MotivationEngine 的笔记（最多 3 条普通 + 1 条重要）"""
        normal = [e for e in state.scratchpad if not e.is_important][-3:]
        important = [e for e in state.scratchpad if e.is_important][-1:]
        return normal + important

    def get_for_dialogue(
        self, state: NPCCognitiveDissonance
    ) -> list[ObservationEntry]:
        """获取注入 DialogueWeaver 的笔记（最多 2 条重要）"""
        return [e for e in state.scratchpad if e.is_important][-2:]

    def get_preview(self, state: NPCCognitiveDissonance) -> str:
        """获取最近一条记录的文本摘要"""
        if not state.scratchpad:
            return ""
        last = state.scratchpad[-1]
        return f"[{last.action_type}] {last.observed_behavior}"

    def read_scratchpad(self, state: NPCCognitiveDissonance, npc_id: str) -> str:
        """LLM 工具：读取 NPC 对主角的认知笔记（返回文本）"""
        if not state.scratchpad:
            return f"[{npc_id}] 暂无对主角的认知记录。"
        lines = [f"[{npc_id}] 对主角的认知笔记："]
        for e in state.scratchpad[-5:]:
            lines.append(
                f"- 第{e.beat_id}拍 [{e.action_type}]: {e.observed_behavior}"
                f" → NPC反应: {e.npc_reaction}"
            )
        return "\n".join(lines)

    def update_scratchpad(self, state: NPCCognitiveDissonance, npc_id: str,
                          beat_id: str, observation: str) -> None:
        """LLM 工具：NPC 主动记录对主角的观察"""
        self.add_observation(
            state=state,
            beat_id=beat_id,
            action_type="observation",
            observed_behavior=observation,
            npc_reaction="NPC 记录在认知笔记中",
            is_important=False,
        )
