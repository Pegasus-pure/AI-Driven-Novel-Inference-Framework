# -*- coding: utf-8 -*-
"""SoulDecisionArbiter — 双人格仲裁器

根据 canon_soul 和 player_soul 仲裁主角在当前场景中的行为。
不调 LLM，纯逻辑计算。
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from .soul_state import SoulPossessionState

_log = logging.getLogger("Rain.SoulArbiter")


class SoulDecisionArbiter:
    """双人格仲裁器

    根据 blend_ratio 决定主角的行为倾向：
    - authentic（本我）= 玩家灵魂主导
    - conforming（贴合）= 原主灵魂主导
    """

    def __init__(self, soul_state: SoulPossessionState):
        self._soul = soul_state

    def decide(
        self,
        scene_context: dict,
        decision_mode: str = "auto",
        player_override: Optional[dict] = None,
    ) -> dict:
        """仲裁主角在当前场景中的行为

        Args:
            scene_context: 场景上下文
            decision_mode: auto | authentic | conforming
            player_override: 玩家在本拍的主动选择
                {"action_type": "authentic|conforming"}

        Returns:
            {
                "decision": str,
                "rationale": str,
                "dissonance_impact": float,
                "action_type": "authentic|conforming",
                "dominant_soul": str,
            }
        """
        mode = self._resolve_mode(decision_mode, player_override)
        result = self._execute_decision(mode, scene_context)
        # ★ 仅在玩家主动选择时记录（非 auto 模式）
        if player_override:
            self._soul.player_soul.record_choice(result["action_type"])
        return result

    # ────────────────────────────────────────────
    # 内部
    # ────────────────────────────────────────────

    def _resolve_mode(
        self, default_mode: str, override: Optional[dict]
    ) -> str:
        if override and override.get("action_type") in ("authentic", "conforming"):
            return override["action_type"]
        return default_mode

    def _execute_decision(self, mode: str, ctx: dict) -> dict:
        if mode == "authentic":
            return self._decide_authentic(ctx)
        elif mode == "conforming":
            return self._decide_conforming(ctx)
        else:  # auto
            return self._decide_blended(ctx)

    def _decide_authentic(self, ctx: dict) -> dict:
        """按玩家灵魂行事（本我）"""
        player = self._soul.player_soul
        tendency = player.behavioral_tendencies
        decision = (
            f"按自己的性格行事——{tendency.get('面对危险', '谨慎')}"
        )
        return {
            "decision": decision,
            "rationale": "玩家灵魂主导——做真实的自己",
            "dissonance_impact": 0.10,
            "action_type": "authentic",
            "dominant_soul": "player",
        }

    def _decide_conforming(self, ctx: dict) -> dict:
        """贴合 Canon 主角行事（贴合）"""
        canon = self._soul.canon_soul
        traits = canon.get("personality", {}).get("traits", ["谨慎"])
        expected = traits[0] if traits else "谨慎"
        decision = f"模仿原主角的行事风格——{expected}"
        return {
            "decision": decision,
            "rationale": "贴合原主——尽量不引起怀疑",
            "dissonance_impact": -0.08,
            "action_type": "conforming",
            "dominant_soul": "canon",
        }

    def _decide_blended(self, ctx: dict) -> dict:
        """根据 blend_ratio 混合决策"""
        if random.random() < self._soul.blend_ratio:
            return self._decide_authentic(ctx)
        else:
            return self._decide_conforming(ctx)
