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
  导演层: Director, Composer, Oracle
  演员层: Motivation, Dialogue, Auditor, Thread, Synthesizer, ContinuityChecker
  动作层: Action, Extractor, Scorer, MicroOracle, RoleReflector, CharMgr, LocMgr
"""

from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any, Callable, Optional, TYPE_CHECKING

from .agents import (
    ActionDirector,
    CharacterManager,
    ConsistencyAuditor,
    ContinuityChecker,
    DialogueWeaver,
    LocationManager,
    MicroOracleAgent,
    MotivationEngine,
    PlanScorerAgent,
    PlanSynthesizerAgent,
    ReflectionOracle,
    RoleReflector,
    SceneComposer,
    SceneDirector,
    StateExtractor,
    ThreadManager,
)
from .config import MananaConfig
from .pipeline_context import ContextBuilder
from .pipeline_helpers import replace_ids_with_names, split_narrative
from .pipeline_state import InteractionPair, apply_state_patch
from .providers import BaseProvider, ProviderFactory
from .schema import MananaSchema
from .utils import (
    get_logger,
    log_error,
    log_layer,
    log_warning,
    set_current_beat,
)

_log = get_logger("MaNA.Pipeline")


class MananaPipeline:
    """MaNA v4 — 5-layer multi-agent narrative pipeline.

    Usage:
        pipeline = MananaPipeline(yaml_dict=cfg)
        await pipeline.initialize()
        result = await pipeline.run_beat("玩家走向图书馆")
    """

    def __init__(self, yaml_dict: dict = None) -> None:
        self._config = MananaConfig(yaml_dict=yaml_dict)
        self._provider_strong: Optional[BaseProvider] = None
        self._provider_medium: Optional[BaseProvider] = None
        self._provider_light: Optional[BaseProvider] = None
        self._beat_count: int = 0
        self._oracle_context: dict[str, Any] = {}
        self._last_narrative: str = ""
        self._last_ending_hook: str = ""
        self._last_action_hints: list[str] = []
        self._pending_reconnect: bool = False

        # v4 state
        self._micro_oracle_buffer: list[dict] = []
        self._next_beat_context: dict[str, Any] = {}

        # T04: Narrative mode tracking
        self._current_narrative_mode: str = "exploration"
        self._mode_duration: int = 0


    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load config and initialize all three provider tiers."""
        await self._init_providers()

    async def _init_providers(self) -> None:
        """Create and configure strong/medium/light providers."""
        failed_tiers = []
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
                error_msg = f"Could not create '{prov_type}' provider for tier '{tier}'"
                _log.error("Pipeline init failed: %s", error_msg)
                failed_tiers.append(tier)
        
        # 如果所有tier都失败了，抛出异常
        if len(failed_tiers) == 3:
            raise RuntimeError(f"All provider tiers failed to initialize: {failed_tiers}")
        elif failed_tiers:
            _log.warning("Some provider tiers failed to initialize: %s", failed_tiers)

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

    # T04: Narrative mode rotation
    _NARRATIVE_MODES = [
        "exploration", "dialogue", "conflict", "revelation", "daily_life",
    ]

    _MODE_TRANSITIONS: dict[str, list[str]] = {
        "exploration": ["dialogue", "conflict", "revelation", "daily_life"],
        "dialogue": ["conflict", "revelation", "daily_life", "exploration"],
        "conflict": ["revelation", "dialogue", "daily_life", "exploration"],
        "revelation": ["daily_life", "conflict", "dialogue", "exploration"],
        "daily_life": ["exploration", "dialogue", "conflict", "revelation"],
    }

    @staticmethod
    def _get_next_narrative_mode(current_mode: str, beat_count: int, context: dict) -> str:
        """3–8 拍轮换一次叙事模式。

        简单轮换策略：
        1. 如果当前模式已持续 >= 8 拍，强制轮换
        2. 如果当前模式已持续 >= 3 拍，有 25% 几率轮换
        3. 否则保持当前模式
        """
        mode_duration = context.get("mode_duration", 0)
        if mode_duration >= 8:
            # 强制轮换——从候选中选第一个
            transitions = MananaPipeline._MODE_TRANSITIONS.get(current_mode, MananaPipeline._NARRATIVE_MODES)
            return transitions[0] if transitions else "exploration"
        elif mode_duration >= 3:
            # 25% 几率轮换
            import random
            if random.random() < 0.25:
                transitions = MananaPipeline._MODE_TRANSITIONS.get(current_mode, MananaPipeline._NARRATIVE_MODES)
                chosen = random.choice(transitions)
                return chosen
        return current_mode

    @staticmethod
    def _get_suggested_next_modes(current_mode: str) -> list[str]:
        """获取当前模式的建议轮换候选项（最多 2 个）。"""
        transitions = MananaPipeline._MODE_TRANSITIONS.get(current_mode, MananaPipeline._NARRATIVE_MODES)
        return transitions[:2] if len(transitions) >= 2 else transitions

    async def run_beat(
        self,
        player_action: str,
        world_state: "WorldState",
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> dict:
        """Execute a complete narrative beat.

        Args:
            player_action: Player's current input/action text.
            world_state: WorldState object containing all world state data.
            progress_cb: Optional async callback(agent_key, label) for
                         pushing agent status to the frontend.

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
        if progress_cb:
            await progress_cb("context_builder", "正在构建场景上下文...")
        # 兼容 dict 和 WorldState 对象两种入参
        if isinstance(world_state, dict):
            ws_dict = world_state
        else:
            ws_dict = world_state.to_dict()
        ctx = ContextBuilder.build(player_action, ws_dict, beat_id=beat_id)

        # ── 注入记忆到场景上下文（记忆系统启用时） ──
        if self._config.is_feature_enabled("memory_system"):
            ctx = await self._inject_memory_to_ctx(ctx, ws_dict, world_state)

        # ── Conflict seed injection（T02: 注入 Canon 冲突种子） ──
        if not isinstance(world_state, dict):
            conflict_pool = getattr(world_state, "conflict_pool", None)
            if conflict_pool is not None:
                seeds = conflict_pool.get_random_combination(2)
                if seeds:
                    ctx["available_conflicts"] = seeds
                    _log.debug("注入了 %d 个冲突种子到场景上下文", len(seeds))

        # ── T04: 注入模式轮换上下文 ──
        ctx["narrative_mode"] = self._current_narrative_mode
        ctx["mode_duration"] = self._mode_duration
        suggested = self._get_suggested_next_modes(self._current_narrative_mode)
        if suggested:
            ctx["suggested_next_modes"] = suggested
        log_layer("L0", f"ContextBuilder 完成 ({len(ctx.get('characters', []))} 角色, "
                  f"{len(ctx.get('active_threads', []))} 线索)")

        # ── v4: Context augmentation (semantic_selection + vector_memory + micro_feedback) ──
        if self._config.is_feature_enabled("semantic_selection") or \
           self._config.get_vector_memory_config().get("enable_vector_memory", False):
            ctx = await self._augment_context(ctx)

        # ── 注入上拍结尾预告到场景上下文（让下一拍的 Director 看到上一拍的 ending_hook） ──
        if self._last_ending_hook:
            ctx["prev_ending_hook"] = self._last_ending_hook
            ctx["prev_action_hints"] = list(self._last_action_hints)

        # ── L1: Director ──
        plan: dict = {}
        if self._config.is_feature_enabled("multi_view") and self._config.is_feature_enabled("best_of_3"):
            log_layer("L1", "SceneDirector 启动 (multi_view + best_of_3)")
            if progress_cb:
                await progress_cb("scene_director", "导演正在编排剧情...")
            plan = await self._run_director_multi_view(ctx)
        elif self._config.is_feature_enabled("best_of_3"):
            log_layer("L1", "SceneDirector 启动 (best_of_3)")
            if progress_cb:
                await progress_cb("scene_director", "导演正在编排剧情...")
            best_plan = await self._run_director_best_of_3(ctx)
            plan = best_plan.get("raw", {}) or {}
            if not plan and best_plan:
                plan = best_plan
        else:
            log_layer("L1", "SceneDirector 启动")
            if progress_cb:
                await progress_cb("scene_director", "导演正在编排剧情...")
            director = SceneDirector()
            director.configure(self._get_provider_for_tier("strong"))
            director_input = {"scene_context": ctx}
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

        # ── T04: 更新模式追踪（Director 可能主动切换模式） ──
        chosen_mode = str(plan.get("narrative_mode", self._current_narrative_mode))
        if chosen_mode and chosen_mode in self._NARRATIVE_MODES:
            if chosen_mode == self._current_narrative_mode:
                self._mode_duration += 1
            else:
                self._current_narrative_mode = chosen_mode
                self._mode_duration = 1
        else:
            # 如果 Director 给出非法模式，保持当前模式并累加
            self._mode_duration += 1

        # ── v4: Complexity scoring + dynamic tier ──
        if self._config.is_feature_enabled("dynamic_tier"):
            complexity = self._compute_complexity(ctx, plan)
            log_layer("L1", f"复杂度评分: {complexity:.2f}")
            self._apply_tier_overrides(complexity)

        # ── L1b: ContinuityChecker（连续叙事审计） ──
        if self._config.is_feature_enabled("continuity_check"):
            log_layer("L1b", "ContinuityChecker 启动")
            if progress_cb:
                await progress_cb("continuity_checker", "审计叙事连贯性...")
            cc_result = await self._run_continuity_check(plan, ctx, player_action, ws_dict)
            cc_verdict = str(cc_result.get("verdict", "APPROVED"))

            cc_retry = 0
            while cc_verdict == "REJECTED" and cc_retry < self._config.get_continuity_max_rewrite():
                cc_retry += 1
                _log.info(f"L1b 打回重做 (第{cc_retry}次)...")
                # 带着约束重新跑 Director
                director = SceneDirector()
                director.configure(self._get_provider_for_tier("strong"))
                director_input = {"scene_context": ctx,
                                  "continuity_constraints": cc_result.get("conflict_details", [])}
                beat_plan_result = await director.run(director_input)
                if beat_plan_result.get("ok", False):
                    plan = beat_plan_result.get("raw", {}) or {}
                cc_result = await self._run_continuity_check(plan, ctx, player_action, ws_dict)
                cc_verdict = str(cc_result.get("verdict", "APPROVED"))

            if cc_verdict == "REJECTED":
                log_warning("ContinuityChecker", f"L1b 超过重做上限，强制通过")
                cc_verdict = "APPROVED"

            log_layer("L1b", f"ContinuityChecker 完成 — {cc_verdict}")

        # ── L2R1: MotivationEngine (N parallel) ──
        featured_chars: list = plan.get("featured_characters", []) or []
        log_layer("L2R1", f"MotivationEngine 启动 ({len(featured_chars)} 角色)")
        if progress_cb:
            await progress_cb("motivation", "演员正在酝酿动机...")
        motivation_results = await self._run_motivations_parallel(ctx, plan)
        log_layer("L2R1", f"MotivationEngine 完成 ({len(motivation_results)} 结果)")

        # ── L2R2: DialogueWeaver + ActionDirector (N×2 parallel) ──
        log_layer("L2R2", "DialogueWeaver/ActionDirector 启动")
        if progress_cb:
            await progress_cb("dialogue", "演员正在对戏...")
        character_outputs = await self._run_dialogue_actions_parallel(ctx, plan, motivation_results)
        log_layer("L2R2", f"DialogueWeaver/ActionDirector 完成 ({len(character_outputs)} 角色输出)")

        # ── L2R3: RoleReflector（角色过渡反思） ──
        if self._config.is_feature_enabled("role_reflection"):
            log_layer("L2R3", "RoleReflector 启动")
            if progress_cb:
                await progress_cb("role_reflector", "演员正在反思表演...")
            rr_result = await self._run_role_reflection(character_outputs, ws_dict, plan)
            rr_results: list = rr_result.get("results", []) or []

            # 处理 NEED_TRANSITION: 附加过渡
            for rr in rr_results:
                if rr.get("verdict") == "NEED_TRANSITION":
                    char_id = rr.get("char_id", "")
                    transition_dialogue = rr.get("transition_dialogue", "")
                    transition_action = rr.get("transition_action", "")
                    for co in character_outputs:
                        if co.get("character_id", co.get("char_id", "")) == char_id:
                            if transition_dialogue:
                                co.setdefault("dialogue", []).append({
                                    "text": transition_dialogue,
                                    "tone": "过渡",
                                    "target": "none",
                                    "subtext": "过渡衔接",
                                })
                            if transition_action:
                                co.setdefault("actions", []).append({
                                    "type": "transition",
                                    "description": transition_action,
                                    "target": "none",
                                    "intensity": "subtle",
                                })
                            break

            # 处理 NEED_REWRITE: 打回 L2R2 重做
            rewrite_chars = [r.get("char_id", "") for r in rr_results
                             if r.get("verdict") == "NEED_REWRITE"]
            rewrite_count = 0
            while rewrite_chars and rewrite_count < 2:
                rewrite_count += 1
                _log.info(f"L2R3 打回重做第{rewrite_count}次: {rewrite_chars}")
                # 重新跑受影响的角色的 L2R2
                new_outputs = []
                for co in character_outputs:
                    cid = co.get("character_id", co.get("char_id", ""))
                    if cid in rewrite_chars:
                        constraint = next(
                            (r.get("rewrite_constraint", "") for r in rr_results
                             if r.get("char_id") == cid), "")
                        new_co = await self._rerun_character_performance(
                            cid, ctx, plan, motivation_results, constraint)
                        if new_co:
                            new_outputs.append(new_co)
                        else:
                            new_outputs.append(co)
                    else:
                        new_outputs.append(co)
                character_outputs = new_outputs

                # 重新跑 RoleReflector
                rr_result = await self._run_role_reflection(character_outputs, ws_dict, plan)
                rr_results = rr_result.get("results", []) or []
                rewrite_chars = [r.get("char_id", "") for r in rr_results
                                 if r.get("verdict") == "NEED_REWRITE"]

            if rewrite_chars:
                log_warning("RoleReflector", f"L2R3 超过重做上限，遗留: {rewrite_chars}")

            log_layer("L2R3", f"RoleReflector 完成 ({len(rr_results)} 角色)")

        # ── L3: SceneComposer ──
        narrative_result: dict = {}
        if self._config.is_feature_enabled("refinement"):
            log_layer("L3", "SceneComposer 启动 (精炼循环)")
            if progress_cb:
                await progress_cb("composer", "编剧正在合成本章...")
            narrative_result = await self._run_composer_with_refinement(ctx, character_outputs, plan)
        else:
            log_layer("L3", "SceneComposer 启动")
            if progress_cb:
                await progress_cb("composer", "编剧正在合成本章...")
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

        # ── L3b ∥ L4a: Auditor + Extractor + CharMgr + LocMgr (四路并行) ──
        log_layer("L3b∥L4a", "Auditor / Extractor / CharMgr / LocMgr 启动 (四路并行)")
        if progress_cb:
            await progress_cb("auditor", "审计员正在验收...")

        auditor_input = self._build_auditor_input(narrative_text, plan, ctx)
        extractor_input = self._build_extractor_input(narrative_text, character_outputs, ws_dict)

        auditor = ConsistencyAuditor()
        auditor.configure(self._get_provider_for_tier("medium"))
        extractor = StateExtractor()
        extractor.configure(self._get_provider_for_tier("light"))

        tasks = [
            auditor.run(auditor_input),
            extractor.run(extractor_input),
        ]

        # CharMgr + LocMgr（当 emergence_system 开启时）
        if self._config.is_feature_enabled("emergence_system"):
            char_mgr = CharacterManager()
            char_mgr.configure(self._get_provider_for_tier("light"))
            loc_mgr = LocationManager()
            loc_mgr.configure(self._get_provider_for_tier("light"))

            char_mgr_input = self._build_char_mgr_input(narrative_text, ws_dict)
            loc_mgr_input = self._build_loc_mgr_input(narrative_text, ws_dict)

            tasks.append(char_mgr.run(char_mgr_input))
            tasks.append(loc_mgr.run(loc_mgr_input))

        results = await asyncio.gather(*tasks)

        audit_result = results[0]
        state_patch_result = results[1]

        # 处理涌现实体结果
        char_mgr_result = {}
        loc_mgr_result = {}
        if self._config.is_feature_enabled("emergence_system") and len(results) >= 4:
            char_mgr_result = results[2]
            loc_mgr_result = results[3]
            await self._process_emergences(world_state, char_mgr_result, loc_mgr_result)

        log_layer("L3b∥L4a", "Auditor / Extractor / CharMgr / LocMgr 完成")

        # Audit FAIL handling
        audit_data: dict = audit_result.get("raw", {}) or {}
        if str(audit_data.get("verdict", "PASS")) not in ("PASS",):
            issues: list = audit_data.get("issues", []) or []
            log_warning("Auditor", f"Beat {beat_id} audit FAIL: {len(issues)} issues")

        # ── L4b: ThreadManager ──
        log_layer("L4b", "ThreadManager 启动")
        if progress_cb:
            await progress_cb("thread_manager", "线索管理员正在整理...")
        thread_updates = await self._run_thread_manager(
            narrative_text, str(plan.get("beat_summary", "")), plan, ws_dict,
        )
        log_layer("L4b", "ThreadManager 完成")

        # ── Apply state changes ──
        state_patch: dict = state_patch_result.get("raw", {}) or {}
        if state_patch and not isinstance(world_state, dict):
            apply_state_patch(world_state, state_patch)

        # ── Apply thread changes ──
        if not isinstance(world_state, dict):
            world_state.apply_thread_updates(thread_updates)

        # ── Narrative history + memory ──
        summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
        if not summary:
            summary = narrative_text[:100]
        if not isinstance(world_state, dict):
            world_state.add_narrative_event(summary, beat_id)
        mem_entry = str(state_patch.get("scene_memory_entry", narrative_text[:60]))
        if mem_entry:
            if not isinstance(world_state, dict):
                world_state.add_scene_memory(mem_entry)

        # ── L5: Oracle (conditional) ──
        if self._beat_count % self._config.get_oracle_interval() == 0:
            log_layer("L5", f"ReflectionOracle 触发 (beat {self._beat_count})")
            if progress_cb:
                await progress_cb("oracle", "神域正在介入...")
            await self._run_oracle(ctx, ws_dict)

        # ── v4: Micro-Oracle ──
        mo_feedback: dict = {}
        if self._config.is_feature_enabled("micro_oracle"):
            mo_summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
            if not mo_summary:
                mo_summary = narrative_text[:100]
            mo_feedback = await self._run_micro_oracle(narrative_text, mo_summary, ctx)

        # ── Trace ──
        from .utils import save_traces
        save_traces(beat_id)
        self._last_narrative = narrative_text
        self._last_ending_hook = str(composer_raw.get("ending_hook", "") or "")
        self._last_action_hints = list(composer_raw.get("action_hints", []) or [])

        # ── 写入本拍记忆（记忆系统启用时） ──
        if self._config.is_feature_enabled("memory_system") and not isinstance(world_state, dict):
            await self._write_beat_memories(
                world_state, plan, character_outputs, narrative_text,
                audit_result, cc_verdict if self._config.is_feature_enabled("continuity_check") else "",
                rr_results if self._config.is_feature_enabled("role_reflection") else [],
            )

        result_data = {
            "narrative_text": narrative_text,
            "action_hints": composer_raw.get("action_hints", []) or [],
            "ending_hook": composer_raw.get("ending_hook", "") or "",
            "music_mood": composer_raw.get("music_mood", "") or "",
            "choices": composer_raw.get("choices", []) or [],
            "state_patch": state_patch,
            "audit": audit_result,
            "micro_oracle": {
                "system_health": mo_feedback.get("system_health", ""),
                "suggestions": mo_feedback.get("suggestions", []),
                "one_line_feedback": mo_feedback.get("one_line_feedback", ""),
            } if mo_feedback else {},
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

    async def _run_director_best_of_3(self, ctx: dict) -> dict:
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
            d_input = {"scene_context": ctx}
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
        plot_result = await self._run_director_best_of_3(plot_ctx)
        plot_plan: dict = plot_result.get("raw", {}) or {}

        # ── Character-driven ──
        log_layer("L1", "Multi-View: 启动 character-driven Best-of-3")
        char_ctx = deepcopy(ctx)
        char_ctx["_director_mode"] = "character_driven"
        char_result = await self._run_director_best_of_3(char_ctx)
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

    async def _run_micro_oracle(self, narrative_text: str, summary_text: str, ctx: dict) -> dict:
        """运行 MicroOracle，返回包含 health/suggestions/feedback 的字典。"""
        agent = MicroOracleAgent()
        agent.configure(self._get_provider_for_tier("light"))

        mo_input = {"narrative_summary": summary_text, "scene_context": ctx}
        feedback = await agent.run(mo_input)

        feedback = feedback if isinstance(feedback, dict) else {}
        self._micro_oracle_buffer.append(feedback)
        if len(self._micro_oracle_buffer) > 10:
            self._micro_oracle_buffer.pop(0)

        self._next_beat_context["micro_feedback"] = str(feedback.get("one_line_feedback", ""))
        self._next_beat_context["micro_system_health"] = str(feedback.get("system_health", "healthy"))
        self._next_beat_context["micro_suggestions"] = list(feedback.get("suggestions", []) or [])

        if feedback.get("has_issue", False):
            severity = str(feedback.get("severity", "info"))
            if severity in ("alert", "warning"):
                log_warning("MicroOracle",
                            f"Beat {self._beat_count}: [{severity}] {feedback.get('one_line_feedback', '')}")

        return feedback

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

    def reload_config(self, yaml_dict: dict) -> None:
        """热重连：重新加载配置并重新初始化 providers"""
        self._config.reload(yaml_dict)
        self.request_reconnect()

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

    # ------------------------------------------------------------------
    # L1b: ContinuityChecker
    # ------------------------------------------------------------------

    async def _run_continuity_check(
        self, plan: dict, ctx: dict, player_action: str, ws_dict: dict,
    ) -> dict:
        """L1b: 运行连续叙事审计。"""
        cc = ContinuityChecker()
        cc.configure(self._get_provider_for_tier(
            self._config.get_str("continuity", "tier", "medium")))

        history_summary = ""
        history: list = ctx.get("recent_history", []) or []
        if history:
            history_summary = "；".join(
                str(e.get("summary", "")) for e in history[-5:]
            )

        # 提取角色状态摘要
        character_states = {}
        chars: list = ctx.get("characters", []) or []
        for c in chars:
            c = c if isinstance(c, dict) else {}
            cs = c.get("current_state", {}) or {}
            char_id = c.get("char_id", c.get("name", ""))
            character_states[char_id] = cs

        threads: list = ctx.get("active_threads", []) or []

        cc_input = {
            "player_action": player_action,
            "history_summary": history_summary,
            "character_states": character_states,
            "beat_plan": plan,
            "narrative_threads": threads,
        }

        return await cc.run(cc_input)

    # ------------------------------------------------------------------
    # L2R3: RoleReflector
    # ------------------------------------------------------------------

    async def _run_role_reflection(
        self, character_outputs: list, ws_dict: dict, plan: dict,
    ) -> dict:
        """L2R3: 运行角色过渡反思。"""
        rr = RoleReflector()
        rr.configure(self._get_provider_for_tier(
            self._config.get_str("reflection", "tier", "light")))

        # 提取角色上一拍状态
        previous_states = {}
        for co in character_outputs:
            co = co if isinstance(co, dict) else {}
            char_id = co.get("character_id", co.get("char_id", ""))
            cs = ws_dict.get("character_states", {}).get(char_id, {}) or {}
            previous_states[char_id] = cs

        rr_input = {
            "character_performances": character_outputs,
            "previous_states": previous_states,
            "beat_plan": plan,
        }

        return await rr.run(rr_input)

    async def _rerun_character_performance(
        self, char_id: str, ctx: dict, plan: dict,
        motivation_results: list, constraint: str = "",
    ) -> Optional[dict]:
        """L2R3 辅助：重新跑单个角色的 L2R2 表演。"""
        # 找到该角色的动机结果
        char_motivation = None
        for m in motivation_results:
            m = m if isinstance(m, dict) else {}
            mid = m.get("character_id", m.get("raw", {}) or {}).get("character_id", "")
            if mid == char_id:
                char_motivation = m.get("raw", {}) or {}
                break

        # 获取角色信息
        char_info = None
        chars: list = ctx.get("characters", []) or []
        for c in chars:
            c = c if isinstance(c, dict) else {}
            if c.get("char_id", "") == char_id:
                char_info = c
                break

        if not char_info:
            return None

        # 重新跑 DialogueWeaver + ActionDirector
        interaction_pairs: list = plan.get("interaction_pairs", []) or []
        interaction = None
        for pair in interaction_pairs:
            pair = pair if isinstance(pair, dict) else {}
            if char_id in pair.get("char_ids", []):
                interaction = pair
                break

        dialogue = DialogueWeaver()
        dialogue.configure(self._get_provider_for_tier("medium"))
        dw_input = {
            "character": char_info,
            "interaction_context": interaction or {},
            "beat_summary": str(plan.get("beat_summary", "")),
            "player_action": str((ctx.get("player", {}) or {}).get("action", "")),
            "scene_tone": str(plan.get("scene_tone", "平淡")),
            "continuity_constraint": constraint,
        }
        if char_motivation:
            dw_input["character"]["motivation_output"] = char_motivation
        dw_result = await dialogue.run(dw_input)

        action = ActionDirector()
        action.configure(self._get_provider_for_tier("light"))
        ad_input = {
            "character": char_info,
            "interaction_context": interaction or {},
            "scene_tone": str(plan.get("scene_tone", "平淡")),
            "player_action": str((ctx.get("player", {}) or {}).get("action", "")),
            "continuity_constraint": constraint,
        }
        ad_result = await action.run(ad_input)

        result = {}
        if dw_result.get("ok", False):
            result.update(dw_result.get("raw", {}))
        if ad_result.get("ok", False):
            result.setdefault("actions", []).extend(
                (ad_result.get("raw", {}) or {}).get("actions", []) or []
            )
        result["char_id"] = char_id
        result["character_id"] = char_id
        return result

    # ------------------------------------------------------------------
    # L3b: Emergence detection helpers
    # ------------------------------------------------------------------

    def _build_char_mgr_input(self, narrative_text: str, ws_dict: dict) -> dict:
        """构建 CharacterManager 的输入。"""
        return {
            "narrative_text": narrative_text,
            "canon_characters": ws_dict.get("canon_characters", {}) or {},
            "dynamic_npcs": ws_dict.get("dynamic_npcs", {}) or {},
            "pending_emergences": ws_dict.get("pending_emergences", {}) or {},
        }

    def _build_loc_mgr_input(self, narrative_text: str, ws_dict: dict) -> dict:
        """构建 LocationManager 的输入。"""
        return {
            "narrative_text": narrative_text,
            "canon_locations": ws_dict.get("canon_locations", {}) or {},
            "dynamic_locations": ws_dict.get("dynamic_locations", {}) or {},
            "pending_emergences": ws_dict.get("pending_emergences", {}) or {},
        }

    async def _process_emergences(
        self, world_state: "WorldState",
        char_mgr_result: dict, loc_mgr_result: dict,
    ) -> None:
        """处理涌现实体: 合并/累加/LLM判定/采纳。"""
        if isinstance(world_state, dict):
            return  # 兼容 dict 模式

        if not hasattr(world_state, "add_pending_emergence"):
            return

        threshold = self._config.get_int("emergence", "hit_threshold", 3)

        # 处理角色涌现
        char_detected: list = char_mgr_result.get("detected_emergences", []) or []
        for d in char_detected:
            d = d if isinstance(d, dict) else {}
            name = str(d.get("name", ""))
            if name:
                world_state.add_pending_emergence(
                    name=name,
                    entity_type="character",
                    mention=str(d.get("mention", "")),
                    tags=d.get("feature_tags", []) or [],
                )

        # 处理地点涌现
        loc_detected: list = loc_mgr_result.get("detected_emergences", []) or []
        for d in loc_detected:
            d = d if isinstance(d, dict) else {}
            name = str(d.get("name", ""))
            if name:
                world_state.add_pending_emergence(
                    name=name,
                    entity_type="location",
                    mention=str(d.get("mention", "")),
                    tags=d.get("feature_tags", []) or [],
                )

        # 处理 readiness 判定结果
        char_readiness: list = char_mgr_result.get("readiness_results", []) or []
        loc_readiness: list = loc_mgr_result.get("readiness_results", []) or []
        for r in char_readiness + loc_readiness:
            r = r if isinstance(r, dict) else {}
            name = str(r.get("name", ""))
            readiness = str(r.get("readiness", "ACCUMULATING"))
            profile = r.get("profile", None)

            if readiness == "READY" and profile and name:
                # 检查已经累积累积的 hit 数据
                pending = world_state.get_pending_emergence(name)
                if pending and pending.get("generated_profile") is None:
                    pending["generated_profile"] = profile
                    pending["readiness"] = "READY"
                # 采纳：移入 dynamic_npcs/locations
                promoted = world_state.promote_emergence(name)
                if promoted:
                    _log.info(f"涌现采纳: {name} ({pending.get('entity_type', '?')})")

    # ------------------------------------------------------------------
    # Memory system
    # ------------------------------------------------------------------

    async def _inject_memory_to_ctx(
        self, ctx: dict, ws_dict: dict, world_state: "WorldState",
    ) -> dict:
        """从 MemoryManager 检索记忆并注入到场景上下文。"""
        if isinstance(world_state, dict):
            return ctx

        current_beat = self._beat_count

        # 导演记忆
        director_mem = world_state.memory.retrieve_director(
            query=(ctx.get("player", {}) or {}).get("action", ""),
            top_k=self._config.get_int("memory", "top_k_director", 5),
            current_beat=current_beat,
        )
        if director_mem:
            ctx["director_memory"] = world_state.memory.get_memory_text(director_mem)

        # 角色记忆（注入到每个角色的 known_facts）
        characters: list = ctx.get("characters", []) or []
        for c in characters:
            c = c if isinstance(c, dict) else {}
            char_id = c.get("char_id", "")
            if not char_id:
                continue
            char_mem = world_state.memory.retrieve_character(
                char_id,
                query=(ctx.get("player", {}) or {}).get("action", ""),
                top_k=self._config.get_int("memory", "top_k_character", 3),
                current_beat=current_beat,
            )
            if char_mem:
                c["character_memory"] = world_state.memory.get_memory_text(char_mem, max_chars=300)

        return ctx

    async def _write_beat_memories(
        self, world_state: "WorldState", plan: dict,
        character_outputs: list, narrative_text: str,
        audit_result: dict, cc_verdict: str, rr_results: list,
    ) -> None:
        """每拍结束后，将本拍的决策/事件/状态变化写入记忆流。"""
        if isinstance(world_state, dict):
            return

        beat = self._beat_count
        mm = world_state.memory

        # 1. 导演决策记忆
        beat_summary = str(plan.get("beat_summary", "")) or ""
        narrative_mode = str(plan.get("narrative_mode", "")) or ""
        if beat_summary:
            mm.add_decision(
                "director", f"第{beat}拍: {beat_summary}",
                timestamp=beat, importance=5.0,
                tags=["narrative", narrative_mode] if narrative_mode else ["narrative"],
                source="L1 Director",
            )

        # 2. ContinuityChecker 结果
        if cc_verdict:
            if cc_verdict == "REJECTED":
                mm.add_decision(
                    "director", f"第{beat}拍导演提案被 ContinuityChecker 拒绝",
                    timestamp=beat, importance=7.0,
                    tags=["rejected", "continuity"],
                    source="ContinuityChecker",
                )
            elif cc_verdict == "NEEDS_TRANSITION":
                mm.add_decision(
                    "director", f"第{beat}拍需要过渡衔接",
                    timestamp=beat, importance=5.0,
                    tags=["transition", "continuity"],
                    source="ContinuityChecker",
                )

        # 3. 角色记忆: 状态变化 + 表演
        for co in character_outputs:
            co = co if isinstance(co, dict) else {}
            char_id = co.get("character_id", co.get("char_id", ""))
            if not char_id:
                continue

            # 表演摘要
            dialogs = co.get("dialogue", []) or []
            actions = co.get("actions", []) or []
            mood = co.get("mood", co.get("emotional_arc", "")) or ""
            parts = []
            if mood:
                parts.append(f"情绪: {mood}")
            if dialogs:
                d = dialogs[0] if isinstance(dialogs[0], dict) else {}
                parts.append(f"对白: {str(d.get('text', ''))[:60]}")
            if actions:
                a = actions[0] if isinstance(actions[0], dict) else {}
                parts.append(f"动作: {str(a.get('description', ''))[:60]}")
            if parts:
                mm.add_observation(
                    char_id, f"第{beat}拍: {'; '.join(parts)}",
                    timestamp=beat, importance=3.0,
                    tags=["performance", mood] if mood else ["performance"],
                    source="L2R2",
                )

        # 4. RoleReflector 结果
        for rr in rr_results:
            rr = rr if isinstance(rr, dict) else {}
            cid = rr.get("char_id", "")
            verdict = rr.get("verdict", "")
            if cid and verdict == "NEED_TRANSITION":
                mm.add_observation(
                    cid, f"第{beat}拍: 表演存在跳跃，添加了过渡衔接",
                    timestamp=beat, importance=5.0,
                    tags=["transition", "reflection"],
                    source="RoleReflector",
                )

        # 5. 世界观察记忆
        if narrative_text:
            mm.add_observation(
                "world", f"第{beat}拍: {narrative_text[:120]}...",
                timestamp=beat, importance=2.0,
                tags=["narrative"],
                source="SceneComposer",
            )

        # 6. Auditor 结果
        audit_data: dict = audit_result.get("raw", {}) or {}
        if str(audit_data.get("verdict", "PASS")) not in ("PASS",):
            mm.add_observation(
                "world", f"第{beat}拍审计: {len(audit_data.get('issues', []) or [])} 个问题",
                timestamp=beat, importance=4.0,
                tags=["audit", "warning"],
                source="ConsistencyAuditor",
            )

        # 7. 检查是否需要 Reflection（导演反思）
        if mm.should_reflect("director"):
            from .agents import MicroOracleAgent
            from .memory import MemoryEntry
            oracle = MicroOracleAgent()
            oracle.configure(self._get_provider_for_tier("light"))
            recent_mem = mm.director_memory[-10:] if mm.director_memory else []
            mem_text = mm.get_memory_text(recent_mem, max_chars=800)

            reflection_input = {
                "context": MananaSchema.build_reflection_context(
                    beat_count=self._beat_count,
                    memory_text=mem_text,
                    agent_type="director",
                )
            }
            reflection_result = await oracle.run(reflection_input)
            if reflection_result.get("ok", False):
                reflection_text = str(
                    (reflection_result.get("raw", {}) or {}).get("reflection", "")
                )
                if reflection_text:
                    mm.add_memory(MemoryEntry(
                        agent_id="director",
                        content=f"反思: {reflection_text}",
                        timestamp=beat,
                        importance=8.0,
                        memory_type="reflection",
                        tags=["reflection"],
                        source="MemoryReflection",
                    ))
                    _log.info(f"导演反思: {reflection_text[:80]}")
            mm.mark_reflected("director")

        # 8. 周期性压缩（每隔 compact_interval 拍触发一次）
        compact_interval = self._config.get_int("memory", "compact_interval", 10)
        if compact_interval > 0 and beat % compact_interval == 0:
            removed = mm.compact_if_needed(current_beat=beat)
            if removed > 0:
                _log.info(f"记忆压缩: 共移除{removed}条旧低重要度记忆")
