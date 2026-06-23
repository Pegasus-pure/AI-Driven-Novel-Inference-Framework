# -*- coding: utf-8 -*-
"""Pipeline — L0 ContextBuilder

Builds a SceneContext dict from WorldState data.
Pure Python logic; no LLM calls.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from .schema import MananaSchema


class ContextBuilder:
    """Layer 0 — Builds a SceneContext dict from WorldState data.

    Pure Python logic; no LLM calls. All data is passed through world_state dict.
    All methods are static — no instance state.
    """

    @staticmethod
    def build(
        player_action: str,
        world_state: dict,
        beat_id: str = "",
        scene_id: str = "",
        location_info: Optional[dict] = None,
    ) -> dict:
        """Assemble a full SceneContext dictionary from world state data.

        Args:
            player_action: Player's current input/action.
            world_state: Dict containing characters_state, canon, threads, history, etc.
            beat_id: Current beat identifier.
            scene_id: Current scene identifier.
            location_info: Optional pre-built location dict.

        Returns:
            Complete SceneContext dictionary conforming to MananaSchema.
        """
        player = ContextBuilder._build_player_context(player_action, world_state)
        chars = ContextBuilder._build_character_context(world_state)
        threads = ContextBuilder._build_thread_context(world_state)
        location = ContextBuilder._build_location_context(world_state, location_info or {})
        history = ContextBuilder._build_history_context(world_state)
        memory = ContextBuilder._build_memory_context(world_state)
        divergence = float(world_state.get("world_divergence", 0.0))
        world_rules = ContextBuilder._build_world_rules_context(world_state)
        game_time = str(world_state.get("game_time", ""))

        return MananaSchema.build_scene_context(
            chars, threads, location, player, history, memory,
            divergence, world_rules, beat_id, scene_id, game_time,
        )

    @staticmethod
    def _build_player_context(action: str, ws: dict) -> dict:
        profile = dict(ws.get("player_profile", {}) or {})
        reputation_raw = dict(ws.get("player_reputation", {}) or {})
        reputation_text: dict[str, str] = {}
        for char_id, val in reputation_raw.items():
            reputation_text[char_id] = ContextBuilder._reputation_to_text(float(val))

        # ★ 灵魂附生模式：player_profile 已与主角合并，附上灵魂状态
        soul = ws.get("soul_possession", {}) or {}
        if soul:
            profile["soul_state"] = "灵魂附生中"
            profile["dominant"] = soul.get("dominant_soul", "player")

        return {
            "action": action,
            "profile": deepcopy(profile),
            "reputation": reputation_text,
        }

    @staticmethod
    def _build_character_context(ws: dict) -> list[dict]:
        characters_state: dict = dict(ws.get("characters_state", {}) or {})
        canon: dict = ws.get("canon", {}) or {}
        canon_chars: list = canon.get("characters", []) or []
        player_location = str(ws.get("player_location", ""))
        dynamic_npcs: dict = ws.get("dynamic_npcs", {}) or {}
        has_location = bool(player_location)

        # ★ 灵魂附生模式：过滤掉主角（主角 = 玩家，已在 player context 中）
        soul = ws.get("soul_possession", {}) or {}
        protagonist_id = ""
        if soul:
            pp = ws.get("player_profile", {}) or {}
            protagonist_id = str(pp.get("character_id", ""))
        if protagonist_id:
            characters_state.pop(protagonist_id, None)

        canon_lookup: dict[str, dict] = {}
        for c in canon_chars:
            c = c if isinstance(c, dict) else {}
            cid = str(c.get("id", ""))
            if cid:
                canon_lookup[cid] = c

        result: list[dict] = []
        for char_id, cs in characters_state.items():
            cs = cs if isinstance(cs, dict) else {}
            if cs.get("status") == "dead":
                continue
            if not has_location:
                canon_data = canon_lookup.get(char_id, {}) or {}
                role = str(canon_data.get("role", ""))
                if "主" not in role and "重要" not in role:
                    continue
                if len(result) >= 8:
                    break
            elif cs.get("location", "") != player_location:
                continue
            entry = ContextBuilder._build_single_character(char_id, cs, canon_lookup, ws, player_location)
            if entry:
                result.append(entry)

        # ★ 跨地点角色：随机选 2-3 个不同地点的角色，标记为 cross_location
        import random as _random
        other_chars = []
        for char_id, cs in characters_state.items():
            cs = cs if isinstance(cs, dict) else {}
            if cs.get("status") == "dead":
                continue
            if has_location and cs.get("location", "") not in ("", player_location):
                entry = ContextBuilder._build_single_character(char_id, cs, canon_lookup, ws, player_location)
                if entry:
                    entry["cross_location"] = True
                    other_chars.append(entry)
        if other_chars and has_location:
            pick_n = min(3, len(other_chars))
            result.extend(_random.sample(other_chars, pick_n))

        # 保底：玩家位置未知且没有找到任何主要角色 → 取前 8 个
        if not has_location and not result:
            for char_id, cs in list(characters_state.items())[:8]:
                cs = cs if isinstance(cs, dict) else {}
                if cs.get("status") == "dead":
                    continue
                entry = ContextBuilder._build_single_character(char_id, cs, canon_lookup, ws, player_location)
                if entry:
                    result.append(entry)

        # Dynamic NPCs not yet in characters_state
        for npc_id, npc in dynamic_npcs.items():
            if npc_id in characters_state:
                continue
            npc = npc if isinstance(npc, dict) else {}
            npc_loc = str(npc.get("location", ""))
            if (has_location and npc_loc == player_location) or not has_location:
                if len(result) >= 10:
                    break
                result.append({
                    "char_id": npc_id,
                    "name": npc.get("name", "??"),
                    "personality": "",
                    "role": str(npc.get("role", "")),
                    "current_state": {"location": npc_loc, "mood": "中性", "goal": ""},
                    "known_facts": [],
                    "relation_to_player": "中立",
                    "is_dynamic": True,
                    "anti_rules": [],
                })

        return result

    @staticmethod
    def _format_personality(personality_data) -> str:
        """将 personality dict/str 格式化为 LLM 友好的文本。"""
        if isinstance(personality_data, str):
            return personality_data
        if not isinstance(personality_data, dict):
            return ""
        parts = []
        if "type" in personality_data:
            parts.append(str(personality_data["type"]))
        if "traits" in personality_data:
            traits = personality_data["traits"]
            if isinstance(traits, list):
                parts.append("、".join(str(t) for t in traits[:5]))
        if "description" in personality_data:
            parts.append(str(personality_data["description"]))
        if "anti_rules" in personality_data:
            ar = personality_data["anti_rules"]
            if isinstance(ar, list) and ar:
                parts.append(f"不会{'、'.join(str(r) for r in ar[:3])}")
        return "；".join(parts) if parts else ""

    @staticmethod
    def _build_single_character(
        char_id: str, cs: dict, canon_lookup: dict[str, dict], ws: dict, player_location: str,
    ) -> dict:
        canon_data = canon_lookup.get(char_id, {}) or {}
        name = str(canon_data.get("name", char_id))
        personality = ContextBuilder._format_personality(canon_data.get("personality", ""))
        role = str(canon_data.get("role", ""))

        # Reputation text
        rep_text = ""
        rep_raw = ws.get("player_reputation", {}) or {}
        if char_id in rep_raw:
            rep_text = ContextBuilder._reputation_to_text(float(rep_raw[char_id]))

        # Known facts
        known_facts: list = []
        kg = ws.get("knowledge_graph", {}) or {}
        if char_id in kg:
            known_facts = list(kg.get(char_id, []) or [])

        current_state = {
            "location": str(cs.get("location", "")),
            "mood": str(cs.get("mood", "中性")),
            "goal": str(cs.get("goal", "")),
        }

        # Anti-rules
        personality_dict = canon_data.get("personality", {})
        if isinstance(personality_dict, dict):
            anti_rules: list = personality_dict.get("anti_rules", []) or []
        else:
            anti_rules = []

        result = {
            "char_id": char_id,
            "name": name,
            "personality": personality,
            "role": role,
            "current_state": current_state,
            "known_facts": known_facts,
            "relation_to_player": rep_text,
            "anti_rules": anti_rules,
            "is_dynamic": False,
        }

        # ★ 认知冲突静默注入（第三档）
        dissonance_map = ws.get("cognitive_dissonance", {}) or {}
        if char_id in dissonance_map:
            d = dissonance_map[char_id]
            if isinstance(d, dict):
                result["cognitive_state"] = {
                    "dissonance_score": float(d.get("dissonance_score", 0.0)),
                    "phase": str(d.get("phase", "normal")),
                    "theory_of_change": str(d.get("theory_of_change", "")),
                    "affinity": float(d.get("affinity", 0.0)),
                    "credibility": float(d.get("credibility", 100.0)),
                }

        return result

    @staticmethod
    def _build_thread_context(ws: dict) -> list[dict]:
        """从 world_state 构建线索上下文（供 LLM 参考）。

        数据源统一为 narrative_threads.active（与前端 state_sync 同一来源）。
        """
        threads_dict: dict = ws.get("narrative_threads", {}) or {}
        active_threads: list = threads_dict.get("active", []) or []

        result: list[dict] = []
        for t in active_threads:
            t = t if isinstance(t, dict) else {}
            result.append({
                "id": str(t.get("id", "")),
                "title": str(t.get("title", "")),
                "type": str(t.get("type", "")),
                "intensity": float(t.get("intensity", 0.0)),
                "complexity": float(t.get("complexity", 0.3)),
                "question": str(t.get("question", "")),
                "involved_characters": list(t.get("involved_characters", []) or []),
                "tension": float(t.get("tension", 0.3)),
                "player_attention": float(t.get("player_attention", 0.5)),
                "priority": float(t.get("priority", 0.5)),
            })
        return result

    @staticmethod
    def _build_history_context(ws: dict) -> list[dict]:
        raw_history: list = ws.get("narrative_history", []) or []
        recent_count = min(len(raw_history), 5)
        start = len(raw_history) - recent_count
        result: list[dict] = []
        for evt in raw_history[start:]:
            evt = evt if isinstance(evt, dict) else {}
            result.append({
                "time": str(evt.get("time", "")),
                "summary": str(evt.get("summary", "")),
                "event_id": str(evt.get("event_id", "")),
            })
        return result

    @staticmethod
    def _build_memory_context(ws: dict) -> dict:
        return {
            "scene_memory": list(ws.get("scene_memory", []) or []),
            "long_term_memory": list(ws.get("long_term_memory", []) or []),
        }

    @staticmethod
    def _build_location_context(ws: dict, location_info: dict) -> dict:
        if location_info:
            return dict(location_info)

        player_location = str(ws.get("player_location", ""))
        canon: dict = ws.get("canon", {}) or {}
        locations: list = canon.get("locations", []) or []

        for loc in locations:
            loc = loc if isinstance(loc, dict) else {}
            if str(loc.get("id", "")) == player_location or str(loc.get("name", "")) == player_location:
                return {
                    "id": str(loc.get("id", "")),
                    "name": str(loc.get("name", "")),
                    "description": str(loc.get("description", "")),
                    "atmosphere": str(loc.get("atmosphere", "")),
                }

        return {"id": player_location, "name": player_location, "description": "", "atmosphere": ""}

    @staticmethod
    def _build_world_rules_context(ws: dict) -> str:
        rules: list = ws.get("custom_world_rules", []) or []
        enabled: list[str] = []
        for r in rules:
            r = r if isinstance(r, dict) else {}
            if r.get("enabled", False):
                content = str(r.get("content", ""))
                if content:
                    enabled.append(content)
        return "\n".join(enabled)

    @staticmethod
    def _reputation_to_text(value: float) -> str:
        if value >= 0.7:
            return "友善"
        elif value >= 0.3:
            return "有好感"
        elif value >= -0.3:
            return "中立"
        elif value >= -0.7:
            return "冷淡"
        else:
            return "敌视"
