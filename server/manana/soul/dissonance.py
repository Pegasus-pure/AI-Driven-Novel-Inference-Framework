# -*- coding: utf-8 -*-
"""DissonanceUpdater — 认知冲突计算与更新

管理每个 NPC 对主角的认知冲突度：计算、衰减、阶段切换。
纯数学计算，不调 LLM。
"""

from __future__ import annotations

import logging
from typing import Optional

from .soul_state import NPCCognitiveDissonance

_log = logging.getLogger("Rain.Dissonance")


class DissonanceUpdater:
    """认知冲突更新器"""

    # 各因素权重
    WEIGHT_BEHAVIOR = 0.40
    WEIGHT_PERSONALITY = 0.35
    WEIGHT_RELATION = 0.25

    def update_all(
        self,
        dissonance_map: dict[str, NPCCognitiveDissonance],
        canon_soul: dict,
        player_soul: dict,
        recent_actions: list[dict],
    ) -> dict[str, dict]:
        """更新所有 NPC 的认知冲突

        Args:
            dissonance_map: {char_id: NPCCognitiveDissonance}
            canon_soul: Canon 主角人格
            player_soul: 玩家灵魂人格
            recent_actions: 最近主角行为记录

        Returns:
            {char_id: {dissonance_delta, new_score, new_phase, adaptation}}
        """
        changes = {}

        for char_id, state in dissonance_map.items():
            delta = self._compute_dissonance_delta(
                state, recent_actions
            )
            # ★ 每拍自然衰减，然后应用行动增量
            state.dissonance_score *= (1 - state.dissonance_decay_rate)
            state.dissonance_score = max(
                0.0, min(1.0, state.dissonance_score + delta)
            )

            # 适应
            if state.dissonance_score < 0.2:
                state.adaptation_progress = min(
                    1.0, state.adaptation_progress + 0.05
                )
                if state.adaptation_progress >= 0.9:
                    state.dissonance_score = 0.0

            state.update_phase()

            changes[char_id] = {
                "dissonance_delta": round(delta, 3),
                "new_score": round(state.dissonance_score, 3),
                "new_phase": state.phase,
                "adaptation": round(state.adaptation_progress, 3),
            }

        return changes

    def _compute_dissonance_delta(
        self,
        state: NPCCognitiveDissonance,
        recent_actions: list[dict],
    ) -> float:
        """计算本拍冲突变化量

        正值 = 冲突上升，负值 = 冲突下降
        """
        if not recent_actions:
            return -state.dissonance_decay_rate

        last_action = recent_actions[-1]
        action_type = last_action.get("action_type", "auto")

        if action_type == "authentic":
            return 0.10
        elif action_type == "conforming":
            return -0.08
        elif action_type == "auto":
            return 0.05 if last_action.get("dominant_soul") == "player" else -0.02

        return 0.0
