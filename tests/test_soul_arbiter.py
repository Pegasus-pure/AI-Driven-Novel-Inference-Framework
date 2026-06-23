# -*- coding: utf-8 -*-
"""灵魂附生 — 仲裁器测试"""

import pytest

from server.manana.soul.soul_state import (
    PlayerSoulProfile,
    SoulPossessionState,
)
from server.manana.soul.arbiter import SoulDecisionArbiter


class TestSoulDecisionArbiter:
    @pytest.fixture
    def arbiter(self):
        soul = SoulPossessionState(
            canon_soul={
                "name": "弗雷",
                "personality": {"traits": ["隐忍", "自我牺牲"]},
            },
            player_soul=PlayerSoulProfile(
                behavioral_tendencies={"面对危险": "勇敢"},
            ),
            blend_ratio=0.8,
        )
        return SoulDecisionArbiter(soul)

    def test_authentic_decision(self, arbiter):
        result = arbiter.decide(
            scene_context={},
            decision_mode="authentic",
        )
        assert result["action_type"] == "authentic"
        assert result["dominant_soul"] == "player"
        assert result["dissonance_impact"] == 0.10

    def test_conforming_decision(self, arbiter):
        result = arbiter.decide(
            scene_context={},
            decision_mode="conforming",
        )
        assert result["action_type"] == "conforming"
        assert result["dominant_soul"] == "canon"
        assert result["dissonance_impact"] == -0.08

    def test_player_override_authentic(self, arbiter):
        result = arbiter.decide(
            scene_context={},
            decision_mode="auto",
            player_override={"action_type": "authentic"},
        )
        assert result["action_type"] == "authentic"

    def test_player_override_conforming(self, arbiter):
        result = arbiter.decide(
            scene_context={},
            decision_mode="auto",
            player_override={"action_type": "conforming"},
        )
        assert result["action_type"] == "conforming"

    def test_blended_with_high_ratio(self):
        """blend_ratio 0.8 时更可能输出 player"""
        soul = SoulPossessionState(
            canon_soul={"name": "弗雷", "personality": {"traits": ["隐忍"]}},
            blend_ratio=0.9,
        )
        arbiter = SoulDecisionArbiter(soul)
        results = [
            arbiter.decide(scene_context={}, decision_mode="auto")
            for _ in range(100)
        ]
        player_count = sum(
            1 for r in results if r["dominant_soul"] == "player"
        )
        assert player_count > 60  # 90% 概率 × 100 次应该 > 60

    def test_records_choice_on_authentic(self, arbiter):
        before = arbiter._soul.player_soul.total_choices
        arbiter.decide(scene_context={}, decision_mode="authentic")
        after = arbiter._soul.player_soul.total_choices
        assert after == before + 1

    def test_records_choice_on_conforming(self, arbiter):
        before = arbiter._soul.player_soul.total_choices
        arbiter.decide(scene_context={}, decision_mode="conforming")
        after = arbiter._soul.player_soul.total_choices
        assert after == before + 1
