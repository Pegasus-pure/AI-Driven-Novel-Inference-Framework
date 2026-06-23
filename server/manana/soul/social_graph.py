# -*- coding: utf-8 -*-
"""SocialPropagator — 怀疑传播与情绪传导

NPC 之间会讨论"主角最近不对劲"——怀疑在关系网中传播。
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from .soul_state import NPCCognitiveDissonance

_log = logging.getLogger("Rain.SocialGraph")


class SocialPropagator:
    """社交传播器"""

    PROPAGATE_THRESHOLD: float = 0.5
    """传播触发的 dissonance 阈值"""
    PROPAGATE_CHANCE: float = 0.3
    """传播概率"""
    PROPAGATE_CONFRONT_CHANCE: float = 0.6
    """对峙阶段传播概率"""
    PROPAGATE_DELTA: float = 0.1
    """每次传播的冲突增量"""
    CLUSTER_BONUS: float = 0.05
    """怀疑簇额外加成"""

    CONFRONT_THRESHOLD: float = 0.7
    """传播必要的最低 bond_strength"""

    # ────────────────────────────────────────────
    # 怀疑传播
    # ────────────────────────────────────────────

    def propagate(
        self,
        dissonance_map: dict[str, NPCCognitiveDissonance],
        social_graph: dict[str, list[dict]],
    ) -> dict[str, float]:
        """执行一轮怀疑传播

        Args:
            dissonance_map: {char_id: NPCCognitiveDissonance}
            social_graph: {char_id: [{"target": char_id, "bond_strength": float}, ...]}

        Returns:
            {char_id: total_delta} 被传播的 NPC 收到的增量
        """
        changes: dict[str, float] = {}

        for char_id, state in dissonance_map.items():
            if state.dissonance_score < self.PROPAGATE_THRESHOLD:
                continue

            # 获取该 NPC 的社交圈
            connections = social_graph.get(char_id, [])
            for conn in connections:
                target = conn.get("target", "")
                bond = conn.get("bond_strength", 0)
                if bond < self.CONFRONT_THRESHOLD:
                    continue
                if target not in dissonance_map:
                    continue

                # 概率传播
                chance = (
                    self.PROPAGATE_CONFRONT_CHANCE
                    if state.phase == "confrontational"
                    else self.PROPAGATE_CHANCE
                )
                if random.random() > chance:
                    continue

                delta = self.PROPAGATE_DELTA
                dissonance_map[target].dissonance_score = min(
                    1.0,
                    dissonance_map[target].dissonance_score + delta,
                )
                changes[target] = changes.get(target, 0) + delta
                dissonance_map[target].update_phase()

        # 怀疑簇加成：3 个以上 NPC 被传播时
        if len(changes) >= 3:
            for target in changes:
                dissonance_map[target].dissonance_score = min(
                    1.0,
                    dissonance_map[target].dissonance_score
                    + self.CLUSTER_BONUS,
                )
                changes[target] += self.CLUSTER_BONUS
                dissonance_map[target].update_phase()

        return changes

    # ────────────────────────────────────────────
    # 情绪传导
    # ────────────────────────────────────────────

    def propagate_emotion(
        self,
        source_id: str,
        emotion: str,
        social_graph: dict[str, list[dict]],
        dissonance_map: dict[str, NPCCognitiveDissonance],
    ) -> None:
        """从源 NPC 传导情绪到其社交圈

        Args:
            source_id: 情绪源 NPC
            emotion: 愤怒 | 困惑 | 接受
            social_graph: NPC 社交图
            dissonance_map: 认知冲突映射
        """
        connections = social_graph.get(source_id, [])
        for conn in connections:
            target = conn.get("target", "")
            bond = conn.get("bond_strength", 0)
            if bond < 0.4:
                continue
            if target not in dissonance_map:
                continue

            ts = dissonance_map[target]

            if emotion == "愤怒":
                ts.dissonance_score = min(
                    1.0, ts.dissonance_score + 0.05
                )

            elif emotion == "困惑":
                if random.random() < 0.3:
                    ts.dissonance_score = min(
                        1.0, ts.dissonance_score + 0.08
                    )

            elif emotion == "接受":
                ts.adaptation_progress = min(
                    1.0, ts.adaptation_progress + 0.1
                )
