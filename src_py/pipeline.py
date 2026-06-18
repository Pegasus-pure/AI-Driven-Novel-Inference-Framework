"""MaNA v4 Pipeline — Main Orchestrator.

The central orchestrator that executes the complete 5-layer narrative pipeline:

  L0: ContextBuilder — scene context assembly
  L1: SceneDirector — beat planning (v4: Best-of-3, Multi-View)
  L2R1: MotivationEngine — per-character motivation (N-parallel)
  L2R2: DialogueWeaver + ActionDirector — dialogue & action (N×2 parallel)
  L3: SceneComposer — narrative prose weaving (v4: refinement loop)
  L3b∥L4a: Auditor + Extractor — consistency check + state extraction (parallel)
  L4b: ThreadManager — thread lifecycle management
  L5: ReflectionOracle — oracle reflection (conditional, every 5 beats)
  v4: MicroOracle — per-beat quality feedback

Three-tier model assignment:
  strong: Director, Composer, Oracle
  medium: Motivation, Dialogue, Auditor, Thread, Synthesizer
  light: Action, Extractor, Scorer, MicroOracle
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from copy import deepcopy
from typing import Any, Optional

from .agents import (
    ActionDirector,
    ConsistencyAuditor,
    DialogueWeaver,
    MicroOracleAgent,
    MotivationEngine,
    PlanScorerAgent,
    PlanSynthesizerAgent,
    ReflectionOracle,
    SceneComposer,
    SceneDirector,
    StateExtractor,
    ThreadManager,
)
from .config import MananaConfig
from .providers import BaseProvider, ProviderFactory
from .schema import MananaSchema
from .utils import (
    get_logger,
    log_error,
    log_layer,
    log_warning,
    set_current_beat,
)

_log = logging.getLogger("MaNA.Pipeline")

# ------------------------------------------------------------------
# ContextBuilder — L0 (pure Python, no LLM)
# ------------------------------------------------------------------


class ContextBuilder:
    """Layer 0 — Builds a SceneContext dict from WorldState data.

    Pure Python logic; no LLM calls. All data is passed through world_state dict.
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


# ============================================================
# InteractionPair helper
# ============================================================


class InteractionPair:
    """Lightweight representation of a character interaction pair."""

    def __init__(self, pair_id: str, char_ids: list[str], pair_type: str) -> None:
        self.pair_id: str = pair_id
        self.char_ids: list[str] = char_ids
        self.pair_type: str = pair_type

    def get_counterpart(self, char_id: str) -> str:
        """Return the other character in the pair."""
        for cid in self.char_ids:
            if cid != char_id:
                return cid
        return ""

    @staticmethod
    def from_dict(d: dict) -> "InteractionPair":
        return InteractionPair(
            pair_id=str(d.get("pair_id", "")),
            char_ids=list(d.get("char_ids", []) or []),
            pair_type=str(d.get("pair_type", "")),
        )


# ============================================================
# MananaPipeline — Main Orchestrator
# ============================================================


class MananaPipeline:
    """MaNA v4 — 5-layer multi-agent narrative pipeline.

    Usage:
        pipeline = MananaPipeline("manana_config.cfg")
        await pipeline.initialize()
        result = await pipeline.run_beat("玩家走向图书馆")
    """

    def __init__(self, config_path: str = "manana_config.cfg") -> None:
        self._config = MananaConfig(config_path)
        self._provider_strong: Optional[BaseProvider] = None
        self._provider_medium: Optional[BaseProvider] = None
        self._provider_light: Optional[BaseProvider] = None
        self._beat_count: int = 0
        self._oracle_context: dict[str, Any] = {}
        self._last_narrative: str = ""
        self._pending_reconnect: bool = False

        # v4 state
        self._micro_oracle_buffer: list[dict] = []
        self._next_beat_context: dict[str, Any] = {}

        # Prompt cache
        self._prompt_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load config and initialize all three provider tiers."""
        self._config.load_config()
        await self._init_providers()

    async def _init_providers(self) -> None:
        """Create and configure strong/medium/light providers."""
        for tier in ("strong", "medium", "light"):
            tier_config = self._config.get_tier_config(tier)
            prov_type = tier_config.get("type", "ollama")
            provider = ProviderFactory.create(prov_type, tier_config)
            if provider:
                _log.info("Pipeline tier '%s': %s provider (model: %s)",
                          tier, prov_type, tier_config.get("model", "?"))
                if tier == "strong":
                    self._provider_strong = provider
                elif tier == "medium":
                    self._provider_medium = provider
                else:
                    self._provider_light = provider
            else:
                _log.error("Pipeline init failed: could not create '%s' provider for tier '%s'",
                           prov_type, tier)

    async def cleanup(self) -> None:
        """Release all provider resources."""
        for prov in (self._provider_strong, self._provider_medium, self._provider_light):
            if prov:
                await prov.cleanup()

    # ------------------------------------------------------------------
    # Provider routing
    # ------------------------------------------------------------------

    def _get_provider_for_tier(self, tier: str) -> Optional[BaseProvider]:
        """Route to the correct provider by tier name."""
        if tier == "strong":
            return self._provider_strong
        elif tier == "medium":
            return self._provider_medium
        elif tier == "light":
            return self._provider_light
        return self._provider_medium  # fallback

    def _create_independent_provider(self, tier: str) -> Optional[BaseProvider]:
        """Create a fresh provider instance for parallel execution.

        Callers should call .cleanup() after collecting results.
        """
        tier_config = self._config.get_tier_config(tier)
        prov_type = tier_config.get("type", "ollama")
        return ProviderFactory.create(prov_type, tier_config)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run_beat(self, player_action: str, world_state: dict) -> dict:
        """Execute a complete narrative beat.

        Args:
            player_action: Player's current input/action text.
            world_state: Dict containing all world state data
                         (characters_state, canon, active_threads, narrative_history, etc.)

        Returns:
            {
                "narrative_text": str,
                "action_hints": list[str],
                "ending_hook": str,
                "music_mood": str,
                "state_patch": dict,
                "audit": dict,
            }
        """
        self._beat_count += 1
        beat_id = f"beat_{self._beat_count:03d}"
        set_current_beat(beat_id)

        _log.info("=== Beat %s START ===", beat_id)

        # ── L0: Context ──
        log_layer("L0", "ContextBuilder 启动")
        ctx = ContextBuilder.build(player_action, world_state, beat_id=beat_id)
        log_layer("L0", f"ContextBuilder 完成 ({len(ctx.get('characters', []))} 角色, "
                  f"{len(ctx.get('active_threads', []))} 线索)")

        # ── v4: Context augmentation (semantic_selection + vector_memory + micro_feedback) ──
        if self._config.is_feature_enabled("semantic_selection") or \
           self._config.get_memory_config().get("enable_vector_memory", False):
            ctx = await self._augment_context(ctx)

        # ── L1: Director ──
        plan: dict = {}
        if self._config.is_feature_enabled("multi_view") and self._config.is_feature_enabled("best_of_3"):
            log_layer("L1", "SceneDirector 启动 (multi_view + best_of_3)")
            plan = await self._run_director_multi_view(ctx)
        elif self._config.is_feature_enabled("best_of_3"):
            log_layer("L1", "SceneDirector 启动 (best_of_3)")
            best_plan = await self._run_director_best_of_3(ctx)
            plan = best_plan.get("raw", {}) or {}
            if not plan and best_plan:
                plan = best_plan
        else:
            log_layer("L1", "SceneDirector 启动")
            director = SceneDirector()
            director.configure(self._get_provider_for_tier("strong"))
            director_input = {"system_prompt": self._load_prompt("director"), "scene_context": ctx}
            beat_plan_result = await director.run(director_input)
            if not beat_plan_result.get("ok", False):
                err = str(beat_plan_result.get("error", "Director failed"))
                log_error("SceneDirector", err)
                return {"error": "Director failed: " + err}
            plan = beat_plan_result.get("raw", {}) or {}

        if not plan:
            log_error("SceneDirector", "Director produced empty plan")
            return {"error": "Director failed: empty plan"}

        log_layer("L1", f"SceneDirector 完成 — 模式: {plan.get('narrative_mode', '?')}")

        # ── v4: Complexity scoring + dynamic tier ──
        if self._config.is_feature_enabled("dynamic_tier"):
            complexity = self._compute_complexity(ctx, plan)
            log_layer("L1", f"复杂度评分: {complexity:.2f}")
            self._apply_tier_overrides(complexity)

        # ── L2R1: MotivationEngine (N parallel) ──
        featured_chars: list = plan.get("featured_characters", []) or []
        log_layer("L2R1", f"MotivationEngine 启动 ({len(featured_chars)} 角色)")
        motivation_results = await self._run_motivations_parallel(ctx, plan)
        log_layer("L2R1", f"MotivationEngine 完成 ({len(motivation_results)} 结果)")

        # ── L2R2: DialogueWeaver + ActionDirector (N×2 parallel) ──
        log_layer("L2R2", "DialogueWeaver/ActionDirector 启动")
        character_outputs = await self._run_dialogue_actions_parallel(ctx, plan, motivation_results)
        log_layer("L2R2", f"DialogueWeaver/ActionDirector 完成 ({len(character_outputs)} 角色输出)")

        # ── L3: SceneComposer ──
        narrative_result: dict = {}
        if self._config.is_feature_enabled("refinement"):
            log_layer("L3", "SceneComposer 启动 (精炼循环)")
            narrative_result = await self._run_composer_with_refinement(ctx, character_outputs, plan)
        else:
            log_layer("L3", "SceneComposer 启动")
            composer = SceneComposer()
            composer.configure(self._get_provider_for_tier("strong"))
            composer_input = self._build_composer_input(plan, character_outputs, ctx)
            narrative_result = await composer.run(composer_input)

        if not narrative_result.get("ok", False):
            composer_err = str(narrative_result.get("error", "Composer failed"))
            log_error("SceneComposer", composer_err)
            return {"error": "Composer failed: " + composer_err}

        narrative_text: str = narrative_result.get("content", "") or ""
        composer_raw: dict = narrative_result.get("raw", {}) or {}
        log_layer("L3", f"SceneComposer 完成 ({len(narrative_text)} 字符)")

        # ── L3b ∥ L4a: Auditor + Extractor (parallel) ──
        log_layer("L3b∥L4a", "Auditor / Extractor 启动 (并行)")

        auditor_input = self._build_auditor_input(narrative_text, plan, ctx)
        extractor_input = self._build_extractor_input(narrative_text, character_outputs, world_state)

        auditor = ConsistencyAuditor()
        auditor.configure(self._get_provider_for_tier("medium"))
        extractor = StateExtractor()
        extractor.configure(self._get_provider_for_tier("light"))

        audit_task = auditor.run(auditor_input)
        extractor_task = extractor.run(extractor_input)
        audit_result, state_patch_result = await asyncio.gather(audit_task, extractor_task)

        log_layer("L3b∥L4a", "Auditor / Extractor 完成")

        # Audit FAIL handling
        audit_data: dict = audit_result.get("raw", {}) or {}
        if str(audit_data.get("verdict", "PASS")) not in ("PASS",):
            issues: list = audit_data.get("issues", []) or []
            log_warning("Auditor", f"Beat {beat_id} audit FAIL: {len(issues)} issues")

        # ── L4b: ThreadManager ──
        log_layer("L4b", "ThreadManager 启动")
        thread_updates = await self._run_thread_manager(
            narrative_text, str(plan.get("beat_summary", "")), plan, world_state,
        )
        log_layer("L4b", "ThreadManager 完成")

        # ── Apply state changes ──
        state_patch: dict = state_patch_result.get("raw", {}) or {}
        if state_patch:
            self._apply_state_patch(world_state, state_patch)

        # ── Apply thread changes ──
        self._apply_thread_updates(world_state, thread_updates)

        # ── Narrative history + memory ──
        summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
        if not summary:
            summary = narrative_text[:100]
        self._add_narrative_event(world_state, summary, beat_id)
        mem_entry = str(state_patch.get("scene_memory_entry", narrative_text[:60]))
        if mem_entry:
            self._add_scene_memory(world_state, mem_entry)
        self._advance_game_time(world_state)

        # ── L5: Oracle (conditional) ──
        if self._beat_count % self._config.get_oracle_interval() == 0:
            log_layer("L5", f"ReflectionOracle 触发 (beat {self._beat_count})")
            await self._run_oracle(ctx, world_state)

        # ── v4: Micro-Oracle ──
        if self._config.is_feature_enabled("micro_oracle"):
            mo_summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
            if not mo_summary:
                mo_summary = narrative_text[:100]
            await self._run_micro_oracle(narrative_text, mo_summary, ctx)

        # ── Trace ──
        from .utils import save_traces
        save_traces(beat_id)
        self._last_narrative = narrative_text

        result_data = {
            "narrative_text": narrative_text,
            "action_hints": composer_raw.get("action_hints", []) or [],
            "ending_hook": composer_raw.get("ending_hook", "") or "",
            "music_mood": composer_raw.get("music_mood", "") or "",
            "state_patch": state_patch,
            "audit": audit_result,
        }

        _log.info("=== Beat %s COMPLETE ===", beat_id)

        if self._pending_reconnect:
            await self._do_reconnect()

        return result_data

    # ------------------------------------------------------------------
    # L2R1: Motivation parallel dispatch
    # ------------------------------------------------------------------

    async def _run_motivations_parallel(self, ctx: dict, plan: dict) -> list[dict]:
        char_ids: list = plan.get("featured_characters", []) or []
        if not char_ids:
            return []

        async def run_one(cid: str) -> dict:
            char_data = self._find_character(ctx, cid)
            if not char_data:
                return {"char_id": cid, "motivation": {}}

            agent = MotivationEngine()
            provider = self._create_independent_provider("medium")
            if not provider:
                return {"char_id": cid, "motivation": {}}

            try:
                agent.configure(provider)
                mot_input = {
                    "system_prompt": self._load_prompt("motivation"),
                    "character": char_data,
                    "scene_summary": plan.get("beat_summary", ""),
                    "player_action": (ctx.get("player", {}) or {}).get("action", ""),
                    "scene_tone": plan.get("scene_tone", "平淡"),
                }
                sys = str(mot_input.get("system_prompt", "") or "") or agent.build_system_prompt()
                usr = agent.build_user_prompt(mot_input)
                result = await agent._call_llm(sys, usr, {"json_mode": True, "temperature": 0.7})

                if result.get("ok", False):
                    parsed = agent._parse_json_response(result)
                    data: dict = parsed.get("data", {}) or {}
                    if not data.get("character_id"):
                        data["character_id"] = cid
                    validation = MananaSchema.validate_motivation_output(data)
                    if not validation.get("valid", False):
                        _log.warning("Motivation validation warn for %s: %s", cid, validation.get("errors", []))
                    return {"char_id": cid, "motivation": data}
                return {"char_id": cid, "motivation": {}}
            finally:
                await provider.cleanup()

        tasks = [run_one(cid) for cid in char_ids]
        return await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    # L2R2: Dialogue + Action parallel dispatch
    # ------------------------------------------------------------------

    async def _run_dialogue_actions_parallel(
        self, ctx: dict, plan: dict, motivations: list[dict],
    ) -> list[dict]:
        da_char_ids: list = plan.get("featured_characters", []) or []
        if not da_char_ids:
            return []

        interaction_map = self._build_interaction_map(plan)
        name_map = self._build_name_map(ctx)
        mot_map: dict[str, dict] = {}
        for m in motivations:
            m = m if isinstance(m, dict) else {}
            mot_map[str(m.get("char_id", ""))] = m.get("motivation", {}) or {}

        async def run_dialogue(cid: str) -> tuple[str, dict]:
            provider = self._create_independent_provider("medium")
            if not provider:
                return (cid, {})
            try:
                agent = DialogueWeaver()
                agent.configure(provider)

                char_data = self._find_character(ctx, cid) or {}
                char_data["motivation_output"] = mot_map.get(cid, {})

                interaction_context: dict = {}
                if cid in interaction_map:
                    pair = interaction_map[cid]
                    counterpart_id = pair.get_counterpart(cid)
                    c_mot: dict = mot_map.get(counterpart_id, {}) or {}
                    c_internal: dict = c_mot.get("internal_state", {}) or {}
                    interaction_context = {
                        "pair_id": pair.pair_id,
                        "pair_type": pair.pair_type,
                        "counterpart": {
                            "name": name_map.get(counterpart_id, counterpart_id),
                            "emotional_tone": c_internal.get("dominant_emotion", "中性"),
                            "visible_goal": c_internal.get("immediate_goal", ""),
                        },
                    }

                d_input = {
                    "system_prompt": self._load_prompt("dialogue_weaver"),
                    "character": char_data,
                    "interaction_context": interaction_context,
                    "beat_summary": plan.get("beat_summary", ""),
                    "player_action": (ctx.get("player", {}) or {}).get("action", ""),
                    "scene_tone": plan.get("scene_tone", "平淡"),
                }

                sys = str(d_input.get("system_prompt", "") or "") or agent.build_system_prompt()
                usr = agent.build_user_prompt(d_input)
                result = await agent._call_llm(sys, usr, {"json_mode": True, "temperature": 0.85})

                if result.get("ok", False):
                    parsed = agent._parse_json_response(result)
                    data: dict = parsed.get("data", {}) or {}
                    if not data.get("character_id"):
                        data["character_id"] = cid
                    validation = MananaSchema.validate_dialogue_output(data)
                    if not validation.get("valid", False):
                        _log.warning("Dialogue validation warn for %s: %s", cid, validation.get("errors", []))
                    return (cid, data)
                return (cid, {})
            finally:
                await provider.cleanup()

        async def run_action(cid: str) -> tuple[str, dict]:
            provider = self._create_independent_provider("light")
            if not provider:
                return (cid, {})
            try:
                agent = ActionDirector()
                agent.configure(provider)

                char_data = self._find_character(ctx, cid) or {}
                char_data["motivation_output"] = mot_map.get(cid, {})

                interaction_context: dict = {}
                if cid in interaction_map:
                    pair = interaction_map[cid]
                    counterpart_id = pair.get_counterpart(cid)
                    c_mot: dict = mot_map.get(counterpart_id, {}) or {}
                    c_internal: dict = c_mot.get("internal_state", {}) or {}
                    interaction_context = {
                        "pair_id": pair.pair_id,
                        "pair_type": pair.pair_type,
                        "counterpart": {
                            "name": name_map.get(counterpart_id, counterpart_id),
                            "emotional_tone": c_internal.get("dominant_emotion", "中性"),
                            "visible_goal": c_internal.get("immediate_goal", ""),
                        },
                    }

                a_input = {
                    "system_prompt": self._load_prompt("action_director"),
                    "character": char_data,
                    "interaction_context": interaction_context,
                    "beat_summary": plan.get("beat_summary", ""),
                    "player_action": (ctx.get("player", {}) or {}).get("action", ""),
                    "scene_tone": plan.get("scene_tone", "平淡"),
                }

                sys = str(a_input.get("system_prompt", "") or "") or agent.build_system_prompt()
                usr = agent.build_user_prompt(a_input)
                result = await agent._call_llm(sys, usr, {"json_mode": True, "temperature": 0.6, "max_tokens": 512})

                if result.get("ok", False):
                    parsed = agent._parse_json_response(result)
                    data: dict = parsed.get("data", {}) or {}
                    if not data.get("character_id"):
                        data["character_id"] = cid
                    return (cid, data)
                return (cid, {})
            finally:
                await provider.cleanup()

        # Launch all D and A tasks in parallel
        d_tasks = [run_dialogue(cid) for cid in da_char_ids if self._find_character(ctx, cid)]
        a_tasks = [run_action(cid) for cid in da_char_ids if self._find_character(ctx, cid)]

        d_results, a_results = await asyncio.gather(
            asyncio.gather(*d_tasks) if d_tasks else asyncio.sleep(0, result=[]),
            asyncio.gather(*a_tasks) if a_tasks else asyncio.sleep(0, result=[]),
        )

        # Workaround: gather on sleep returns None
        if not isinstance(d_results, list):
            d_results = []
        if not isinstance(a_results, list):
            a_results = []

        d_dict: dict[str, dict] = dict(d_results)
        a_dict: dict[str, dict] = dict(a_results)

        # Merge per character
        da_results: list[dict] = []
        for cid in da_char_ids:
            merged_char_data = self._find_character(ctx, cid) or {}
            d = d_dict.get(cid, {}) or {}
            actions_dict = a_dict.get(cid, {}) or {}

            dialogue_actions: list = d.get("actions", []) or []
            dedicated_actions: list = actions_dict.get("actions", []) or []

            merged_actions = list(dialogue_actions)
            for a in dedicated_actions:
                if not self._action_exists(merged_actions, a if isinstance(a, dict) else {}):
                    merged_actions.append(a)

            dialogue_texts: list[str] = []
            for dl in (d.get("dialogue", []) or []):
                dl = dl if isinstance(dl, dict) else {}
                dialogue_texts.append(f"{dl.get('target', '?')}: \"{dl.get('text', '')}\" ({dl.get('tone', '')})")

            da_results.append({
                "character_id": cid,
                "character_name": merged_char_data.get("name", cid),
                "dialogue": " | ".join(dialogue_texts),
                "dialogue_raw": d.get("dialogue", []) or [],
                "actions": merged_actions,
                "actions_raw": d.get("actions", []) or [],
                "emotional_arc": d.get("emotional_arc", "") or "",
                "stance_change": d.get("stance_change", "") or "",
                "stance_change_raw": d.get("stance_change", {}) or {},
            })

        return da_results

    # ------------------------------------------------------------------
    # L4b: ThreadManager
    # ------------------------------------------------------------------

    async def _run_thread_manager(
        self, narrative_text: str, beat_summary: str, plan: dict, world_state: dict,
    ) -> dict:
        agent = ThreadManager()
        agent.configure(self._get_provider_for_tier("medium"))

        active_threads: list = world_state.get("active_threads", []) or []
        pool_config: dict = world_state.get("thread_pool_config", {}) or {}

        input_data = {
            "system_prompt": self._load_prompt("thread_manager"),
            "narrative_text": narrative_text,
            "beat_summary": beat_summary,
            "active_threads": active_threads,
            "thread_pool_config": pool_config,
            "narrative_mode": plan.get("narrative_mode", ""),
        }

        result = await agent.run(input_data)
        if result.get("ok", False):
            return result.get("raw", {}) or {}
        return {}

    # ------------------------------------------------------------------
    # L5: Oracle
    # ------------------------------------------------------------------

    async def _run_oracle(self, ctx: dict, world_state: dict) -> None:
        agent = ReflectionOracle()
        agent.configure(self._get_provider_for_tier("strong"))

        threads_summary = "\n".join(
            f"- [{t.get('id', '?')}] {t.get('title', '?')} (进度: {t.get('progress', 0.0):.0%})"
            for t in (world_state.get("active_threads", []) or [])
            if isinstance(t, dict)
        )

        recent_history: list = world_state.get("narrative_history", []) or []
        characters: list = ctx.get("characters", []) or []

        character_arcs: list[dict] = []
        for c in characters:
            c = c if isinstance(c, dict) else {}
            cs: dict = c.get("current_state", {}) or {}
            character_arcs.append({
                "char_id": c.get("char_id", ""),
                "name": c.get("name", ""),
                "mood_progression": [cs.get("mood", "中性")],
                "key_actions": [],
                "stance_shift": c.get("relation_to_player", ""),
            })

        player: dict = ctx.get("player", {}) or {}
        player_profile = {
            "traits": (player.get("profile", {}) or {}).get("traits", []),
            "motivation": str((player.get("profile", {}) or {}).get("motivation", "")),
            "tendency": str((player.get("profile", {}) or {}).get("tendency", "中立")),
            "action": player.get("action", ""),
            "reputation_count": len(player.get("reputation", {}) or {}),
        }

        oracle_input = {
            "system_prompt": self._load_prompt("oracle"),
            "beat_count": self._beat_count,
            "active_threads_summary": threads_summary,
            "recent_beats_summary": recent_history[-10:],
            "character_arcs": character_arcs,
            "divergence_trend": ctx.get("divergence", 0.0),
            "player_profile": player_profile,
            "game_time": ctx.get("game_time", ""),
        }

        result = await agent.run(oracle_input)
        if result.get("ok", False):
            oracle_data: dict = result.get("raw", {}) or {}
            self._oracle_context = {
                "pacing": oracle_data.get("pacing_assessment", ""),
                "observations": oracle_data.get("character_observations", []) or [],
                "opportunities": oracle_data.get("narrative_opportunities", []) or [],
                "tone_recommendation": oracle_data.get("tone_recommendation", ""),
                "from_beat": self._beat_count,
            }
            log_layer("L5", f"Oracle 上下文已更新 "
                      f"({len(oracle_data.get('character_observations', []) or [])} 观察, "
                      f"{len(oracle_data.get('narrative_opportunities', []) or [])} 机会)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_character(self, ctx: dict, char_id: str) -> dict:
        chars: list = ctx.get("characters", []) or []
        for c in chars:
            c = c if isinstance(c, dict) else {}
            if c.get("char_id", "") == char_id:
                return c
        return {}

    def _build_name_map(self, ctx: dict) -> dict[str, str]:
        nm: dict[str, str] = {}
        for c in (ctx.get("characters", []) or []):
            c = c if isinstance(c, dict) else {}
            nm[str(c.get("char_id", ""))] = str(c.get("name", "??"))
        return nm

    def _build_interaction_map(self, plan: dict) -> dict[str, InteractionPair]:
        im: dict[str, InteractionPair] = {}
        pairs: list = plan.get("interaction_pairs", []) or []
        for p in pairs:
            p = p if isinstance(p, dict) else {}
            ip = InteractionPair.from_dict(p)
            for cid in ip.char_ids:
                im[cid] = ip
        return im

    @staticmethod
    def _action_exists(existing: list, new_action: dict) -> bool:
        new_desc = str(new_action.get("description", "") if isinstance(new_action, dict) else "")
        new_type = str(new_action.get("type", "") if isinstance(new_action, dict) else "")
        for e in existing:
            e = e if isinstance(e, dict) else {}
            if e.get("description", "") == new_desc and e.get("type", "") == new_type:
                return True
        return False

    # ------------------------------------------------------------------
    # Composer / Auditor / Extractor input builders
    # ------------------------------------------------------------------

    def _build_composer_input(self, plan: dict, character_outputs: list, ctx: dict) -> dict:
        location: dict = ctx.get("location", {}) or {}
        return {
            "system_prompt": self._load_prompt("composer"),
            "director_output": plan,
            "character_outputs": character_outputs,
            "scene_context_summary": {
                "game_time": ctx.get("game_time", ""),
                "location_name": location.get("name", ""),
                "location_atmosphere": location.get("atmosphere", ""),
                "player_action": (ctx.get("player", {}) or {}).get("action", ""),
            },
            "recent_narrative": self._last_narrative[:500] if self._last_narrative else "",
        }

    def _build_auditor_input(self, narrative_text: str, plan: dict, ctx: dict) -> dict:
        characters: list = ctx.get("characters", []) or []
        character_personas: dict[str, dict] = {}
        for c in characters:
            c = c if isinstance(c, dict) else {}
            char_id = str(c.get("char_id", ""))
            if not char_id:
                continue
            personality = str(c.get("personality", "") or "")
            traits: list[str] = []
            if personality:
                parts = personality.replace("、", ",").split(",")
                traits = [p.strip() for p in parts if p.strip()]
            character_personas[char_id] = {
                "name": c.get("name", ""),
                "core_traits": traits,
                "speech_style": personality,
                "core_fear": "",
                "known_facts": c.get("known_facts", []) or [],
            }

        recent_history: list = ctx.get("recent_history", []) or []
        recent_facts: list[str] = []
        for evt in recent_history:
            evt = evt if isinstance(evt, dict) else {}
            evt_summary = str(evt.get("summary", ""))
            if evt_summary:
                recent_facts.append(evt_summary)

        return {
            "system_prompt": self._load_prompt("auditor"),
            "narrative_text": narrative_text,
            "character_personas": character_personas,
            "world_rules": ctx.get("relevant_world_rules", ""),
            "recent_facts": recent_facts,
            "previous_narrative": self._last_narrative[:500] if self._last_narrative else "",
        }

    def _build_extractor_input(
        self, narrative_text: str, character_outputs: list, world_state: dict,
    ) -> dict:
        existing_state = {
            "character_moods": self._build_mood_snapshot(world_state),
            "character_locations": self._build_location_snapshot(world_state),
            "player_reputation": deepcopy(world_state.get("player_reputation", {}) or {}),
            "active_threads": world_state.get("active_threads", []) or [],
            "knowledge_graph": deepcopy(world_state.get("knowledge_graph", {}) or {}),
        }
        return {
            "system_prompt": self._load_prompt("state_extractor"),
            "narrative_text": narrative_text,
            "character_outputs": character_outputs,
            "existing_state": existing_state,
        }

    def _build_mood_snapshot(self, world_state: dict) -> dict:
        snap: dict[str, dict] = {}
        chars_state: dict = world_state.get("characters_state", {}) or {}
        for cid, cs in chars_state.items():
            cs = cs if isinstance(cs, dict) else {}
            snap[cid] = {"mood": cs.get("mood", "中性"), "intensity": cs.get("mood_intensity", 0.0)}
        return snap

    def _build_location_snapshot(self, world_state: dict) -> dict[str, str]:
        snap: dict[str, str] = {}
        chars_state: dict = world_state.get("characters_state", {}) or {}
        for cid, cs in chars_state.items():
            cs = cs if isinstance(cs, dict) else {}
            snap[cid] = str(cs.get("location", ""))
        return snap

    # ------------------------------------------------------------------
    # State application helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_state_patch(world_state: dict, state_patch: dict) -> None:
        """Apply reputation/mood/location/knowledge changes to world_state."""
        # Reputation changes
        for rc in (state_patch.get("reputation_changes", []) or []):
            rc = rc if isinstance(rc, dict) else {}
            char_id = str(rc.get("char_id", ""))
            delta = float(rc.get("delta", 0.0))
            if char_id:
                rep = world_state.setdefault("player_reputation", {})
                rep[char_id] = rep.get(char_id, 0.0) + delta

        # Mood changes
        for mc in (state_patch.get("mood_changes", []) or []):
            mc = mc if isinstance(mc, dict) else {}
            char_id = str(mc.get("char_id", ""))
            if char_id:
                cs = world_state.setdefault("characters_state", {}).setdefault(char_id, {})
                new_mood = mc.get("new_mood", "")
                if new_mood:
                    cs["mood"] = new_mood
                intensity = mc.get("intensity", None)
                if intensity is not None:
                    cs["mood_intensity"] = float(intensity)

        # Location changes
        for lc in (state_patch.get("location_changes", []) or []):
            lc = lc if isinstance(lc, dict) else {}
            char_id = str(lc.get("char_id", ""))
            to_loc = str(lc.get("to", ""))
            if char_id and to_loc:
                cs = world_state.setdefault("characters_state", {}).setdefault(char_id, {})
                cs["location"] = to_loc

        # New knowledge
        for nk in (state_patch.get("new_knowledge", []) or []):
            nk = nk if isinstance(nk, dict) else {}
            known_by: list = nk.get("known_by", []) or []
            content = str(nk.get("content", ""))
            if content and known_by:
                kg = world_state.setdefault("knowledge_graph", {})
                for kb in known_by:
                    kg.setdefault(str(kb), []).append(content)

        # Dynamic NPCs
        for npc in (state_patch.get("new_dynamic_npcs", []) or []):
            npc = npc if isinstance(npc, dict) else {}
            name = str(npc.get("name", ""))
            if name:
                dn = world_state.setdefault("dynamic_npcs", {})
                npc_id = f"dyn_{name}"
                dn[npc_id] = npc

        # Player profile updates
        ppu: dict = state_patch.get("player_profile_updates", {}) or {}
        if ppu and isinstance(ppu, dict) and ppu:
            profile = world_state.setdefault("player_profile", {})
            if ppu.get("new_trait"):
                profile.setdefault("traits", []).append(ppu["new_trait"])
            if ppu.get("updated_motivation"):
                profile["motivation"] = ppu["updated_motivation"]
            if ppu.get("tendency_shift"):
                profile["tendency"] = ppu["tendency_shift"]

    @staticmethod
    def _apply_thread_updates(world_state: dict, updates: dict) -> None:
        """Apply ThreadManager changes to world_state."""
        # Advances
        for adv in (updates.get("thread_advances", []) or []):
            adv = adv if isinstance(adv, dict) else {}
            tid = str(adv.get("thread_id", ""))
            delta = float(adv.get("delta", 0.0))
            if tid and delta > 0:
                for t in (world_state.get("active_threads", []) or []):
                    t = t if isinstance(t, dict) else {}
                    if t.get("id", "") == tid:
                        t["progress"] = min(1.0, float(t.get("progress", 0.0)) + delta)
                        break

        # New threads
        for nt in (updates.get("new_threads", []) or []):
            nt = nt if isinstance(nt, dict) else {}
            title = str(nt.get("title", ""))
            ttype = str(nt.get("type", "side"))
            if title:
                new_t = {
                    "id": f"thread_{len(world_state.get('active_threads', [])) + 1:03d}",
                    "title": title,
                    "type": ttype,
                    "progress": 0.0,
                    "tension": 0.3,
                    "priority": 0.5,
                    "question": nt.get("question", ""),
                    "involved_characters": [],
                    "player_attention": 0.5,
                }
                world_state.setdefault("active_threads", []).append(new_t)

        # Closed threads
        closed_ids: set[str] = set()
        for ct in (updates.get("closed_threads", []) or []):
            closed_ids.add(str(ct))
        if closed_ids:
            active = world_state.get("active_threads", []) or []
            world_state["active_threads"] = [
                t for t in active
                if str((t if isinstance(t, dict) else {}).get("id", "")) not in closed_ids
            ]

        # Tension adjustments
        for ta in (updates.get("tension_adjustments", []) or []):
            ta = ta if isinstance(ta, dict) else {}
            tid = str(ta.get("thread_id", ""))
            tension = float(ta.get("new_tension", 0.5))
            if tid:
                for t in (world_state.get("active_threads", []) or []):
                    t = t if isinstance(t, dict) else {}
                    if t.get("id", "") == tid:
                        t["tension"] = tension
                        break

    @staticmethod
    def _add_narrative_event(world_state: dict, summary: str, beat_id: str) -> None:
        world_state.setdefault("narrative_history", []).append({
            "time": world_state.get("game_time", ""),
            "summary": summary,
            "event_id": beat_id,
        })

    @staticmethod
    def _add_scene_memory(world_state: dict, entry: str) -> None:
        world_state.setdefault("scene_memory", []).append(entry)

    @staticmethod
    def _advance_game_time(world_state: dict) -> None:
        # Simple increment: advance by 1 time unit
        current = int(world_state.get("game_time_tick", 0))
        world_state["game_time_tick"] = current + 1

    # ------------------------------------------------------------------
    # Prompt loading
    # ------------------------------------------------------------------

    def _load_prompt(self, agent_key: str) -> str:
        """Load a prompt template from prompts/{agent_key}.md with caching."""
        if agent_key in self._prompt_cache:
            return self._prompt_cache[agent_key]

        # Try loading from prompts/ directory relative to config path
        config_dir = os.path.dirname(os.path.abspath(self._config.CONFIG_PATH))
        prompt_path = os.path.join(config_dir, "prompts", f"{agent_key}.md")

        if os.path.isfile(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read()
                self._prompt_cache[agent_key] = content
                return content

        # Fallback: empty string (agents use their built-in defaults)
        _log.warning("Prompt file not found: %s, using built-in default", prompt_path)
        self._prompt_cache[agent_key] = ""
        return ""

    # ------------------------------------------------------------------
    # v4: Context augmentation
    # ------------------------------------------------------------------

    async def _augment_context(self, ctx: dict) -> dict:
        """v4: Semantic Canon selection + vector memory retrieval + micro feedback."""
        # Micro-Oracle feedback from previous beat
        micro_feedback = str(self._next_beat_context.get("micro_feedback", ""))
        if micro_feedback:
            ctx["micro_feedback"] = micro_feedback

        # Semantic selection (placeholder — requires CanonSelector LLM agent)
        # Vector memory (placeholder — requires embedding infrastructure)

        return ctx

    # ------------------------------------------------------------------
    # v4: Best-of-3 Director
    # ------------------------------------------------------------------

    async def _run_director_best_of_3(self, ctx: dict, prompt_key: str = "director") -> dict:
        bo3_config = self._config.get_best_of_3_config()
        sample_count = bo3_config.get("sample_count", 3)
        min_total = bo3_config.get("scorer_min_total", 8)

        # Temperature sequence
        if sample_count == 1:
            temps = [0.6]
        elif sample_count == 2:
            temps = [0.4, 0.7]
        else:
            temps = [0.4, 0.6, 0.8]

        plans: list[dict] = []
        for temp in temps:
            director = SceneDirector()
            director.configure(self._get_provider_for_tier("strong"))
            d_input = {"system_prompt": self._load_prompt(prompt_key), "scene_context": ctx}
            result = await director.run(d_input)
            if result.get("ok", False):
                raw: dict = result.get("raw", {}) or {}
                if raw:
                    plans.append(raw)

        if not plans:
            log_error("SceneDirector", "Best-of-3: all directors failed")
            return {"error": "All directors failed", "raw": {}}

        if len(plans) == 1:
            return {"ok": True, "raw": plans[0]}

        # Score and select best
        scorer = PlanScorerAgent()
        scorer.configure(self._get_provider_for_tier("light"))

        best_plan = plans[0]
        best_total = 0
        for plan in plans:
            score_result = await scorer.run(plan)
            total = int(score_result.get("total", 0))
            if total > best_total:
                best_total = total
                best_plan = plan

        if best_total < min_total and len(plans) > 1:
            log_warning("SceneDirector", f"Best-of-3: all plans below min_total ({min_total}), using best available")

        log_layer("L1", f"Best-of-3 选中: total={best_total} (from {len(plans)} candidates)")
        return {"ok": True, "raw": best_plan}

    # ------------------------------------------------------------------
    # v4: Multi-View Director
    # ------------------------------------------------------------------

    async def _run_director_multi_view(self, ctx: dict) -> dict:
        # ── Plot-driven ──
        log_layer("L1", "Multi-View: 启动 plot-driven Best-of-3")
        plot_ctx = deepcopy(ctx)
        plot_ctx["_director_mode"] = "plot_driven"
        plot_result = await self._run_director_best_of_3(plot_ctx, "director_plot")
        plot_plan: dict = plot_result.get("raw", {}) or {}

        # ── Character-driven ──
        log_layer("L1", "Multi-View: 启动 character-driven Best-of-3")
        char_ctx = deepcopy(ctx)
        char_ctx["_director_mode"] = "character_driven"
        char_result = await self._run_director_best_of_3(char_ctx, "director_char")
        char_plan: dict = char_result.get("raw", {}) or {}

        # ── Synthesizer ──
        log_layer("L1", "Multi-View: Synthesizer 融合双视角")
        synthesizer = PlanSynthesizerAgent()
        synthesizer.configure(self._get_provider_for_tier("medium"))

        synth_input = {
            "plot_plan": plot_plan,
            "character_plan": char_plan,
            "scene_context": ctx,
        }
        synth_result = await synthesizer.run(synth_input)
        final_plan: dict = synth_result.get("raw", {}) or {}

        if not final_plan:
            final_plan = char_plan if char_plan else plot_plan

        log_layer("L1", "Multi-View: 合成完成")
        return final_plan

    # ------------------------------------------------------------------
    # v4: Composer Refinement Loop
    # ------------------------------------------------------------------

    async def _run_composer_with_refinement(
        self, ctx: dict, character_outputs: list, plan: dict,
    ) -> dict:
        limits = self._config.get_refinement_limits()
        max_warning_refine = limits.get("max_warning_refine", 1)
        max_fail_rewrite = limits.get("max_fail_rewrite", 2)

        # Round 1: Composer → Auditor
        composer = SceneComposer()
        composer.configure(self._get_provider_for_tier("strong"))
        composer_input = self._build_composer_input(plan, character_outputs, ctx)
        result = await composer.run(composer_input)

        if not result.get("ok", False):
            return result

        narrative_text: str = result.get("content", "") or ""

        auditor = ConsistencyAuditor()
        auditor.configure(self._get_provider_for_tier("medium"))
        auditor_input = self._build_auditor_input(narrative_text, plan, ctx)
        audit_result = await auditor.run(auditor_input)
        audit_data: dict = audit_result.get("raw", {}) or {}
        verdict = str(audit_data.get("verdict", "PASS"))

        if verdict == "PASS":
            log_layer("L3", "精炼循环: PASS — 无需精炼")
            return result

        # WARNING: one round of refinement
        if verdict == "WARNING":
            log_layer("L3", "精炼循环: WARNING — 微调1轮")
            for _ in range(max_warning_refine):
                refinement_hints: list = audit_data.get("refinement_hints", []) or []
                if not refinement_hints:
                    # Fallback: use issues as hints
                    refinement_hints = audit_data.get("issues", []) or []
                composer_input["refinement_hints"] = refinement_hints
                composer_input["mode"] = "refine"
                result = await composer.run(composer_input)
                if result.get("ok", False):
                    return result
            return result

        # FAIL: rewrite up to max_fail_rewrite rounds
        log_layer("L3", f"精炼循环: FAIL — 重写最多{max_fail_rewrite}轮")
        initial_quality = float(audit_data.get("overall_quality", {}).get("character_consistency", 0.5) if isinstance(audit_data.get("overall_quality"), dict) else 0.5)
        candidates: list[dict] = [{"result": result, "quality": initial_quality}]

        for _ in range(max_fail_rewrite):
            refinement_hints = audit_data.get("refinement_hints", []) or []
            if not refinement_hints:
                refinement_hints = audit_data.get("issues", []) or []

            rewrite_input = self._build_composer_input(plan, character_outputs, ctx)
            rewrite_input["refinement_hints"] = refinement_hints
            rewrite_input["mode"] = "rewrite"

            rewrite_result = await composer.run(rewrite_input)
            if not rewrite_result.get("ok", False):
                continue

            rewrite_text = rewrite_result.get("content", "") or ""
            re_auditor_input = self._build_auditor_input(rewrite_text, plan, ctx)
            re_audit_result = await auditor.run(re_auditor_input)
            re_audit_data: dict = re_audit_result.get("raw", {}) or {}
            re_verdict = str(re_audit_data.get("verdict", "FAIL"))

            oq = re_audit_data.get("overall_quality", {})
            re_quality = float(
                oq.get("character_consistency", 0.5)
                if isinstance(oq, dict) else 0.5
            )

            candidates.append({"result": rewrite_result, "quality": re_quality})

            if re_verdict == "PASS":
                return rewrite_result

            audit_data = re_audit_data

        # Pick highest-quality candidate
        picked = candidates[0]["result"]
        picked_quality = float(candidates[0]["quality"])
        for cand in candidates:
            q = float(cand["quality"])
            if q > picked_quality:
                picked_quality = q
                picked = cand["result"]

        log_layer("L3", f"精炼循环: 从{len(candidates)}个候选中选取最优 (quality={picked_quality:.2f})")
        return picked

    # ------------------------------------------------------------------
    # v4: Micro-Oracle
    # ------------------------------------------------------------------

    async def _run_micro_oracle(self, narrative_text: str, summary_text: str, ctx: dict) -> None:
        agent = MicroOracleAgent()
        agent.configure(self._get_provider_for_tier("light"))

        mo_input = {"narrative_summary": summary_text, "scene_context": ctx}
        feedback = await agent.run(mo_input)

        feedback = feedback if isinstance(feedback, dict) else {}
        self._micro_oracle_buffer.append(feedback)
        if len(self._micro_oracle_buffer) > 10:
            self._micro_oracle_buffer.pop(0)

        self._next_beat_context["micro_feedback"] = str(feedback.get("one_line_feedback", ""))

        if feedback.get("has_issue", False):
            severity = str(feedback.get("severity", "info"))
            if severity in ("alert", "warning"):
                log_warning("MicroOracle",
                            f"Beat {self._beat_count}: [{severity}] {feedback.get('one_line_feedback', '')}")

    # ------------------------------------------------------------------
    # v4: Complexity scoring
    # ------------------------------------------------------------------

    def _compute_complexity(self, ctx: dict, plan: dict) -> float:
        score = 0.0

        # New character
        if self._has_new_character(ctx):
            score += 0.3

        # Multiple threads
        involved_threads: list = plan.get("priority_thread_ids", []) or []
        if len(involved_threads) >= 2:
            score += 0.25

        # High divergence
        divergence = float(ctx.get("divergence", 0.0))
        if divergence >= 0.4:
            score += 0.2

        # Conflict scene
        pairs: list = plan.get("interaction_pairs", []) or []
        for p in pairs:
            p = p if isinstance(p, dict) else {}
            if str(p.get("pair_type", "")) == "conflict":
                score += 0.15
                break

        # Player intervention keywords
        player_action = str((ctx.get("player", {}) or {}).get("action", ""))
        if self._contains_intervention_keywords(player_action):
            score += 0.1

        return min(score, 1.0)

    def _has_new_character(self, ctx: dict) -> bool:
        """Check if any character is new (not in world_state known characters).

        Since we don't have direct access to WorldState in pure Python, we check
        is_dynamic flag which ContextBuilder sets for dynamic NPCs.
        """
        chars: list = ctx.get("characters", []) or []
        for c in chars:
            c = c if isinstance(c, dict) else {}
            if c.get("is_dynamic", False):
                return True
        return False

    @staticmethod
    def _contains_intervention_keywords(action: str) -> bool:
        keywords = ["阻止", "改变", "干涉", "打断", "制止", "干预", "插手"]
        for kw in keywords:
            if kw in action:
                return True
        return False

    # ------------------------------------------------------------------
    # v4: Dynamic tier overrides
    # ------------------------------------------------------------------

    def _apply_tier_overrides(self, complexity: float) -> None:
        overrides = self._config.get_tier_overrides(complexity)
        if overrides:
            log_layer("L1", f"动态Tier: complexity={complexity:.2f} → overrides={json.dumps(overrides, ensure_ascii=False)}")
        # In a full implementation, overrides would modify provider routing.
        # Current simplified approach logs the suggestion only.

    # ------------------------------------------------------------------
    # Hot reconnect
    # ------------------------------------------------------------------

    def request_reconnect(self) -> None:
        """Request provider reconnection after the next beat completes."""
        self._pending_reconnect = True
        _log.info("Hot reconnect requested — will apply after current beat completes")

    async def _do_reconnect(self) -> None:
        """Execute provider reconnection."""
        _log.info("Executing hot reconnect...")
        for prov in (self._provider_strong, self._provider_medium, self._provider_light):
            if prov:
                await prov.cleanup()
        self._provider_strong = None
        self._provider_medium = None
        self._provider_light = None
        await self._init_providers()
        self._pending_reconnect = False
        _log.info("Hot reconnect complete")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        """Check if at least the strong provider is available."""
        return self._provider_strong is not None

    def get_beat_count(self) -> int:
        return self._beat_count

    def get_last_narrative(self) -> str:
        return self._last_narrative

    def get_oracle_context(self) -> dict:
        return dict(self._oracle_context)

    def get_config_value(self, section: str, key: str, default: Any = "") -> Any:
        """Get a config value by section and key."""
        self._config._ensure_loaded()
        return self._config._get_str(section, key, str(default))
