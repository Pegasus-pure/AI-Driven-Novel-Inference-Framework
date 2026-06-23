"""MaNA v4 Pipeline — Main Orchestrator.

The central orchestrator that executes the complete 5-layer narrative pipeline:

  L0: ContextBuilder — scene context assembly
  L1: SceneDirector — beat planning (v4: Best-of-N, Multi-View)
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
import random
from copy import deepcopy
from typing import Any, Callable, Optional

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
    SoulChoiceGenerator,
    StateExtractor,
    ThreadManager,
)
from .config import MananaConfig
from .pipeline_context import ContextBuilder
from .pipeline_helpers import replace_ids_with_names, split_narrative
from .pipeline_state import InteractionPair, apply_state_patch
from .providers import BaseProvider, ProviderFactory
from .reward_tracker import RewardTracker
from .prompt_optimizer import PromptOptimizer
from .schema import MananaSchema
from .utils import (
    get_logger,
    log_error,
    log_layer,
    log_warning,
    set_current_beat,
)
from server.config.exceptions import PipelineError, ProviderError

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
        self._reward_tracker: RewardTracker | None = None
        self._prompt_optimizer: PromptOptimizer | None = None

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
            raise ProviderError(f"All provider tiers failed to initialize: {failed_tiers}")
        elif failed_tiers:
            _log.warning("Some provider tiers failed to initialize: %s", failed_tiers)

        # 初始化 RewardTracker
        self._reward_tracker = RewardTracker(self._config._yaml_dict)

        # 初始化 PromptOptimizer（阶段三，由功能开关控制）
        if self._config.is_feature_enabled("prompt_optimization"):
            self._prompt_optimizer = PromptOptimizer(self._config._yaml_dict)

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
        soul_choice: Optional[dict] = None,
        needs_soul_choices: bool = True,
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
        # ── 起始 ──
        beat_id = self._start_beat()
        self._needs_soul_choices = needs_soul_choices

        # ── L0: 上下文 ──
        ctx, ws_dict = await self._build_beat_context(
            player_action, world_state, beat_id, progress_cb, soul_choice,
        )

        # ── L1: Director + 模式追踪 + 复杂度 ──
        plan = await self._run_l1_director(ctx, progress_cb)

        log_layer("L1", f"SceneDirector 完成 — 模式: {plan.get('narrative_mode', '?')}")
        self._update_mode_tracking(plan)
        self._apply_complexity_scoring(ctx, plan)

        # ── L1b: 连续性审计 ──
        cc_verdict, plan = await self._run_l1b_continuity_check(
            plan, ctx, player_action, ws_dict, progress_cb,
        )

        # ── L2: 动机 + 对话/动作 + 反思 ──
        motivation_results = await self._run_motivations_parallel(ctx, plan, progress_cb)
        character_outputs = await self._run_dialogue_actions_parallel(ctx, plan, motivation_results, progress_cb)
        rr_results = await self._run_l2r3_role_reflection(
            character_outputs, ws_dict, plan, progress_cb,
            ctx=ctx, motivation_results=motivation_results,
        )

        # ── L3: Composer ──
        narrative_text, composer_raw = await self._run_l3_composer(
            ctx, character_outputs, plan, progress_cb,
        )

        # ── L3b ∥ L4a + L4b: 并行审计 + ThreadManager ──
        audit_result, state_patch_result, thread_updates = await self._run_l3b_l4a_parallel(
            narrative_text, plan, ctx, character_outputs, ws_dict, world_state, beat_id, progress_cb,
        )

        # ── Post-beat ──
        result_data = await self._finalize_beat(
            world_state, ws_dict, plan, character_outputs,
            narrative_text, composer_raw, audit_result, state_patch_result,
            thread_updates, ctx, beat_id, progress_cb, cc_verdict, rr_results,
        )

        return await self._end_beat(result_data, beat_id)

    # ------------------------------------------------------------------
    # Post-beat finalization
    # ------------------------------------------------------------------

    async def _build_soul_choices(self, ctx: dict, narrative_text: str, plan: dict) -> dict:
        """调用 SoulChoiceGenerator (light) 生成本我/贴合行动选项。

        同时保留 Arbiter 的决策元数据。
        """
        arbiter_decision = ctx.get("soul", {}).get("decision", {}) or {}
        # 从 ctx 提取主角信息
        chars = ctx.get("characters", []) or []
        protagonist_name = "主角"
        proto_personality = ""
        for c in chars:
            if not c.get("is_dynamic", False):
                protagonist_name = str(c.get("name", "主角"))
                proto_personality = str(c.get("personality", ""))
                break

        generator = SoulChoiceGenerator()
        provider = self._create_independent_provider("light")
        if not provider:
            return arbiter_decision
        try:
            generator.configure(provider)
            input_data = {
                "narrative_text": narrative_text,
                "protagonist_name": protagonist_name,
                "protagonist_personality": proto_personality,
                "scene_summary": str(plan.get("beat_summary", "")),
                "action_hints": plan.get("action_hints", []) or [],
            }
            result = await generator.run(input_data)
            if result.get("ok", False):
                parsed = generator._parse_json_response(result)
                choices = parsed.get("data", {}) or {}
                return {
                    "action_type": arbiter_decision.get("action_type", ""),
                    "dissonance_impact": arbiter_decision.get("dissonance_impact", 0),
                    "dominant_soul": arbiter_decision.get("dominant_soul", ""),
                    "authentic": choices.get("authentic", []) or [],
                    "conforming": choices.get("conforming", []) or [],
                }
        finally:
            await provider.cleanup()
        return arbiter_decision

    async def _finalize_beat(
        self,
        world_state: "WorldState",
        ws_dict: dict,
        plan: dict,
        character_outputs: list,
        narrative_text: str,
        composer_raw: dict,
        audit_result: dict,
        state_patch_result: dict,
        thread_updates: list,
        ctx: dict,
        beat_id: str,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
        cc_verdict: str = "",
        rr_results: list = None,
    ) -> dict:
        """Post-beat: 应用状态变更 + 记录历史 + Oracle + 组装结果 + Reward。

        从 run_beat 最后的 ~80 行内联代码提取。
        """
        rr_results = rr_results or []

        # ── Apply state changes ──
        state_patch: dict = state_patch_result.get("raw", {}) or {}
        if state_patch:
            apply_state_patch(world_state, state_patch)

        # ── Apply thread changes ──
        world_state.apply_thread_updates(thread_updates)

        # ── Narrative history + memory ──
        summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
        if not summary:
            summary = narrative_text[:100]
        world_state.add_narrative_event(summary, beat_id)
        mem_entry = str(state_patch.get("scene_memory_entry", narrative_text[:60]))
        if mem_entry:
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

        # ── Trace ──（保留框架，实际由 Godot 版使用时接入）
        self._last_narrative = narrative_text
        self._last_ending_hook = str(composer_raw.get("ending_hook", "") or "")
        self._last_action_hints = list(composer_raw.get("action_hints", []) or [])

        # ── 写入本拍记忆 ──
        if self._config.is_feature_enabled("memory_system"):
            await self._write_beat_memories(
                world_state, plan, character_outputs, narrative_text,
                audit_result, cc_verdict, rr_results,
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
            # ★ 灵魂附生数据 — 调用 SoulChoiceGenerator 生成上下文感知选项
            "soul_decision": (
                await self._build_soul_choices(ctx, narrative_text, plan)
                if getattr(self, '_needs_soul_choices', True)
                else ctx.get("soul", {}).get("decision", {})
            ),
            "soul_inner_voice": ctx.get("soul", {}).get("inner_voice", {}),
        }

        # ── Reward computation (阶段一) ──
        if self._reward_tracker:
            reward_record = self._reward_tracker.compute_and_log(result_data, beat_id, self._beat_count)
            result_data["reward"] = reward_record.get("reward", 0.0)
            result_data["reward_components"] = reward_record.get("components", {})
        else:
            result_data["reward"] = 0.0

        # ── Prompt optimization trigger (阶段三) ──
        if self._prompt_optimizer:
            self._prompt_optimizer.maybe_run(self._beat_count)

        return result_data

    # ------------------------------------------------------------------
    # Beat lifecycle
    # ------------------------------------------------------------------

    def _start_beat(self) -> str:
        """初始化 beat 计数器、ID 和日志。"""
        self._beat_count += 1
        beat_id = f"beat_{self._beat_count:03d}"
        set_current_beat(beat_id)
        _log.info("=== Beat %s START ===", beat_id)
        return beat_id

    async def _end_beat(self, result_data: dict, beat_id: str) -> dict:
        """收尾：日志、重连检查、返回结果。"""
        _log.info("=== Beat %s COMPLETE ===", beat_id)
        if self._pending_reconnect:
            await self._do_reconnect()
        return result_data

    def _apply_complexity_scoring(self, ctx: dict, plan: dict) -> None:
        """如果 dynamic_tier 启用，计算复杂度并应用层级覆盖。"""
        if self._config.is_feature_enabled("dynamic_tier"):
            complexity = self._compute_complexity(ctx, plan)
            log_layer("L1", f"复杂度评分: {complexity:.2f}")
            self._apply_tier_overrides(complexity)

    # ------------------------------------------------------------------
    # Mode Tracking
    # ------------------------------------------------------------------

    def _update_mode_tracking(self, plan: dict) -> None:
        """更新叙事模式追踪（Director 可能主动切换模式）。"""
        chosen_mode = str(plan.get("narrative_mode", self._current_narrative_mode))
        if chosen_mode and chosen_mode in self._NARRATIVE_MODES:
            if chosen_mode == self._current_narrative_mode:
                self._mode_duration += 1
            else:
                self._current_narrative_mode = chosen_mode
                self._mode_duration = 1
        else:
            self._mode_duration += 1

    # ------------------------------------------------------------------
    # L3: SceneComposer
    # ------------------------------------------------------------------

    async def _run_l3_composer(
        self,
        ctx: dict,
        character_outputs: list,
        plan: dict,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> tuple[str, dict]:
        """L3: SceneComposer — 带/不带精炼循环。

        Returns:
            (narrative_text, composer_raw) 成功时。
        Raises:
            PipelineError: Composer 失败时。
        """
        if self._config.is_feature_enabled("refinement"):
            log_layer("L3", "SceneComposer 启动 (精炼循环)")
            if progress_cb:
                await progress_cb("composer", "编剧正在合成本章...")
            result = await self._run_composer_with_refinement(ctx, character_outputs, plan)
        else:
            log_layer("L3", "SceneComposer 启动")
            if progress_cb:
                await progress_cb("composer", "编剧正在合成本章...")
            composer = SceneComposer()
            composer.configure(self._get_provider_for_tier("strong"))
            if self._prompt_optimizer:
                composer._optimization_hints = self._prompt_optimizer.get_latest_hints()
            else:
                composer._optimization_hints = ""
            composer_input = self._build_composer_input(plan, character_outputs, ctx)
            result = await composer.run(composer_input)

        if not result.get("ok", False):
            err = str(result.get("error", "Composer failed"))
            log_error("SceneComposer", err)
            raise PipelineError(f"L3 composer failed: {err}")

        raw_content: str = result.get("content", "") or ""
        composer_raw: dict = result.get("raw", {}) or {}
        # 剥离叙事正文中的 JSON 后缀
        narrative_text = SceneComposer._strip_json_suffix(SceneComposer(), raw_content)
        log_layer("L3", f"SceneComposer 完成 ({len(narrative_text)} 字符)")
        return narrative_text, composer_raw

    # ------------------------------------------------------------------
    # L3b ∥ L4a: Auditor + Extractor + CharMgr + LocMgr + L4b ThreadManager
    # ------------------------------------------------------------------

    async def _run_l3b_l4a_parallel(
        self,
        narrative_text: str,
        plan: dict,
        ctx: dict,
        character_outputs: list,
        ws_dict: dict,
        world_state: "WorldState",
        beat_id: str,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> tuple[dict, dict, list]:
        """L3b∥L4a: 四路并行（Auditor + Extractor + CharMgr + LocMgr）+ L4b ThreadManager。

        Returns:
            (audit_result, state_patch_result, thread_updates)
        """
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

        if self._config.is_feature_enabled("emergence_system"):
            character_mgr = CharacterManager()
            character_mgr.configure(self._get_provider_for_tier("light"))
            location_mgr = LocationManager()
            location_mgr.configure(self._get_provider_for_tier("light"))
            character_mgr_input = self._build_character_mgr_input(narrative_text, ws_dict)
            location_mgr_input = self._build_location_mgr_input(narrative_text, ws_dict)
            tasks.append(character_mgr.run(character_mgr_input))
            tasks.append(location_mgr.run(location_mgr_input))

        results = await asyncio.gather(*tasks)

        audit_result = results[0]
        state_patch_result = results[1]

        # 涌现实体
        if self._config.is_feature_enabled("emergence_system") and len(results) >= 4:
            await self._process_emergences(world_state, results[2], results[3])

        log_layer("L3b∥L4a", "Auditor / Extractor / CharMgr / LocMgr 完成")

        # Audit FAIL 日志
        audit_data: dict = audit_result.get("raw", {}) or {}
        if str(audit_data.get("verdict", "PASS")) not in ("PASS",):
            issues: list = audit_data.get("issues", []) or []
            log_warning("Auditor", f"Beat {beat_id} audit FAIL: {len(issues)} issues")

        # L4b: ThreadManager
        log_layer("L4b", "ThreadManager 启动")
        if progress_cb:
            await progress_cb("thread_manager", "线索管理员正在整理...")
        thread_updates = await self._run_thread_manager(
            narrative_text, str(plan.get("beat_summary", "")), plan, ws_dict,
        )
        log_layer("L4b", "ThreadManager 完成")

        return audit_result, state_patch_result, thread_updates

    # ------------------------------------------------------------------
    # L0: Context Building
    # ------------------------------------------------------------------

    async def _build_beat_context(
        self,
        player_action: str,
        world_state: "WorldState",
        beat_id: str,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
        soul_choice: Optional[dict] = None,
    ) -> tuple[dict, dict]:
        """L0: 构建 beat 上下文 — ContextBuilder + 记忆注入 + 冲突种子 + 模式轮换 + 增强。

        Args:
            player_action: 玩家输入
            world_state: WorldState 对象
            beat_id: 当前 beat 编号
            progress_cb: 可选的进度回调

        Returns:
            (ctx, ws_dict)
        """
        log_layer("L0", "ContextBuilder 启动")
        if progress_cb:
            await progress_cb("context_builder", "正在构建场景上下文...")
        ws_dict = world_state.to_dict()
        # ★ 为无地点角色分配临时地点（LLM light），增加角色多样性
        await self._assign_temp_locations(ws_dict)
        ctx = ContextBuilder.build(player_action, ws_dict, beat_id=beat_id)

        # ★ 灵魂附生模式：注入 soul 数据到上下文（唯一模式）
        ctx["game_mode"] = "soul_possession"
        if hasattr(world_state, 'soul_possession') and world_state.soul_possession is not None:
            from .soul.arbiter import SoulDecisionArbiter
            from .soul.inner_voice import InnerVoiceGenerator

            soul_state = world_state.soul_possession
            player_override = soul_choice

            decision = SoulDecisionArbiter(soul_state).decide(
                scene_context=ctx,
                decision_mode="auto",
                player_override=player_override,
            )
            inner_voice = InnerVoiceGenerator(soul_state).generate(ctx, decision)

            ctx["soul"] = {
                "decision": decision,
                "inner_voice": inner_voice,
            }

            # ★ 确保附身主角始终在场（Directer 必须能看到被附身角色）
            protagonist_id = str((soul_state.canon_soul or {}).get("id", ""))
            if protagonist_id:
                existing_ids = {c.get("char_id", "") for c in ctx.get("characters", [])}
                if protagonist_id not in existing_ids:
                    # 从 ws_dict 中找到该角色并注入
                    for char_id, cs in (ws_dict.get("characters_state", {}) or {}).items():
                        if char_id == protagonist_id:
                            canon_chars: list = (ws_dict.get("canon", {}) or {}).get("characters", []) or []
                            canon_lookup = {}
                            for c in canon_chars:
                                c = c if isinstance(c, dict) else {}
                                cid = str(c.get("id", ""))
                                if cid:
                                    canon_lookup[cid] = c
                            prot_entry = ContextBuilder._build_single_character(
                                char_id, cs, canon_lookup, ws_dict,
                                str(ws_dict.get("player_location", "")),
                            )
                            if prot_entry:
                                ctx.setdefault("characters", []).insert(0, prot_entry)
                            break

        # ── 注入记忆到场景上下文（记忆系统启用时） ──
        if self._config.is_feature_enabled("memory_system"):
            ctx = await self._inject_memory_to_ctx(ctx, ws_dict, world_state)
            # 注入 LLM 工具定义到场景上下文（供 Director 使用）
            ctx["llm_tools_prompt"] = self._get_llm_tools_prompt()

        # ── Conflict seed injection（T02: 注入 Canon 冲突种子） ──
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

        # ── v4: Context augmentation (semantic_selection + vector_memory) ──
        if self._config.is_feature_enabled("semantic_selection") or \
           self._config.get_vector_memory_config().get("enable_vector_memory", False):
            ctx = await self._augment_context(ctx)

        # ── 注入上拍结尾预告到场景上下文 ──
        if self._last_ending_hook:
            ctx["prev_ending_hook"] = self._last_ending_hook
            ctx["prev_action_hints"] = list(self._last_action_hints)

        return ctx, ws_dict

    async def _assign_temp_locations(self, ws_dict: dict) -> None:
        """为无地点角色用 LLM (light) 分配临时地点，写入 ws_dict。

        仅修改 ws_dict["characters_state"] 中 location 为空/未知的角色。
        临时值不持久化，仅影响本拍的角色入选。
        """
        cs = ws_dict.get("characters_state", {}) or {}
        unplaced = {}
        for cid, state in cs.items():
            state = state if isinstance(state, dict) else {}
            loc = str(state.get("location", "")).strip()
            if loc in ("", "未知"):
                unplaced[cid] = state

        if not unplaced:
            return

        # 收集已知地点列表
        all_locs = set()
        for state in cs.values():
            state = state if isinstance(state, dict) else {}
            loc = str(state.get("location", "")).strip()
            if loc and loc not in ("", "未知"):
                all_locs.add(loc)
        canon_locs: list = (ws_dict.get("canon", {}) or {}).get("locations", []) or []
        for l in canon_locs:
            if isinstance(l, dict):
                name = str(l.get("name", "")).strip()
                if name:
                    all_locs.add(name)
        if not all_locs:
            return

        # 用 light LLM 分配（简单 prompt）
        provider = self._create_independent_provider("light")
        if not provider:
            return
        try:
            char_list = "\n".join(
                f"- {cid}: 角色名={state.get('name', cid)}, 角色定位={state.get('role', '未知')}"
                for cid, state in unplaced.items()
            )
            loc_list = ", ".join(sorted(all_locs)[:10])
            prompt = (
                f"以下角色尚未分配地点，请根据角色信息合理分配到已知地点中。\n\n"
                f"可选地点: {loc_list}\n\n"
                f"{char_list}\n\n"
                f"输出一个 JSON 对象，key 为角色ID，value 为地点名。只输出 JSON，不要其他内容。"
            )
            import json
            resp = await provider.chat(
                "你是角色调度助手，只输出 JSON。",
                prompt,
                {"json_mode": True, "temperature": 0.3},
            )
            raw = (resp.get("content", "") or "").strip()
            # 尝试提取 JSON
            if "{" in raw:
                raw = raw[raw.find("{"):raw.rfind("}") + 1]
            assignments = json.loads(raw) if raw else {}
            for cid, loc in (assignments or {}).items():
                loc = str(loc).strip()
                if cid in unplaced and loc in all_locs:
                    cs[cid]["location"] = loc
        except Exception:
            pass  # 失败不影响管线
        finally:
            await provider.cleanup()

    # ------------------------------------------------------------------
    # L2R1: Motivation parallel dispatch
    # ------------------------------------------------------------------

    async def _run_motivations_parallel(
        self, ctx: dict, plan: dict,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> list[dict]:
        char_ids: list = plan.get("featured_characters", []) or []
        if not char_ids:
            return []
        log_layer("L2R1", f"MotivationEngine 启动 ({len(char_ids)} 角色)")
        if progress_cb:
            await progress_cb("motivation", "演员正在酝酿动机...")

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

        log_layer("L2R1", "MotivationEngine 并行启动...")
        tasks = [run_one(cid) for cid in char_ids]
        results = await asyncio.gather(*tasks)
        log_layer("L2R1", f"MotivationEngine 完成 ({len(results)} 结果)")
        return results

    # ------------------------------------------------------------------
    # L2R2: Dialogue + Action parallel dispatch
    # ------------------------------------------------------------------

    async def _run_dialogue_actions_parallel(
        self, ctx: dict, plan: dict, motivations: list[dict],
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> list[dict]:
        da_char_ids: list = plan.get("featured_characters", []) or []
        if not da_char_ids:
            return []
        log_layer("L2R2", "DialogueWeaver/ActionDirector 启动")
        if progress_cb:
            await progress_cb("dialogue", "演员正在对戏...")

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

        log_layer("L2R2", f"DialogueWeaver/ActionDirector 完成 ({len(da_results)} 角色输出)")
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
    # L1: Director dispatch
    # ------------------------------------------------------------------

    async def _run_l1_director(
        self,
        ctx: dict,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> dict:
        """L1: 根据功能开关选择 Director 模式。

        Returns:
            有效 plan dict。
        Raises:
            PipelineError: 所有 Director 模式都失败时。
        """
        if self._config.is_feature_enabled("multi_view") and self._is_director_best_of_n_enabled():
            log_layer("L1", "SceneDirector 启动 (multi_view + best_of_n)")
            if progress_cb:
                await progress_cb("scene_director", "导演正在编排剧情...")
            plan = await self._run_director_multi_view(ctx)
            if not plan:
                raise PipelineError("Director (multi_view) failed: empty plan")
            return plan

        if self._is_director_best_of_n_enabled():
            log_layer("L1", "SceneDirector 启动 (best_of_n)")
            if progress_cb:
                await progress_cb("scene_director", "导演正在编排剧情...")
            result = await self._run_director_best_of_n(ctx)
            plan = result.get("raw", {}) or {}
            if not plan:
                raise PipelineError(f"Director (best_of_n) failed: {result.get('error', 'empty plan')}")
            return plan

        log_layer("L1", "SceneDirector 启动")
        if progress_cb:
            await progress_cb("scene_director", "导演正在编排剧情...")
        director = SceneDirector()
        director.configure(self._get_provider_for_tier("strong"))
        result = await director.run({"scene_context": ctx})
        if not result.get("ok", False):
            raise PipelineError(f"Director failed: {result.get('error', 'unknown')}")
        return result.get("raw", {}) or {}

    # ------------------------------------------------------------------
    # v4: Director Best-of-N
    # ------------------------------------------------------------------

    def _is_director_best_of_n_enabled(self) -> bool:
        """Check if director Best-of-N is enabled."""
        dbon = self._config._cfg_dict.get("director_best_of_n", {}) or {}
        return dbon.get("enabled", "true") == "true"

    async def _run_director_best_of_n(self, ctx: dict) -> dict:
        bon_config = self._config.get_director_best_of_n_config()
        sample_count = bon_config.get("sample_count", 3)
        temps = bon_config.get("temperatures", [0.4, 0.6, 0.8])

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
            log_error("SceneDirector", "Best-of-N: all directors failed")
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

        log_layer("L1", f"Best-of-N 选中: total={best_total} (from {len(plans)} candidates)")
        return {"ok": True, "raw": best_plan}

    # ------------------------------------------------------------------
    # v4: Multi-View Director
    # ------------------------------------------------------------------

    async def _run_director_multi_view(self, ctx: dict) -> dict:
        # ── Plot-driven ──
        log_layer("L1", "Multi-View: 启动 plot-driven Best-of-N")
        plot_ctx = deepcopy(ctx)
        plot_ctx["_director_mode"] = "plot_driven"
        plot_result = await self._run_director_best_of_n(plot_ctx)
        plot_plan: dict = plot_result.get("raw", {}) or {}

        # ── Character-driven ──
        log_layer("L1", "Multi-View: 启动 character-driven Best-of-N")
        char_ctx = deepcopy(ctx)
        char_ctx["_director_mode"] = "character_driven"
        char_result = await self._run_director_best_of_n(char_ctx)
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

        # ── Composer Best-of-N (阶段二) ──
        composer_bon_cfg = (self._config._yaml_dict or {}).get("composer", {}).get("best_of_n", {})
        composer_bon_enabled: bool = composer_bon_cfg.get("enabled", False)
        composer_bon_count: int = int(composer_bon_cfg.get("sample_count", 3))
        composer_bon_temps: list[float] = [float(t) for t in composer_bon_cfg.get("temperatures", [0.5, 0.7, 0.9])]

        if composer_bon_enabled and composer_bon_count > 1:
            log_layer("L3", f"Composer Best-of-N: 生成 {composer_bon_count} 个候选叙事")
            candidates: list[dict] = []

            for i in range(composer_bon_count):
                temp = composer_bon_temps[i % len(composer_bon_temps)]
                prov = self._create_independent_provider("strong")
                if not prov:
                    continue
                c = SceneComposer()
                c.configure(prov)
                c._optimization_hints = (
                    self._prompt_optimizer.get_latest_hints() if self._prompt_optimizer else ""
                )
                c._current_temperature = temp  # 注入温度
                inp = self._build_composer_input(plan, character_outputs, ctx)
                r = await c.run(inp)
                await prov.cleanup()
                if not r.get("ok", False):
                    continue
                txt = r.get("content", "") or ""
                # 快速 Auditor 打分
                aud = ConsistencyAuditor()
                aud.configure(self._get_provider_for_tier("medium"))
                aud_inp = self._build_auditor_input(txt, plan, ctx)
                aud_res = await aud.run(aud_inp)
                aud_data = aud_res.get("raw", {}) or {}
                quality = float(
                    (aud_data.get("overall_quality") or {}).get("character_consistency", 0.5)
                    if isinstance(aud_data.get("overall_quality"), dict) else 0.5
                )
                candidates.append({"result": r, "text": txt, "quality": quality, "audit": aud_data})

            if candidates:
                # 用 quality 分数选最优（简易 reward）
                best = candidates[0]
                best_score = best["quality"] + (
                    0.1 if str(best["audit"].get("verdict", "PASS")) == "PASS" else 0.0
                )
                for c in candidates:
                    v = str(c["audit"].get("verdict", "PASS"))
                    score = c["quality"] + (0.1 if v == "PASS" else 0.0)
                    if score > best_score:
                        best_score = score
                        best = c
                log_layer("L3", f"Composer Best-of-N: 选中 score={best_score:.4f}")
                result = best["result"]
                narrative_text = best["text"]
                audit_data = best["audit"]
                verdict = str(audit_data.get("verdict", "PASS"))
                # 直接进入后续流程（跳过第一轮 Composer+Auditor）
                if verdict == "PASS":
                    log_layer("L3", "精炼循环: PASS — 无需精炼")
                    return result
                # 否则进入 refinement 循环
                # WARNING: one round of refinement
                if verdict == "WARNING":
                    log_layer("L3", "精炼循环: WARNING — 微调1轮")
                    composer = SceneComposer()
                    composer.configure(self._get_provider_for_tier("strong"))
                    if self._prompt_optimizer:
                        composer._optimization_hints = self._prompt_optimizer.get_latest_hints()
                    for _ in range(max_warning_refine):
                        rh = audit_data.get("refinement_hints", []) or []
                        if not rh:
                            rh = audit_data.get("issues", []) or []
                        refine_input = self._build_composer_input(plan, character_outputs, ctx)
                        refine_input["refinement_hints"] = rh
                        refine_input["mode"] = "refine"
                        r2 = await composer.run(refine_input)
                        if r2.get("ok", False):
                            return r2
                    return result
                # FAIL: 进入重写循环
                log_layer("L3", f"精炼循环: FAIL — 重写最多{max_fail_rewrite}轮")
                initial_quality = best["quality"]
                rewrite_candidates: list[dict] = [{"result": result, "quality": initial_quality}]
                auditor = ConsistencyAuditor()
                auditor.configure(self._get_provider_for_tier("medium"))
                audit_data_ref = audit_data
                for _ in range(max_fail_rewrite):
                    rh = audit_data_ref.get("refinement_hints", []) or []
                    if not rh:
                        rh = audit_data_ref.get("issues", []) or []
                    rewrite_input = self._build_composer_input(plan, character_outputs, ctx)
                    rewrite_input["refinement_hints"] = rh
                    rewrite_input["mode"] = "rewrite"
                    rr = await composer.run(rewrite_input)
                    if not rr.get("ok", False):
                        continue
                    rt = rr.get("content", "") or ""
                    rai = self._build_auditor_input(rt, plan, ctx)
                    rar = await auditor.run(rai)
                    rad = rar.get("raw", {}) or {}
                    rv = str(rad.get("verdict", "FAIL"))
                    oq = rad.get("overall_quality", {})
                    rq = float(oq.get("character_consistency", 0.5) if isinstance(oq, dict) else 0.5)
                    rewrite_candidates.append({"result": rr, "quality": rq})
                    if rv == "PASS":
                        return rr
                    audit_data_ref = rad
                picked = rewrite_candidates[0]["result"]
                picked_quality = float(rewrite_candidates[0]["quality"])
                for rc in rewrite_candidates:
                    q = float(rc["quality"])
                    if q > picked_quality:
                        picked_quality = q
                        picked = rc["result"]
                log_layer("L3", f"精炼循环: 从{len(rewrite_candidates)}个候选中选取最优 (quality={picked_quality:.2f})")
                return picked

        # ── 原有逻辑（Best-of-N 未开启）──
        # Round 1: Composer → Auditor
        composer = SceneComposer()
        composer.configure(self._get_provider_for_tier("strong"))
        # 注入优化提示（阶段三）
        if self._prompt_optimizer:
            composer._optimization_hints = self._prompt_optimizer.get_latest_hints()
        else:
            composer._optimization_hints = ""
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
    # L1b: ContinuityChecker dispatch (with retry loop)
    # ------------------------------------------------------------------

    async def _run_l1b_continuity_check(
        self,
        plan: dict,
        ctx: dict,
        player_action: str,
        ws_dict: dict,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
    ) -> tuple[str, dict]:
        """L1b: 运行 ContinuityChecker + 打回重做循环。

        Returns:
            (cc_verdict, plan) — plan 可能在重做后被更新。
        """
        cc_verdict = "APPROVED"
        if not self._config.is_feature_enabled("continuity_check"):
            return cc_verdict, plan

        log_layer("L1b", "ContinuityChecker 启动")
        if progress_cb:
            await progress_cb("continuity_checker", "审计叙事连贯性...")
        cc_result = await self._run_continuity_check(plan, ctx, player_action, ws_dict)
        cc_verdict = str(cc_result.get("verdict", "APPROVED"))

        cc_retry = 0
        while cc_verdict == "REJECTED" and cc_retry < self._config.get_continuity_max_rewrite():
            cc_retry += 1
            _log.info(f"L1b 打回重做 (第{cc_retry}次)...")
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
            log_warning("ContinuityChecker", "L1b 超过重做上限，强制通过")
            cc_verdict = "APPROVED"

        log_layer("L1b", f"ContinuityChecker 完成 — {cc_verdict}")
        return cc_verdict, plan

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
    # L2R3: RoleReflector dispatch (with transition + rewrite loops)
    # ------------------------------------------------------------------

    async def _run_l2r3_role_reflection(
        self,
        character_outputs: list,
        ws_dict: dict,
        plan: dict,
        progress_cb: Optional[Callable[[str, str], Any]] = None,
        ctx: dict = None,
        motivation_results: list = None,
    ) -> list:
        """L2R3: 运行 RoleReflector + 处理 NEED_TRANSITION + NEED_REWRITE 循环。

        Args:
            character_outputs: list[dict]，会被就地修改（插入过渡对话/动作）。

        Returns:
            rr_results: list[dict] 反思结果
        """
        if not self._config.is_feature_enabled("role_reflection"):
            return []

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
                            if not isinstance(co.get("dialogue"), list):
                                co["dialogue"] = []
                            co["dialogue"].append({
                                "text": transition_dialogue,
                                "tone": "过渡",
                                "target": "none",
                                "subtext": "过渡衔接",
                            })
                        if transition_action:
                            if not isinstance(co.get("actions"), list):
                                co["actions"] = []
                            co["actions"].append({
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
            character_outputs[:] = new_outputs  # 就地替换

            # 重新跑 RoleReflector
            rr_result = await self._run_role_reflection(character_outputs, ws_dict, plan)
            rr_results = rr_result.get("results", []) or []
            rewrite_chars = [r.get("char_id", "") for r in rr_results
                             if r.get("verdict") == "NEED_REWRITE"]

        if rewrite_chars:
            log_warning("RoleReflector", f"L2R3 超过重做上限，遗留: {rewrite_chars}")

        log_layer("L2R3", f"RoleReflector 完成 ({len(rr_results)} 角色)")
        return rr_results

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

    def _build_character_mgr_input(self, narrative_text: str, ws_dict: dict) -> dict:
        """构建 CharacterManager 的输入。"""
        return {
            "narrative_text": narrative_text,
            "canon_characters": ws_dict.get("canon_characters", {}) or {},
            "dynamic_npcs": ws_dict.get("dynamic_npcs", {}) or {},
            "pending_emergences": ws_dict.get("pending_emergences", {}) or {},
        }

    def _build_location_mgr_input(self, narrative_text: str, ws_dict: dict) -> dict:
        """构建 LocationManager 的输入。"""
        return {
            "narrative_text": narrative_text,
            "canon_locations": ws_dict.get("canon_locations", {}) or {},
            "dynamic_locations": ws_dict.get("dynamic_locations", {}) or {},
            "pending_emergences": ws_dict.get("pending_emergences", {}) or {},
        }

    async def _process_emergences(
        self, world_state: "WorldState",
        character_mgr_result: dict, location_mgr_result: dict,
    ) -> None:
        """处理涌现实体: 合并/累加/LLM判定/采纳。"""
        if not hasattr(world_state, "add_pending_emergence"):
            return

        threshold = self._config.get_int("emergence", "hit_threshold", 3)

        # 处理角色涌现
        char_detected: list = character_mgr_result.get("detected_emergences", []) or []
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
        loc_detected: list = location_mgr_result.get("detected_emergences", []) or []
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
        char_readiness: list = character_mgr_result.get("readiness_results", []) or []
        loc_readiness: list = location_mgr_result.get("readiness_results", []) or []
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

    def _get_llm_tools_prompt(self) -> str:
        """返回 LLM 可用的记忆/scratchpad 工具定义"""
        return """
## Available Tools

You may invoke these tools within your reasoning to access character memories:

- `read_memory(agent_id, query)` — retrieve relevant memories for an agent (use "director" for your own decisions, "world" for global events, or a character ID like "char_003" for that character's memories). query is a short natural language description of what you're looking for.
- `write_memory(agent_id, content, importance)` — record a new memory. agent_id: which agent this belongs to. content: the memory text. importance: 1-10 rating of how important this is.

When you finish your plan, call write_memory("director", "<your decision summary>", 5) to record your decision for future beats.
"""

    async def _write_beat_memories(
        self, world_state: "WorldState", plan: dict,
        character_outputs: list, narrative_text: str,
        audit_result: dict, cc_verdict: str, rr_results: list,
    ) -> None:
        """每拍结束后，将本拍的决策/事件/状态变化写入记忆流。"""
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
            from server.manana.agents import MicroOracleAgent
            from server.manana.contextual_memory import MemoryEntry
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
