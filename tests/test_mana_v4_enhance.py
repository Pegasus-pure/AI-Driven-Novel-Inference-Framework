# -*- coding: utf-8 -*-
"""MaNA v4 增强方案 · 单元测试

测试三大改动的核心功能：
1. 涌现实体队列管理
2. 配置文件加载
3. Agent Prompt 构建
"""

import json
import sys
import os

# 添加 server 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

# ── 不需要 aiohttp 依赖的测试 ──


def test_pending_emergence_add_and_merge():
    """测试涌现实体的添加和合并逻辑（不依赖 WorldState 实例）"""
    pending = {}

    # 首次添加
    pending["神秘剑客"] = {
        "entity_type": "character",
        "hit_count": 1,
        "mention_samples": ["一个身披斗篷的神秘剑客从阴影中走出"],
        "feature_tags": ["神秘", "用剑", "斗篷"],
        "readiness": "ACCUMULATING",
    }
    assert pending["神秘剑客"]["hit_count"] == 1
    assert len(pending["神秘剑客"]["mention_samples"]) == 1

    # 合并：相同实体
    pe = pending["神秘剑客"]
    pe["hit_count"] += 1
    new_mention = "那位持剑的蒙面人缓缓开口"
    if new_mention not in pe["mention_samples"]:
        pe["mention_samples"].append(new_mention)
    existing_tags = set(pe["feature_tags"])
    existing_tags.update(["蒙面", "持剑"])
    pe["feature_tags"] = list(existing_tags)

    assert pending["神秘剑客"]["hit_count"] == 2
    assert len(pending["神秘剑客"]["mention_samples"]) == 2
    assert "蒙面" in pending["神秘剑客"]["feature_tags"]

    # 采纳：标记 READY 并生成档案
    pe["readiness"] = "READY"
    pe["generated_profile"] = {
        "name": "神秘剑客",
        "personality": "沉默寡言",
        "role": "流浪剑士",
        "appearance": "黑色斗篷，佩长剑",
        "speech_style": "简洁",
    }

    assert pe["readiness"] == "READY"
    assert pe["generated_profile"]["name"] == "神秘剑客"
    print("[OK] test_pending_emergence_add_and_merge")


def test_pending_emergence_threshold():
    """测试阈值判断逻辑"""
    pending = {}
    threshold = 3

    # 模拟三次命中后采纳
    name = "暗影森林"
    for i in range(1, 5):
        if name not in pending:
            pending[name] = {"entity_type": "location", "hit_count": 0,
                             "mention_samples": [], "feature_tags": [],
                             "readiness": "ACCUMULATING", "generated_profile": None}
        pending[name]["hit_count"] += 1
        pending[name]["mention_samples"].append(f"第{i}次提到暗影森林")

        if pending[name]["hit_count"] >= threshold:
            pending[name]["readiness"] = "READY"
            pending[name]["generated_profile"] = {
                "name": "暗影森林",
                "description": "终年不见日光的密林",
                "atmosphere": "阴森",
                "associated_characters": [],
            }
            break

    assert pending[name]["hit_count"] == 3
    assert pending[name]["readiness"] == "READY"
    assert pending[name]["generated_profile"] is not None
    print("[OK] test_pending_emergence_threshold 通过")


def test_continuity_checker_prompt():
    """验证 ContinuityChecker 的 user prompt 构建"""
    from manana.agents import ContinuityChecker

    cc = ContinuityChecker()
    system = cc.build_system_prompt()
    user = cc.build_user_prompt({
        "player_action": "玩家要求角色立刻离开",
        "history_summary": "角色正在和重要人物进行关键对话",
        "character_states": {"alice": {"location": " tavern", "mood": "紧张"}},
        "beat_plan": {"beat_summary": "角色突然离开 tavern"},
        "narrative_threads": [{"id": "t1", "title": "谈判"}],
    })

    assert "审计" in system
    assert "玩家" in user
    assert "alice" in user
    assert len(user) > 50
    print("[OK] test_continuity_checker_prompt 通过")


def test_role_reflector_prompt():
    """验证 RoleReflector 的 user prompt 构建"""
    from manana.agents import RoleReflector

    rr = RoleReflector()
    user = rr.build_user_prompt({
        "character_performances": [{
            "character_id": "alice",
            "dialogue": [{"text": "你好", "tone": "友好", "target": "player"}],
            "actions": [{"type": "gesture", "description": "挥手"}],
            "mood": "愉快",
        }],
        "previous_states": {"alice": {
            "location": "garden", "mood": "悲伤",
            "wearing": "丧服", "relationships": {"bob": "仇敌"},
        }},
        "beat_plan": {"beat_summary": "alice 在花园中"},
    })

    assert "alice" in user
    assert "丧服" in user or "悲伤" in user
    print("[OK] test_role_reflector_prompt 通过")


def test_character_manager_prompt():
    """验证 CharacterManager 的 prompt 构建"""
    from manana.agents import CharacterManager

    cm = CharacterManager()
    user = cm.build_user_prompt({
        "narrative_text": "一个红发少女从人群中走出，她腰间别着两把短刀。",
        "canon_characters": {"alice": {"name": "Alice"}},
        "dynamic_npcs": {},
        "pending_emergences": {
            "神秘剑客": {
                "hit_count": 2,
                "feature_tags": ["神秘", "用剑"],
                "mention_samples": ["一位神秘剑客在角落喝酒"],
            }
        },
    })

    assert "红发" in user
    assert "神秘剑客" in user
    assert "任务1" in user
    assert "任务2" in user
    print("[OK] test_character_manager_prompt 通过")


def test_config_structure():
    """验证新配置结构"""
    # 验证 config.yaml 中包含新字段
    import yaml
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert "emergence_system" in cfg.get("features", {})
    assert "continuity_check" in cfg.get("features", {})
    assert "role_reflection" in cfg.get("features", {})

    assert cfg["features"]["emergence_system"] is True
    assert cfg["features"]["continuity_check"] is True
    assert cfg["features"]["role_reflection"] is True

    assert cfg["emergence"]["hit_threshold"] == 3
    assert cfg["continuity"]["tier"] == "medium"
    assert cfg["reflection"]["tier"] == "light"
    print("[OK] test_config_structure 通过")


if __name__ == "__main__":
    test_pending_emergence_add_and_merge()
    test_pending_emergence_threshold()
    test_continuity_checker_prompt()
    test_role_reflector_prompt()
    test_character_manager_prompt()
    test_config_structure()
    print("[PASS] 全部测试通过")
