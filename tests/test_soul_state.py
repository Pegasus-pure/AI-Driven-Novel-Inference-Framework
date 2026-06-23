# -*- coding: utf-8 -*-
"""灵魂附生 — 数据模型测试"""

import pytest

from server.manana.soul.soul_state import (
    PlayerSoulProfile,
    SoulPossessionState,
    NPCCognitiveDissonance,
    ObservationEntry,
)


class TestPlayerSoulProfile:
    def test_default_creation(self):
        profile = PlayerSoulProfile()
        assert profile.soul_name == "异界旅人"
        assert profile.total_choices == 0
        assert not profile.is_derived

    def test_record_choice(self):
        profile = PlayerSoulProfile()
        profile.record_choice("authentic")
        profile.record_choice("authentic")
        profile.record_choice("conforming")
        assert profile.total_choices == 3
        assert profile.authentic_count == 2
        assert profile.conforming_count == 1
        assert profile.authentic_ratio == pytest.approx(2 / 3)

    def test_is_derived_after_10(self):
        profile = PlayerSoulProfile()
        for _ in range(10):
            profile.record_choice("authentic")
        assert profile.is_derived

    def test_serialization_roundtrip(self):
        profile = PlayerSoulProfile(
            soul_name="测试灵魂",
            behavioral_tendencies={"面对危险": "勇敢"},
        )
        profile.record_choice("authentic")
        data = profile.to_dict()
        restored = PlayerSoulProfile.from_dict(data)
        assert restored.soul_name == "测试灵魂"
        assert restored.behavioral_tendencies["面对危险"] == "勇敢"
        assert restored.total_choices == 1
        assert restored.authentic_count == 1

    def test_default_from_dict_empty(self):
        restored = PlayerSoulProfile.from_dict({})
        assert restored.soul_name == "异界旅人"
        assert restored.total_choices == 0


class TestSoulPossessionState:
    def test_default_creation(self):
        state = SoulPossessionState()
        assert state.dominant_soul == "player"
        assert state.blend_ratio == 0.8
        assert state.is_player_dominant()

    def test_canon_immutable(self):
        state = SoulPossessionState()
        state.canon_soul = {"name": "弗雷"}
        assert state.canon_soul["name"] == "弗雷"

    def test_serialization_roundtrip(self):
        state = SoulPossessionState(
            canon_soul={"name": "弗雷"},
            blend_ratio=0.5,
            dominant_soul="blended",
        )
        data = state.to_dict()
        restored = SoulPossessionState.from_dict(data)
        assert restored.canon_soul["name"] == "弗雷"
        assert restored.blend_ratio == 0.5
        assert restored.dominant_soul == "blended"


class TestNPCCognitiveDissonance:
    def test_default_creation(self):
        state = NPCCognitiveDissonance()
        assert state.dissonance_score == 0.0
        assert state.phase == "normal"
        assert state.affinity == 0.0
        assert state.credibility == 100.0

    def test_phase_normal(self):
        state = NPCCognitiveDissonance(dissonance_score=0.1)
        state.update_phase()
        assert state.phase == "normal"

    def test_phase_subtle(self):
        state = NPCCognitiveDissonance(dissonance_score=0.3)
        state.update_phase()
        assert state.phase == "subtle"

    def test_phase_questioning(self):
        state = NPCCognitiveDissonance(dissonance_score=0.6)
        state.update_phase()
        assert state.phase == "questioning"

    def test_phase_confrontational(self):
        state = NPCCognitiveDissonance(dissonance_score=0.8)
        state.update_phase()
        assert state.phase == "confrontational"

    def test_phase_adapted(self):
        state = NPCCognitiveDissonance(
            dissonance_score=0.3,
            adaptation_progress=0.95,
        )
        state.update_phase()
        assert state.phase == "adapted"

    def test_scratchpad_entries(self):
        state = NPCCognitiveDissonance()
        entry = ObservationEntry(
            beat_id="beat_001",
            action_type="authentic",
            observed_behavior="弗雷没有砸酒杯",
            npc_reaction="愣住",
        )
        state.scratchpad.append(entry)
        assert len(state.scratchpad) == 1
        assert state.scratchpad[0].beat_id == "beat_001"

    def test_serialization_roundtrip(self):
        state = NPCCognitiveDissonance(
            char_id="char_003",
            dissonance_score=0.65,
            phase="questioning",
            scratchpad=[
                ObservationEntry(
                    beat_id="b1",
                    action_type="authentic",
                    observed_behavior="行为异常",
                    npc_reaction="困惑",
                )
            ],
        )
        data = state.to_dict()
        restored = NPCCognitiveDissonance.from_dict(data)
        assert restored.char_id == "char_003"
        assert restored.dissonance_score == 0.65
        assert len(restored.scratchpad) == 1
        assert restored.scratchpad[0].beat_id == "b1"


class TestObservationEntry:
    def test_default_creation(self):
        entry = ObservationEntry()
        assert not entry.is_important

    def test_serialization_roundtrip(self):
        entry = ObservationEntry(
            beat_id="b1",
            action_type="authentic",
            observed_behavior="说'放开她'",
            npc_reaction="困惑",
            is_important=True,
        )
        data = entry.to_dict()
        restored = ObservationEntry.from_dict(data)
        assert restored.beat_id == "b1"
        assert restored.is_important
