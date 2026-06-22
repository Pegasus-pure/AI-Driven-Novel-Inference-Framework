# -*- coding: utf-8 -*-
"""Pipeline — State application helpers

Contains InteractionPair helper and state application logic
extracted from the main pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..world_state import WorldState

_log = logging.getLogger("Rain.Pipeline.State")


class InteractionPair:
    """Lightweight representation of a character interaction pair."""

    def __init__(self, pair_id: str, char_ids: list[str], pair_type: str) -> None:
        self.pair_id: str = pair_id
        self.char_ids: list[str] = list(char_ids)
        self.pair_type: str = pair_type

    def get_counterpart(self, char_id: str) -> str:
        """Get the other character in this pair."""
        for cid in self.char_ids:
            if cid != char_id:
                return cid
        return ""

    @staticmethod
    def from_dict(d: dict) -> "InteractionPair":
        return InteractionPair(
            pair_id=str(d.get("pair_id", "")),
            char_ids=list(d.get("char_ids", []) or []),
            pair_type=str(d.get("type", "dialogue")),
        )


def apply_state_patch(world_state: "WorldState", state_patch: dict) -> None:
    """通过 WorldState 方法应用 Extractor 返回的状态补丁。"""
    for rc in (state_patch.get("reputation_changes", []) or []):
        rc = rc if isinstance(rc, dict) else {}
        char_id = str(rc.get("char_id", ""))
        delta = float(rc.get("delta", 0.0))
        if char_id:
            world_state.apply_reputation_change(char_id, delta)

    for mc in (state_patch.get("mood_changes", []) or []):
        mc = mc if isinstance(mc, dict) else {}
        char_id = str(mc.get("char_id", ""))
        if char_id:
            world_state.apply_mood_change(
                char_id,
                str(mc.get("new_mood", "")),
                mc.get("intensity"),
            )

    for lc in (state_patch.get("location_changes", []) or []):
        lc = lc if isinstance(lc, dict) else {}
        char_id = str(lc.get("char_id", ""))
        new_loc = str(lc.get("to", ""))

        # ── 位置跳跃审计：评估新旧位置是否连续 ──
        if char_id and new_loc and hasattr(world_state, "characters_state"):
            prev_loc = str(
                (world_state.characters_state.get(char_id, {}) or {}).get("location", "")
            )
            if prev_loc and prev_loc != new_loc and prev_loc != "未知":
                # 简单检测：如果新旧位置没有共同的父地点前缀，标记为可疑跳跃
                prev_parts = set(p.strip() for p in prev_loc.replace("·", "|").replace("/", "|").split("|"))
                new_parts = set(p.strip() for p in new_loc.replace("·", "|").replace("/", "|").split("|"))
                common = prev_parts & new_parts
                if not common:
                    _log.warning(
                        "位置跳跃审计: %s %s → %s (无公共前缀)",
                        char_id, prev_loc, new_loc,
                    )

        world_state.apply_location_change(
            char_id,
            new_loc,
        )

    for nk in (state_patch.get("new_knowledge", []) or []):
        nk = nk if isinstance(nk, dict) else {}
        content = str(nk.get("content", ""))
        known_by: list = nk.get("known_by", []) or []
        if content and known_by:
            for kb in known_by:
                world_state.add_knowledge(str(kb), content)

    for npc in (state_patch.get("new_dynamic_npcs", []) or []):
        world_state.add_dynamic_npc(npc if isinstance(npc, dict) else {})

    ppu: dict = state_patch.get("player_profile_updates", {}) or {}
    if ppu and isinstance(ppu, dict):
        if ppu.get("new_trait"):
            world_state.add_player_trait(ppu["new_trait"])
        if ppu.get("updated_motivation"):
            world_state.update_player_motivation(ppu["updated_motivation"])
        if ppu.get("tendency_shift"):
            world_state.update_player_tendency(ppu["tendency_shift"])

    divergence_delta = state_patch.get("divergence_delta", None)
    if divergence_delta is not None:
        world_state.update_divergence(float(divergence_delta))

    narrative_tension = state_patch.get("narrative_tension", None)
    if narrative_tension is not None:
        world_state.narrative_tension = max(0.0, min(1.0, float(narrative_tension)))

    new_conflicts: list = state_patch.get("new_seed_conflicts", []) or []
    if new_conflicts and hasattr(world_state, "conflict_pool") and world_state.conflict_pool:
        world_state.conflict_pool.add_seeds(new_conflicts)
