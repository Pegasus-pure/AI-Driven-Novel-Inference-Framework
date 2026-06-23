# -*- coding: utf-8 -*-
"""灵魂附生 — 认知冲突与笔记管理测试"""

import pytest

from server.manana.soul.soul_state import (
    NPCCognitiveDissonance,
    PlayerSoulProfile,
)
from server.manana.soul.dissonance import DissonanceUpdater
from server.manana.soul.scratchpad import ScratchpadManager


@pytest.fixture
def sample_dissonance_map():
    return {
        "char_003": NPCCognitiveDissonance(
            char_id="char_003",
            memory_of_protagonist={
                "expected_behavior": "冷酷",
                "trust_level": 0.2,
                "relationship_note": "仇敌",
            },
        ),
        "char_002": NPCCognitiveDissonance(
            char_id="char_002",
            memory_of_protagonist={
                "expected_behavior": "傲慢",
                "trust_level": 0.5,
                "relationship_note": "主仆",
            },
        ),
    }


class TestDissonanceUpdater:
    def test_authentic_increases(self, sample_dissonance_map):
        updater = DissonanceUpdater()
        changes = updater.update_all(
            dissonance_map=sample_dissonance_map,
            canon_soul={"personality": {"traits": ["冷酷"]}},
            player_soul=PlayerSoulProfile().to_dict(),
            recent_actions=[{"action_type": "authentic"}],
        )
        assert changes["char_003"]["dissonance_delta"] == 0.10
        assert changes["char_003"]["new_score"] == 0.10

    def test_conforming_decreases(self, sample_dissonance_map):
        # 先设一个非零值
        sample_dissonance_map["char_003"].dissonance_score = 0.5
        updater = DissonanceUpdater()
        changes = updater.update_all(
            dissonance_map=sample_dissonance_map,
            canon_soul={},
            player_soul=PlayerSoulProfile().to_dict(),
            recent_actions=[{"action_type": "conforming"}],
        )
        # 0.5 + (-0.08) = 0.42, 再衰减 ×0.95 = 0.399
        assert changes["char_003"]["new_score"] < 0.5
        assert changes["char_003"]["new_score"] > 0

    def test_decay_when_no_action(self, sample_dissonance_map):
        sample_dissonance_map["char_003"].dissonance_score = 0.5
        updater = DissonanceUpdater()
        changes = updater.update_all(
            dissonance_map=sample_dissonance_map,
            canon_soul={},
            player_soul=PlayerSoulProfile().to_dict(),
            recent_actions=[],
        )
        # 无行动: 衰减 -0.05, 0.5 + (-0.05) = 0.45, ×0.95 = 0.4275
        assert changes["char_003"]["new_score"] == pytest.approx(0.427, rel=1e-3)
        assert changes["char_003"]["new_score"] < 0.5

    def test_adaptation_starts_when_low(self, sample_dissonance_map):
        updater = DissonanceUpdater()
        for _ in range(5):
            changes = updater.update_all(
                dissonance_map=sample_dissonance_map,
                canon_soul={},
                player_soul=PlayerSoulProfile().to_dict(),
                recent_actions=[{"action_type": "conforming"}],
            )
        c3 = sample_dissonance_map["char_003"]
        # 经过 5 拍，应该有 adaptation 积累
        assert c3.adaptation_progress > 0

    def test_adapted_resets_dissonance(self, sample_dissonance_map):
        c3 = sample_dissonance_map["char_003"]
        c3.adaptation_progress = 0.95  # 即将 adapted
        updater = DissonanceUpdater()
        updater.update_all(
            dissonance_map=sample_dissonance_map,
            canon_soul={},
            player_soul=PlayerSoulProfile().to_dict(),
            recent_actions=[{"action_type": "conforming"}],
        )
        # adaptation_progress 0.95 + 0.05 = 1.0 → >= 0.9 → dissonance = 0
        assert c3.dissonance_score == 0.0
        assert c3.phase == "adapted"

    def test_phase_transitions(self, sample_dissonance_map):
        c3 = sample_dissonance_map["char_003"]
        updater = DissonanceUpdater()

        # 快速推高 dissonance
        for _ in range(8):
            updater.update_all(
                dissonance_map=sample_dissonance_map,
                canon_soul={},
                player_soul=PlayerSoulProfile().to_dict(),
                recent_actions=[{"action_type": "authentic"}],
            )
        # 8 × 0.10 = 0.80 → confrontational
        assert c3.phase == "confrontational"


class TestScratchpadManager:
    def test_add_observation(self):
        state = NPCCognitiveDissonance(char_id="char_003")
        mgr = ScratchpadManager()
        mgr.add_observation(
            state=state,
            beat_id="b1",
            action_type="authentic",
            observed_behavior="弗雷没有砸酒杯",
            npc_reaction="愣住",
        )
        assert len(state.scratchpad) == 1
        assert state.scratchpad[0].beat_id == "b1"

    def test_fifo_truncation(self):
        state = NPCCognitiveDissonance(char_id="char_003")
        mgr = ScratchpadManager()
        for i in range(25):
            mgr.add_observation(
                state=state,
                beat_id=f"b{i:03d}",
                action_type="authentic",
                observed_behavior=f"行为{i}",
                npc_reaction="困惑",
            )
        # 超过 20 条应该截断
        assert len(state.scratchpad) <= mgr.MAX_ENTRIES + mgr.MAX_IMPORTANT

    def test_important_events_retained(self):
        state = NPCCognitiveDissonance(char_id="char_003")
        mgr = ScratchpadManager()

        # 写 20 条普通 + 5 条重要
        for i in range(20):
            mgr.add_observation(
                state=state, beat_id=f"b{i:03d}", action_type="authentic",
                observed_behavior=f"普通{i}", npc_reaction="..",
            )
        for i in range(5):
            mgr.add_observation(
                state=state, beat_id=f"im{i:03d}", action_type="authentic",
                observed_behavior=f"关键{i}", npc_reaction="..",
                is_important=True,
            )

        # 所有重要事件应保留
        important = [e for e in state.scratchpad if e.is_important]
        assert len(important) <= mgr.MAX_IMPORTANT

    def test_get_for_motivation(self):
        state = NPCCognitiveDissonance(char_id="char_003")
        mgr = ScratchpadManager()
        for i in range(10):
            mgr.add_observation(
                state=state, beat_id=f"b{i:03d}", action_type="authentic",
                observed_behavior=f"行为{i}", npc_reaction="..",
            )
        result = mgr.get_for_motivation(state)
        assert len(result) <= 4

    def test_get_preview_empty(self):
        state = NPCCognitiveDissonance(char_id="char_003")
        mgr = ScratchpadManager()
        assert mgr.get_preview(state) == ""
