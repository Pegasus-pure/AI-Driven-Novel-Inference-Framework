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
        return {
            "action": action,
            "profile": deepcopy(profile),
            "reputation": reputation_text,
        }

    @staticmethod
    def _build_character_context(ws: dict) -> list[dict]:
        characters_state: dict = ws.get("characters_state", {}) or {}
        canon: dict = ws.get("canon", {}) or {}
        canon_chars: list = canon.get("characters", []) or []
        player_location = str(ws.get("player_location", ""))
        dynamic_npcs: dict = ws.get("dynamic_npcs", {}) or {}

        canon_lookup: dict[str, dict] = {}
        for c in canon_chars:
            c = c if isinstance(c, dict) else {}
            cid = str(c.get("id", ""))
            if cid:
                canon_lookup[cid] = c

        result: list[dict] = []
        for char_id, cs in characters_state.items():
            cs = cs if isinstance(cs, dict) else {}
            entry = ContextBuilder._build_single_character(char_id, cs, canon_lookup, ws, player_location)
            if entry:
                result.append(entry)

        # Dynamic NPCs not yet in characters_state
        for npc_id, npc in dynamic_npcs.items():
            if npc_id in characters_state:
                continue
            npc = npc if isinstance(npc, dict) else {}
            npc_loc = str(npc.get("location", ""))
            if npc_loc == player_location or not player_location:
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
    def _build_single_character(
        char_id: str, cs: dict, canon_lookup: dict[str, dict], ws: dict, player_location: str,
    ) -> dict:
        canon_data = canon_lookup.get(char_id, {}) or {}
        name = str(canon_data.get("name", char_id))
        personality = str(canon_data.get("personality", ""))
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

        return {
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

    @staticmethod
    def _build_thread_context(ws: dict) -> list[dict]:
        active_threads: list = ws.get("active_threads", []) or []
        if not active_threads:
            threads_dict: dict = ws.get("narrative_threads", {}) or {}
            active_threads = threads_dict.get("active", []) or []

        result: list[dict] = []
        for t in active_threads:
            t = t if isinstance(t, dict) else {}
            result.append({
                "id": str(t.get("id", "")),
                "title": str(t.get("title", "")),
                "type": str(t.get("type", "")),
                "progress": float(t.get("progress", 0.0)),
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
