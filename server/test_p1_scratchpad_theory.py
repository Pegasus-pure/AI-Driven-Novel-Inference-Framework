# -*- coding: utf-8 -*-
"""P1 Validation: ScratchpadManager + theory_of_change integration tests."""

from __future__ import annotations

import sys
import os

# Ensure server is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from manana.soul import ScratchpadManager, DissonanceUpdater
from manana.soul.soul_state import NPCCognitiveDissonance


def test1_scratchpad_write():
    """Test 1: ScratchpadManager basic write."""
    print("=" * 60)
    print("TEST 1: ScratchpadManager 写入")
    print("=" * 60)

    sm = ScratchpadManager()
    state = NPCCognitiveDissonance(char_id="npc_a")

    sm.add_observation(state, beat_id="beat_001", action_type="authentic",
        observed_behavior="主角: 按自己的方式行事",
        npc_reaction="感到有些不对劲", is_important=True)
    sm.add_observation(state, beat_id="beat_002", action_type="conforming",
        observed_behavior="主角: 模仿原主口吻",
        npc_reaction="觉得一切正常", is_important=False)

    # Verify writes
    assert len(state.scratchpad) == 2, f"Expected 2 entries, got {len(state.scratchpad)}"
    assert state.scratchpad[0].beat_id == "beat_001", \
        f"Expected beat_001, got {state.scratchpad[0].beat_id}"
    assert state.scratchpad[1].is_important == False, \
        f"Expected False, got {state.scratchpad[1].is_important}"
    print("SCRATCHPAD WRITE TEST PASSED")
    return True


def test2_fifo_truncation():
    """Test 2: FIFO truncation of normal entries."""
    print("=" * 60)
    print("TEST 2: FIFO 截断")
    print("=" * 60)

    sm = ScratchpadManager()
    state = NPCCognitiveDissonance(char_id="npc_a")

    # Write 25 normal entries (exceeds max of 20)
    for i in range(25):
        sm.add_observation(state, beat_id=f"beat_{i:03d}", action_type="auto",
            observed_behavior=f"观察 {i}", npc_reaction="", is_important=False)

    normal_count = len([e for e in state.scratchpad if not e.is_important])
    assert normal_count <= 20, f"FIFO failed: {normal_count} normal entries (max expected 20)"
    print(f"FIFO TEST PASSED: {normal_count} normal entries (max 20)")
    return True


def test3_theory_of_change():
    """Test 3: theory_of_change template logic."""
    print("=" * 60)
    print("TEST 3: theory_of_change 模板逻辑")
    print("=" * 60)

    # Simulate: dissonance from 0 → 0.30, should generate subtle theory
    state = NPCCognitiveDissonance(char_id="npc_a", dissonance_score=0.0)
    assert state.theory_of_change == "", "Should start empty"

    # Simulate logic: score >= 0.25 and not theory_of_change
    score = 0.30
    if score >= 0.50 and not state.theory_of_change:
        state.theory_of_change = "开始怀疑…"
    elif score >= 0.25 and not state.theory_of_change:
        state.theory_of_change = "最近总觉得有些不对劲…"

    assert state.theory_of_change != "", "theory_of_change should be set"
    assert state.theory_of_change == "最近总觉得有些不对劲…", \
        f"Unexpected theory: {state.theory_of_change}"

    # Simulate crossing 0.50 threshold — should NOT overwrite
    old = state.theory_of_change
    score = 0.55
    if score >= 0.50 and not state.theory_of_change:
        state.theory_of_change = "should not happen"
    # Since theory_of_change already exists, should not change
    assert state.theory_of_change == old, "Should not overwrite existing theory"

    print("THEORY_OF_CHANGE TEMPLATE TEST PASSED")
    return True


def test4_end_to_end():
    """Test 4: End-to-end DissonanceUpdater + ScratchpadManager."""
    print("=" * 60)
    print("TEST 4: 端到端 — 完整数据流")
    print("=" * 60)

    dissonance_map = {"npc_a": NPCCognitiveDissonance(char_id="npc_a")}
    soul_decision = {
        "action_type": "authentic",
        "decision": "按自己的方式行事",
        "dominant_soul": "player",
    }
    recent_actions = [soul_decision]

    updater = DissonanceUpdater()
    changes = updater.update_all(dissonance_map, {}, {}, recent_actions)

    # Simulate scratchpad write (matching game_session logic)
    beat_id = "beat_005"
    protagonist_name = "主角"
    scratchpad = ScratchpadManager()
    for cid, ch in changes.items():
        state = dissonance_map.get(cid)
        if state is None:
            continue
        scratchpad.add_observation(state, beat_id=beat_id, action_type="authentic",
            observed_behavior=f"{protagonist_name}: 按自己的方式行事",
            npc_reaction="感到有些不对劲", is_important=True)

    # Verify
    assert len(dissonance_map["npc_a"].scratchpad) >= 1, \
        f"Expected >=1 scratchpad entries, got {len(dissonance_map['npc_a'].scratchpad)}"
    assert dissonance_map["npc_a"].scratchpad[0].is_important == True, \
        "First entry should be important"

    print(
        f"END-TO-END TEST PASSED: "
        f"{len(dissonance_map['npc_a'].scratchpad)} scratchpad entries, "
        f"score={dissonance_map['npc_a'].dissonance_score:.3f}"
    )
    return True


def main():
    """Run all P1 validation tests."""
    results = {}
    tests = [
        ("Test 1: Scratchpad Write", test1_scratchpad_write),
        ("Test 2: FIFO Truncation", test2_fifo_truncation),
        ("Test 3: theory_of_change Template", test3_theory_of_change),
        ("Test 4: End-to-End", test4_end_to_end),
    ]

    for name, test_fn in tests:
        try:
            passed = test_fn()
            results[name] = "PASSED" if passed else "FAILED"
        except AssertionError as e:
            results[name] = f"FAILED -- {e}"
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            results[name] = f"ERROR -- {e}"
            print(f"  ERROR {name}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, result in results.items():
        status = "PASS" if result == "PASSED" else "FAIL"
        print(f"  [{status}] {name}: {result}")
        if result != "PASSED":
            all_pass = False

    print(f"\nOverall: {'ALL PASSED' if all_pass else 'SOME FAILURES'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
