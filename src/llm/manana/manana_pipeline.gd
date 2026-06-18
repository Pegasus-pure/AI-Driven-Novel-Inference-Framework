extends Node

## MaNA 五层编排器 (Autoload 单例)。
##
## 负责整个叙事管线的生命周期:
##   L0: ContextBuilder — 场景上下文构建
##   L1: SceneDirector — 节拍计划
##   L2R1: MotivationEngine — 动机分析 (N 并行)
##   L2R2: DialogueWeaver + ActionDirector — 对话+动作 (N×2 并行)
##   L3: SceneComposer — 叙事编织
##   L3b∥L4a: ConsistencyAuditor + StateExtractor (并行)
##   L4b: ThreadManager — 线索管理
##   L5: ReflectionOracle — 反思神谕 (条件触发)
##
## 通过 EventBus 广播 beat_started / beat_completed / agent_error / pipeline_degraded。
##
## 多 Provider 架构 (v2):
##   每个 tier (strong/medium/light) 拥有独立的 Provider 实例，
##   Agent 根据 model_tier 自动路由到对应 Provider。

# ============================================================
# 内部状态
# ============================================================

var _provider_strong: BaseLLMProvider = null
var _provider_medium: BaseLLMProvider = null
var _provider_light: BaseLLMProvider = null
var _config: MananaConfig = null
var _beat_count: int = 0
var _oracle_context: Dictionary = {}  # Q6: Oracle 反思结果，注入 Director
var _last_narrative: String = ""
var _pending_reconnect: bool = false

# — v4: 向量记忆、微Oracle缓冲、拍间上下文 —
var _vector_memory: VectorMemory = null
var _micro_oracle_buffer: Array = []
var _next_beat_context: Dictionary = {}

# ============================================================
# Prompt 模板缓存
# ============================================================

var _prompt_cache: Dictionary = {}

# ============================================================
# 初始化
# ============================================================

func _ready() -> void:
	_config = MananaConfig.new()
	_config.load_config()
	_init_providers()
	_vector_memory = VectorMemory.new()
	EventBus.beat_completed.connect(_on_beat_completed)


## 初始化三层 LLM Provider
func _init_providers() -> void:
	var tiers: Array[String] = ["strong", "medium", "light"]
	for tier: String in tiers:
		var tier_config: Dictionary = _config.get_tier_config(tier)
		var prov_type: String = str(tier_config.get("type", "ollama"))

		var provider: BaseLLMProvider = ProviderFactory.create(prov_type, tier_config)
		if provider:
			provider.configure(tier_config)
			# v4: 注入 embed 模型名（从 [memory] 节读取，默认 nomic-embed-text）
			var mem_cfg: Dictionary = _config.get_memory_config()
			provider._config["embed_model"] = str(mem_cfg.get("embed_model", "qwen3-embedding:0.6b"))
			# 将 HTTPRequest 节点挂载到 Pipeline 上
			if provider.has_method("_attach_http_node"):
				provider._attach_http_node(self)
			ProviderRegistry.register_provider(tier, provider)
			match tier:
				"strong":
					_provider_strong = provider
				"medium":
					_provider_medium = provider
				"light":
					_provider_light = provider
			print("[MaNA] Pipeline tier '%s': %s provider (model: %s)" % [tier, prov_type, tier_config.get("model", "?")])
		else:
			push_error("[MaNA] Pipeline init failed: could not create '%s' provider for tier '%s'" % [prov_type, tier])


## 为并行任务创建独立 Provider 实例（带独立 HTTPRequest 节点）。
## 与单例 _provider_strong/medium/light 配置相同，但请求互不阻塞。
## 调用方负责在收集结果后调用 provider.cleanup() 释放 HTTPRequest 节点。
func _create_independent_provider(tier: String) -> BaseLLMProvider:
	var tier_config: Dictionary = _config.get_tier_config(tier)
	var prov_type: String = str(tier_config.get("type", "ollama"))
	var provider: BaseLLMProvider = ProviderFactory.create(prov_type, tier_config)
	if provider == null:
		push_error("[MaNA] _create_independent_provider: failed to create provider for tier '%s'" % tier)
		return null
	# 挂载独立 HTTPRequest 到 Pipeline
	if provider.has_method("_attach_http_node"):
		provider._attach_http_node(self)
	return provider


## 根据 tier 路由到对应 Provider
func _get_provider_for_tier(tier: String) -> BaseLLMProvider:
	match tier:
		"strong":
			return _provider_strong
		"medium":
			return _provider_medium
		"light":
			return _provider_light
		_:
			return _provider_medium  # 默认 fallback


# ============================================================
# 热重连
# ============================================================

## 请求在下一个 beat 完成后重连所有 Provider
func request_reconnect() -> void:
	_pending_reconnect = true
	print("[MaNA] Hot reconnect requested — will apply after current beat completes")


## 执行重连：清理旧 Provider → 重新初始化 → 广播事件
func _do_reconnect() -> void:
	print("[MaNA] Executing hot reconnect...")
	ProviderRegistry.clear_all()
	_provider_strong = null
	_provider_medium = null
	_provider_light = null
	_init_providers()
	EventBus.provider_reconnected.emit()
	_pending_reconnect = false
	print("[MaNA] Hot reconnect complete")


# ============================================================
# 主入口: 执行一个完整的叙事节拍
# ============================================================

## 执行一个完整 Beat。
## [param player_action] 玩家当前输入
## [returns] {narrative_text: String, action_hints: Array, state_patch: Dictionary, audit: Dictionary}
func run_beat(player_action: String) -> Dictionary:
	_beat_count += 1
	var beat_id: String = "beat_%03d" % _beat_count

	MananaLogger.set_current_beat(beat_id)
	EventBus.beat_started.emit(beat_id)
	print("[MaNA] === Beat %s START ===" % beat_id)

	# ── L0: Context ──
	MananaLogger.log_layer("L0", "ContextBuilder 启动")
	var ctx: Dictionary = ContextBuilder.new().build(player_action, WorldState, beat_id)
	MananaLogger.log_layer("L0", "ContextBuilder 完成 (%d 角色, %d 线索)" % [
		(ctx.get("characters", []) as Array).size(),
		(ctx.get("active_threads", []) as Array).size(),
	])

	# ── v4: Context 增强 (CanonSelector + VectorMemory + micro_feedback) ──
	if _config.is_feature_enabled("semantic_selection") or _config.get_memory_config().get("enable_vector_memory", false):
		ctx = await _augment_context(ctx)

	# ── L1: Director ──
	var plan: Dictionary = {}
	if _config.is_feature_enabled("multi_view") and _config.is_feature_enabled("best_of_3"):
		# v4.1: 多视角 + Best-of-3
		MananaLogger.log_layer("L1", "SceneDirector 启动 (multi_view + best_of_3)")
		plan = await _run_director_multi_view(ctx)
	elif _config.is_feature_enabled("best_of_3"):
		# v4.0: 单视角 Best-of-3
		MananaLogger.log_layer("L1", "SceneDirector 启动 (best_of_3)")
		var best_plan: Dictionary = await _run_director_best_of_3(ctx)
		plan = best_plan.get("raw", {}) as Dictionary
		if plan.is_empty() and not best_plan.is_empty():
			plan = best_plan
	else:
		# v3 兼容: 单 Director
		MananaLogger.log_layer("L1", "SceneDirector 启动")
		var director: SceneDirector = SceneDirector.new()
		director.configure(_get_provider_for_tier("strong"))
		if not _oracle_context.is_empty():
			director._oracle_context = _oracle_context
		var director_input: Dictionary = {
			"system_prompt": _load_prompt("director"),
			"scene_context": ctx,
		}
		var beat_plan_result: Dictionary = await director.run(director_input)
		if not beat_plan_result.get("ok", false):
			var err: String = str(beat_plan_result.get("error", "Director failed"))
			MananaLogger.log_error("SceneDirector", err)
			EventBus.agent_error.emit("SceneDirector", err)
			return {"error": "Director failed: " + err}
		plan = beat_plan_result.get("raw", {}) as Dictionary

	if plan.is_empty():
		MananaLogger.log_error("SceneDirector", "Director produced empty plan")
		EventBus.agent_error.emit("SceneDirector", "empty plan")
		return {"error": "Director failed: empty plan"}

	MananaLogger.log_layer("L1", "SceneDirector 完成 — 模式: %s" % plan.get("narrative_mode", "?"))

	# ── v4: 复杂度评估 + 动态 Tier ──
	if _config.is_feature_enabled("dynamic_tier"):
		var complexity: float = _compute_complexity(ctx, plan)
		MananaLogger.log_layer("L1", "复杂度评分: %.2f" % complexity)
		_apply_tier_overrides(complexity)

	# ── L2R1: MotivationEngine (N 并行) ──
	MananaLogger.log_layer("L2R1", "MotivationEngine 启动 (%d 角色)" % (plan.get("featured_characters", []) as Array).size())
	var motivation_results: Array = await _run_motivations_parallel(ctx, plan)
	MananaLogger.log_layer("L2R1", "MotivationEngine 完成 (%d 结果)" % motivation_results.size())

	# ── L2R2: DialogueWeaver + ActionDirector (N×2 并行) ──
	MananaLogger.log_layer("L2R2", "DialogueWeaver/ActionDirector 启动")
	var character_outputs: Array = await _run_dialogue_actions_parallel(ctx, plan, motivation_results)
	MananaLogger.log_layer("L2R2", "DialogueWeaver/ActionDirector 完成 (%d 角色输出)" % character_outputs.size())

	# ── L3: SceneComposer ──
	var narrative_result: Dictionary = {}
	if _config.is_feature_enabled("refinement"):
		MananaLogger.log_layer("L3", "SceneComposer 启动 (精炼循环)")
		narrative_result = await _run_composer_with_refinement(ctx, character_outputs, plan)
	else:
		MananaLogger.log_layer("L3", "SceneComposer 启动")
		var composer: SceneComposer = SceneComposer.new()
		composer.configure(_get_provider_for_tier("strong"))
		var composer_input: Dictionary = _build_composer_input(plan, character_outputs, ctx)
		narrative_result = await composer.run(composer_input)

	if not narrative_result.get("ok", false):
		var composer_err: String = str(narrative_result.get("error", "Composer failed"))
		MananaLogger.log_error("SceneComposer", composer_err)
		EventBus.agent_error.emit("SceneComposer", composer_err)
		return {"error": "Composer failed: " + composer_err}

	var narrative_text: String = narrative_result.get("content", "") as String
	var composer_raw: Dictionary = narrative_result.get("raw", {}) as Dictionary
	MananaLogger.log_layer("L3", "SceneComposer 完成 (%d 字符)" % narrative_text.length())

	# ── L3b ∥ L4a: Auditor + Extractor (并行) ──
	MananaLogger.log_layer("L3b∥L4a", "Auditor / Extractor 启动 (并行)")

	var auditor: ConsistencyAuditor = ConsistencyAuditor.new()
	auditor.configure(_get_provider_for_tier("medium"))
	var auditor_input: Dictionary = _build_auditor_input(narrative_text, plan, ctx)
	var audit_result: Dictionary = await auditor.run(auditor_input)

	var extractor: StateExtractor = StateExtractor.new()
	extractor.configure(_get_provider_for_tier("light"))
	var extractor_input: Dictionary = _build_extractor_input(narrative_text, character_outputs)
	var state_patch_result: Dictionary = await extractor.run(extractor_input)

	MananaLogger.log_layer("L3b∥L4a", "Auditor / Extractor 完成")

	# 审计 FAIL 处理 (Q2: 记录 WARNING，不自动重写)
	var audit_data: Dictionary = audit_result.get("raw", {}) as Dictionary
	if str(audit_data.get("verdict", "PASS")) != "PASS":
		var issues: Array = audit_data.get("issues", []) as Array
		MananaLogger.log_warning("Auditor", "Beat %s audit FAIL: %s" % [beat_id, JSON.stringify(issues)])
		EventBus.agent_error.emit("ConsistencyAuditor", "Audit FAIL: %d issues" % issues.size())

	# ── L4b: ThreadManager ──
	MananaLogger.log_layer("L4b", "ThreadManager 启动")
	var thread_updates: Dictionary = await _run_thread_manager(narrative_text, str(plan.get("beat_summary", "")), plan)
	MananaLogger.log_layer("L4b", "ThreadManager 完成")

	# ── 应用状态变更 ──
	var state_patch: Dictionary = state_patch_result.get("raw", {}) as Dictionary
	if not state_patch.is_empty():
		WorldState.apply_state_patch(state_patch)

	# ── 应用线索变更 ──
	_apply_thread_updates(thread_updates)

	# ── 叙事历史 + 记忆 ──
	var summary: String = str(state_patch.get("narrative_summary", narrative_text.left(100)))
	if summary == "":
		summary = narrative_text.left(100)
	WorldState.add_narrative_event(summary, beat_id)
	var mem_entry: String = str(state_patch.get("scene_memory_entry", narrative_text.left(60)))
	if mem_entry != "":
		WorldState.add_to_scene_memory(mem_entry)
	WorldState.advance_time(1)
	WorldState.sync_dynamic_canon()

	# ── L5: Oracle (条件触发) ──
	if _beat_count % _config.get_oracle_interval() == 0:
		MananaLogger.log_layer("L5", "ReflectionOracle 触发 (beat %d)" % _beat_count)
		await _run_oracle(ctx)

	# ── v4: Micro-Oracle 拍末质量反馈 ──
	if _config.is_feature_enabled("micro_oracle"):
		var mo_summary: String = str(state_patch.get("narrative_summary", narrative_text.left(100)))
		if mo_summary == "":
			mo_summary = narrative_text.left(100)
		await _run_micro_oracle(narrative_text, mo_summary, ctx)

	# ── 保存 Trace ──
	MananaLogger.save_traces(beat_id)
	_last_narrative = narrative_text

	var result_data: Dictionary = {
		"narrative_text": narrative_text,
		"action_hints": composer_raw.get("action_hints", []),
		"ending_hook": composer_raw.get("ending_hook", ""),
		"music_mood": composer_raw.get("music_mood", ""),
		"state_patch": state_patch,
		"audit": audit_result,
	}

	EventBus.beat_completed.emit(beat_id, result_data)
	print("[MaNA] === Beat %s COMPLETE ===" % beat_id)

	return result_data


# ============================================================
# L2R1: MotivationEngine 并行调度
# ============================================================

func _run_motivations_parallel(ctx: Dictionary, plan: Dictionary) -> Array:
	var char_ids: Array = plan.get("featured_characters", []) as Array
	if char_ids.size() == 0:
		return []

	var results: Array = []
	var launched: int = 0

	# 第一遍: 全部启动（不 await，每个 worker 独立 Provider）
	for cid in char_ids:
		var char_data: Dictionary = _find_character(ctx, cid)
		if char_data.is_empty():
			continue

		launched += 1
		var mot_input: Dictionary = {
			"system_prompt": _load_prompt("motivation"),
			"character": char_data,
			"scene_summary": plan.get("beat_summary", ""),
			"player_action": ctx.get("player", {}).get("action", ""),
			"scene_tone": plan.get("scene_tone", "平淡"),
		}
		_motivation_worker(cid, mot_input, results)

	# 第二遍: 等待所有 worker 完成
	while results.size() < launched:
		await get_tree().process_frame

	return results


## Motivation 后台 worker: 独立 Provider → LLM 调用 → 解析 → 存入 shared results
func _motivation_worker(cid: String, mot_input: Dictionary, results: Array) -> void:
	var agent: MotivationEngine = MotivationEngine.new()
	var provider: BaseLLMProvider = _create_independent_provider("medium")
	if provider == null:
		results.append({"char_id": cid, "motivation": {}})
		return
	agent.configure(provider)

	var sys: String = agent.build_system_prompt()
	var usr: String = agent.build_user_prompt(mot_input)
	var result: Dictionary = await agent._call_llm(sys, usr, {"json_mode": true, "temperature": 0.7})

	if result.get("ok", false):
		var parsed: Dictionary = agent._parse_json_response(result)
		var data: Dictionary = parsed.get("data", {}) as Dictionary
		if not data.has("character_id") or str(data.get("character_id", "")) == "":
			data["character_id"] = cid
		results.append({
			"char_id": cid,
			"motivation": data,
		})
	else:
		# 降级: 空动机
		results.append({
			"char_id": cid,
			"motivation": {},
		})

	provider.cleanup()


# ============================================================
# L2R2: Dialogue + Action 并行调度
# ============================================================

func _run_dialogue_actions_parallel(ctx: Dictionary, plan: Dictionary, motivations: Array) -> Array:
	var da_char_ids: Array = plan.get("featured_characters", []) as Array
	if da_char_ids.size() == 0:
		return []

	# 构建交互对查找表和名称映射
	var interaction_map: Dictionary = _build_interaction_map(plan)
	var name_map: Dictionary = _build_name_map(ctx)

	# 构建 motivation 查找表
	var mot_map: Dictionary = {}
	for m_ in motivations:
		var m: Dictionary = m_ as Dictionary
		mot_map[m["char_id"]] = m.get("motivation", {})

	# 共享结果容器 + 完成计数器
	var dialogue_data: Dictionary = {}  # {char_id: dialogue_result}
	var action_data: Dictionary = {}    # {char_id: action_result}
	var counter: Dictionary = {"d": 0, "a": 0}  # 已完成计数
	var expected_d: int = 0
	var expected_a: int = 0

	# 第一遍: 全部启动（不 await，每个 worker 独立 Provider）
	for cid in da_char_ids:
		var da_char_data: Dictionary = _find_character(ctx, cid)
		if da_char_data.is_empty():
			continue

		# 注入动机分析结果
		da_char_data["motivation_output"] = mot_map.get(cid, {})

		# ── 构建交互上下文 ──
		var interaction_context: Dictionary = {}
		if cid in interaction_map:
			var pair: InteractionPair = interaction_map[cid]
			var counterpart_id: String = pair.get_counterpart(cid)
			var counterpart_motivation: Dictionary = mot_map.get(counterpart_id, {}) as Dictionary
			var counterpart_internal: Dictionary = counterpart_motivation.get("internal_state", {}) as Dictionary
			interaction_context = {
				"pair_id": pair.pair_id,
				"pair_type": pair.pair_type,
				"counterpart": {
					"name": name_map.get(counterpart_id, counterpart_id),
					"emotional_tone": counterpart_internal.get("dominant_emotion", "中性"),
					"visible_goal": counterpart_internal.get("immediate_goal", ""),
				},
			}

		var base_input: Dictionary = {
			"character": da_char_data,
			"interaction_context": interaction_context,
			"beat_summary": plan.get("beat_summary", ""),
			"player_action": ctx.get("player", {}).get("action", ""),
			"scene_tone": plan.get("scene_tone", "平淡"),
		}

		# ── 启动 Dialogue Worker（独立 Provider）──
		expected_d += 1
		_dialogue_worker(cid, base_input, dialogue_data, counter)

		# ── 启动 Action Worker（独立 Provider）──
		expected_a += 1
		_action_worker(cid, base_input, action_data, counter)

	# 第二遍: 等待所有 worker 完成
	while counter["d"] < expected_d or counter["a"] < expected_a:
		await get_tree().process_frame

	# 合并每个角色的对话 + 动作输出（与原代码逻辑完全一致）
	var da_results: Array = []
	for cid in da_char_ids:
		var merged_char_data: Dictionary = _find_character(ctx, cid)
		var d: Dictionary = dialogue_data.get(cid, {}) as Dictionary
		var actions_dict: Dictionary = action_data.get(cid, {}) as Dictionary

		# 从对话输出中抽取 action，从 action 输出中补充
		var dialogue_actions: Array = d.get("actions", []) as Array
		var dedicated_actions: Array = actions_dict.get("actions", []) as Array

		# 合并动作（对话中的优先）
		var merged_actions: Array = dialogue_actions.duplicate()
		for a_ in dedicated_actions:
			if not _action_exists(merged_actions, a_ as Dictionary):
				merged_actions.append(a_)

		var dialogue_texts: Array = []
		for dl_ in d.get("dialogue", []):
			var dl: Dictionary = dl_ as Dictionary
			dialogue_texts.append("%s: \"%s\" (%s)" % [
				dl.get("target", "?"), dl.get("text", ""), dl.get("tone", "")
			])

		da_results.append({
			"character_id": cid,
			"character_name": merged_char_data.get("name", cid),
			"dialogue": " | ".join(dialogue_texts),
			"dialogue_raw": d.get("dialogue", []),
			"actions": merged_actions,
			"actions_raw": d.get("actions", []),
			"emotional_arc": d.get("emotional_arc", ""),
			"stance_change": d.get("stance_change", ""),
			"stance_change_raw": d.get("stance_change", {}),
		})

	return da_results


## Dialogue 后台 worker: 独立 Provider → LLM → 解析 → 存入 shared dialogue_data
func _dialogue_worker(cid: String, base_input: Dictionary, dialogue_data: Dictionary, counter: Dictionary) -> void:
	var provider: BaseLLMProvider = _create_independent_provider("medium")
	if provider == null:
		dialogue_data[cid] = {}
		counter["d"] = counter["d"] + 1
		return
	var agent: DialogueWeaver = DialogueWeaver.new()
	agent.configure(provider)

	var d_input: Dictionary = base_input.duplicate(true)
	d_input["system_prompt"] = _load_prompt("dialogue_weaver")
	var d_sys: String = agent.build_system_prompt()
	var d_usr: String = agent.build_user_prompt(d_input)
	var d_result: Dictionary = await agent._call_llm(d_sys, d_usr, {"json_mode": true, "temperature": 0.85})

	if d_result.get("ok", false):
		var d_parsed: Dictionary = agent._parse_json_response(d_result)
		dialogue_data[cid] = d_parsed.get("data", {}) as Dictionary
	else:
		dialogue_data[cid] = {}

	provider.cleanup()
	counter["d"] = counter["d"] + 1


## Action 后台 worker: 独立 Provider → LLM → 解析 → 存入 shared action_data
func _action_worker(cid: String, base_input: Dictionary, action_data: Dictionary, counter: Dictionary) -> void:
	var provider: BaseLLMProvider = _create_independent_provider("light")
	if provider == null:
		action_data[cid] = {}
		counter["a"] = counter["a"] + 1
		return
	var agent: ActionDirector = ActionDirector.new()
	agent.configure(provider)

	var a_input: Dictionary = base_input.duplicate(true)
	a_input["system_prompt"] = _load_prompt("action_director")
	var a_sys: String = agent.build_system_prompt()
	var a_usr: String = agent.build_user_prompt(a_input)
	var a_result: Dictionary = await agent._call_llm(a_sys, a_usr, {"json_mode": true, "temperature": 0.6, "max_tokens": 512})

	if a_result.get("ok", false):
		var a_parsed: Dictionary = agent._parse_json_response(a_result)
		action_data[cid] = a_parsed.get("data", {}) as Dictionary
	else:
		action_data[cid] = {}

	provider.cleanup()
	counter["a"] = counter["a"] + 1


# ============================================================
# L4b: ThreadManager
# ============================================================

func _run_thread_manager(narrative_text: String, beat_summary: String, plan: Dictionary) -> Dictionary:
	var tm_agent: ThreadManager = ThreadManager.new()
	tm_agent.configure(_get_provider_for_tier("medium"))

	var active_threads: Array = WorldState.get_active_threads()
	var pool_config: Dictionary = WorldState.thread_pool_config

	var input_data: Dictionary = {
		"system_prompt": _load_prompt("thread_manager"),
		"narrative_text": narrative_text,
		"beat_summary": beat_summary,
		"active_threads": active_threads,
		"thread_pool_config": pool_config,
		"narrative_mode": plan.get("narrative_mode", ""),
	}

	var tm_result: Dictionary = await tm_agent.run(input_data)
	if tm_result.get("ok", false):
		return tm_result.get("raw", {}) as Dictionary
	return {}


# ============================================================
# L5: Oracle
# ============================================================

func _run_oracle(ctx: Dictionary) -> void:
	var oracle_agent: ReflectionOracle = ReflectionOracle.new()
	oracle_agent.configure(_get_provider_for_tier("strong"))

	var oracle_active_threads: Array = WorldState.get_active_threads()
	var threads_summary: String = WorldState.get_threads_summary()
	var recent_history: Array = WorldState.narrative_history.duplicate()
	var characters: Array = ctx.get("characters", []) as Array

	# 构建 character_arcs 数组 — 每个角色的情绪轨迹和关键行动
	var character_arcs: Array = []
	for c_ in characters:
		var c: Dictionary = c_ as Dictionary
		var cs: Dictionary = c.get("current_state", {}) as Dictionary
		character_arcs.append({
			"char_id": c.get("char_id", ""),
			"name": c.get("name", ""),
			"mood_progression": [cs.get("mood", "中性")],
			"key_actions": [],
			"stance_shift": c.get("relation_to_player", ""),
		})

	# 构建玩家画像
	var player: Dictionary = ctx.get("player", {}) as Dictionary
	var player_profile: Dictionary = {
		"traits": (player.get("profile", {}).get("traits", []) as Array),
		"motivation": str(player.get("profile", {}).get("motivation", "")),
		"tendency": str(player.get("profile", {}).get("tendency", "中立")),
		"action": player.get("action", ""),
		"reputation_count": (player.get("reputation", {}) as Dictionary).size(),
	}

	var oracle_input_data: Dictionary = {
		"system_prompt": _load_prompt("oracle"),
		"beat_count": _beat_count,
		"active_threads_summary": threads_summary,
		"recent_beats_summary": recent_history.slice(max(0, recent_history.size() - 10), recent_history.size()),
		"character_arcs": character_arcs,
		"divergence_trend": ctx.get("divergence", 0.0),
		"player_profile": player_profile,
		"game_time": ctx.get("game_time", ""),
	}

	var oracle_result: Dictionary = await oracle_agent.run(oracle_input_data)
	if oracle_result.get("ok", false):
		var oracle_data: Dictionary = oracle_result.get("raw", {}) as Dictionary
		# 存储为隐藏上下文，下次 Director 会用到
		_oracle_context = {
			"pacing": oracle_data.get("pacing_assessment", ""),
			"observations": oracle_data.get("character_observations", []),
			"opportunities": oracle_data.get("narrative_opportunities", []),
			"tone_recommendation": oracle_data.get("tone_recommendation", ""),
			"from_beat": _beat_count,
		}
		MananaLogger.log_layer("L5", "Oracle 上下文已更新 (%d 观察, %d 机会)" % [
			(oracle_data.get("character_observations", []) as Array).size(),
			(oracle_data.get("narrative_opportunities", []) as Array).size(),
		])


# ============================================================
# 辅助方法
# ============================================================

## 在 ctx.characters 中按 char_id 查找角色
func _find_character(ctx: Dictionary, char_id: String) -> Dictionary:
	var chars: Array = ctx.get("characters", []) as Array
	for c_ in chars:
		var found_char: Dictionary = c_ as Dictionary
		if found_char.get("char_id", "") == char_id:
			return found_char
	return {}


func _build_name_map(ctx: Dictionary) -> Dictionary:
	var nm: Dictionary = {}
	var nm_chars: Array = ctx.get("characters", []) as Array
	for c_ in nm_chars:
		var nm_char: Dictionary = c_ as Dictionary
		nm[nm_char.get("char_id", "")] = nm_char.get("name", "??")
	return nm


func _build_interaction_map(plan: Dictionary) -> Dictionary:
	"""构建 {char_id: InteractionPair} 查找表"""
	var im: Dictionary = {}
	var pairs: Array = plan.get("interaction_pairs", []) as Array
	for p_ in pairs:
		var interaction_pair: InteractionPair = InteractionPair.from_dict(p_ as Dictionary)
		for cid in interaction_pair.char_ids:
			im[cid] = interaction_pair
	return im


## 检查动作是否已在列表中存在
func _action_exists(existing: Array, new_action: Dictionary) -> bool:
	var new_desc: String = str(new_action.get("description", ""))
	var new_type: String = str(new_action.get("type", ""))
	for e_ in existing:
		var e: Dictionary = e_ as Dictionary
		if e.get("description", "") == new_desc and e.get("type", "") == new_type:
			return true
	return false


# ============================================================
# Composer / Auditor / Extractor 输入构建
# ============================================================

func _build_composer_input(plan: Dictionary, character_outputs: Array, ctx: Dictionary) -> Dictionary:
	var location: Dictionary = ctx.get("location", {}) as Dictionary
	return {
		"system_prompt": _load_prompt("composer"),
		"director_output": plan,
		"character_outputs": character_outputs,
		"scene_context_summary": {
			"game_time": ctx.get("game_time", ""),
			"location_name": location.get("name", ""),
			"location_atmosphere": location.get("atmosphere", ""),
			"player_action": ctx.get("player", {}).get("action", ""),
		},
		"recent_narrative": _last_narrative.left(500),
	}


func _build_auditor_input(narrative_text: String, plan: Dictionary, ctx: Dictionary) -> Dictionary:
	var auditor_characters: Array = ctx.get("characters", []) as Array

	# 构建 character_personas: {char_id: {name, core_traits, speech_style, core_fear, known_facts}}
	var character_personas: Dictionary = {}
	for c_ in auditor_characters:
		var auditor_char: Dictionary = c_ as Dictionary
		var char_id: String = str(auditor_char.get("char_id", ""))
		if char_id == "":
			continue
		var personality: String = str(auditor_char.get("personality", ""))
		# 将性格文本拆分为 traits 列表
		var traits: Array = []
		if personality != "":
			# 用常见分隔符拆分: 顿号、逗号、空格
			var parts: Array = personality.replace("、", ",").split(",")
			for p_ in parts:
				var p: String = p_.strip_edges() as String
				if p != "":
					traits.append(p)
		character_personas[char_id] = {
			"name": auditor_char.get("name", ""),
			"core_traits": traits,
			"speech_style": personality,  # 说话风格从性格推测，用性格文本代理
			"core_fear": "",              # Canon 中可能无此字段，留空
			"known_facts": auditor_char.get("known_facts", []),
		}

	# 构建 recent_facts: 从 recent_history 提取摘要字符串
	var auditor_recent_history: Array = ctx.get("recent_history", []) as Array
	var recent_facts: Array[String] = []
	for evt_ in auditor_recent_history:
		var evt: Dictionary = evt_ as Dictionary
		var evt_summary: String = str(evt.get("summary", ""))
		if evt_summary != "":
			recent_facts.append(evt_summary)

	return {
		"system_prompt": _load_prompt("auditor"),
		"narrative_text": narrative_text,
		"character_personas": character_personas,
		"world_rules": ctx.get("relevant_world_rules", ""),
		"recent_facts": recent_facts,
		"previous_narrative": _last_narrative.left(500),
	}


func _build_extractor_input(narrative_text: String, character_outputs: Array) -> Dictionary:
	var existing_state: Dictionary = {
		"character_moods": _build_mood_snapshot(),
		"character_locations": _build_location_snapshot(),
		"player_reputation": WorldState.player_reputation.duplicate(true),
		"active_threads": WorldState.get_active_threads(),
		"knowledge_graph": WorldState.knowledge_graph.duplicate(true),
	}

	return {
		"system_prompt": _load_prompt("state_extractor"),
		"narrative_text": narrative_text,
		"character_outputs": character_outputs,
		"existing_state": existing_state,
	}


func _build_mood_snapshot() -> Dictionary:
	var snap: Dictionary = {}
	for cid in WorldState.characters_state:
		var mood_cs: Dictionary = WorldState.characters_state[cid] as Dictionary
		snap[cid] = {
			"mood": mood_cs.get("mood", "中性"),
			"intensity": mood_cs.get("mood_intensity", 0.0),
		}
	return snap


func _build_location_snapshot() -> Dictionary:
	var loc_snap: Dictionary = {}
	for cid in WorldState.characters_state:
		var loc_cs: Dictionary = WorldState.characters_state[cid] as Dictionary
		loc_snap[cid] = loc_cs.get("location", "")
	return loc_snap


## 应用 ThreadManager 产出的线索变更
func _apply_thread_updates(updates: Dictionary) -> void:
	# 推进线索
	for adv_ in updates.get("thread_advances", []):
		var adv: Dictionary = adv_ as Dictionary
		var tid: String = str(adv.get("thread_id", ""))
		var delta: float = adv.get("delta", 0.0) as float
		if tid != "" and delta > 0:
			WorldState.advance_thread(tid, delta)

	# 新建线索
	for nt_ in updates.get("new_threads", []):
		var nt: Dictionary = nt_ as Dictionary
		WorldState.create_thread_from_narrative(
			str(nt.get("title", "新线索")),
			str(nt.get("type", "side")),
		)

	# 关闭线索 (ThreadManager 输出 String[])
	for ct_ in updates.get("closed_threads", []):
		var ct: String = str(ct_)
		if ct != "":
			WorldState.close_thread_by_id(ct)

	# 张力调节
	for ta_ in updates.get("tension_adjustments", []):
		var ta: Dictionary = ta_ as Dictionary
		var tension_tid: String = str(ta.get("thread_id", ""))
		var tension: float = ta.get("new_tension", 0.5) as float
		if tension_tid != "":
			WorldState.set_thread_tension(tension_tid, tension)


# ============================================================
# Prompt 模板加载
# ============================================================

## 从 res://prompts/ 加载 prompt 模板，带缓存。
func _load_prompt(agent_key: String) -> String:
	if _prompt_cache.has(agent_key):
		return _prompt_cache[agent_key] as String

	var path: String = "res://prompts/%s.md" % agent_key
	if not FileAccess.file_exists(path):
		push_warning("[MaNA] Prompt file not found: %s, using default" % path)
		return ""

	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return ""

	var content: String = f.get_as_text()
	f.close()
	_prompt_cache[agent_key] = content
	return content


# ============================================================
# 公共 API
# ============================================================

## 检查 Pipeline 是否已初始化就绪（至少 strong provider 可用）
func is_ready() -> bool:
	return _provider_strong != null


## 获取配置值（按 section + key）
func get_config_value(section: String, key: String, default: Variant = "") -> Variant:
	if _config == null:
		return default
	_config._ensure_loaded()
	return _config._config_file.get_value(section, key, default)


## 设置配置值（按 section + key）并自动保存
func set_config_value(section: String, key: String, value: Variant) -> void:
	if _config == null:
		return
	_config._ensure_loaded()
	_config._config_file.set_value(section, key, value)
	_config._config_file.save(MananaConfig.CONFIG_PATH)


## 强制保存配置到磁盘
func save_settings() -> void:
	if _config == null:
		return
	_config._ensure_loaded()
	_config._config_file.save(MananaConfig.CONFIG_PATH)


# ============================================================
# Signal Handler
# ============================================================

func _on_beat_completed(_beat_id: String, _result: Dictionary) -> void:
	if _pending_reconnect:
		_do_reconnect()


# ============================================================
# v4: Context 增强 (CanonSelector + VectorMemory + micro_feedback)
# ============================================================

## 增强上下文: 语义 Canon 选择 + 向量记忆检索 + 微Oracle反馈注入
func _augment_context(ctx: Dictionary) -> Dictionary:
	# ── P2-1: CanonSelector 语义过滤 ──
	if _config.is_feature_enabled("semantic_selection"):
		await _select_relevant_canon(ctx)

	# ── VectorMemory 语义检索 ──
	var mem_config: Dictionary = _config.get_memory_config()
	if mem_config.get("enable_vector_memory", false) and _vector_memory != null and _vector_memory.size() > 0:
		var ctx_summary: String = _build_context_summary(ctx)
		var query_embedding: PackedFloat64Array = await _vector_memory.embed(_provider_medium, ctx_summary)
		if query_embedding.size() > 0:
			var top_k: int = mem_config.get("vector_top_k", 3) as int
			var similar_memories: Array = _vector_memory.search(query_embedding, top_k)
			if similar_memories.size() > 0:
				var mem_texts: Array[String] = []
				for entry_ in similar_memories:
					var entry: Dictionary = entry_ as Dictionary
					var text: String = str(entry.get("text", ""))
					if text != "":
						mem_texts.append(text)
				if mem_texts.size() > 0:
					ctx["semantic_memories"] = mem_texts

	# ── P1-1: 注入上一拍 Micro-Oracle 反馈 ──
	var micro_feedback: String = str(_next_beat_context.get("micro_feedback", ""))
	if micro_feedback != "":
		ctx["micro_feedback"] = micro_feedback

	return ctx


## 构建场景摘要供向量检索使用
func _build_context_summary(ctx: Dictionary) -> String:
	var parts: Array[String] = []
	var location: Dictionary = ctx.get("location", {}) as Dictionary
	if location.get("name", "") != "":
		parts.append("地点: " + str(location.get("name", "")))
	var player_dict: Dictionary = ctx.get("player", {}) as Dictionary
	if player_dict.get("action", "") != "":
		parts.append("玩家行动: " + str(player_dict.get("action", "")))
	var chars: Array = ctx.get("characters", []) as Array
	for c_ in chars:
		var c: Dictionary = c_ as Dictionary
		parts.append(str(c.get("name", "")))
	var threads: Array = ctx.get("active_threads", []) as Array
	for t_ in threads:
		var t: Dictionary = t_ as Dictionary
		parts.append(str(t.get("title", "")))
	return " | ".join(parts)


# ============================================================
# v4: P2-1 Canon 语义选择
# ============================================================

## 调用 CanonSelector 做候选 Canon 的语义 Top-K 选择
func _select_relevant_canon(ctx: Dictionary) -> void:
	var candidates: Array = ctx.get("_canon_candidates", []) as Array
	# 少于等于 5 个候选时直接全注入，无需 LLM 选择
	if candidates.size() <= 5:
		return

	var location: Dictionary = ctx.get("location", {}) as Dictionary
	var player_dict: Dictionary = ctx.get("player", {}) as Dictionary

	# 构建角色摘要
	var char_names: Array[String] = []
	var chars: Array = ctx.get("characters", []) as Array
	for c_ in chars:
		var c: Dictionary = c_ as Dictionary
		char_names.append(str(c.get("name", "")))

	# 构建线索摘要
	var threads_summary: Array[String] = []
	var threads: Array = ctx.get("active_threads", []) as Array
	for t_ in threads:
		var t: Dictionary = t_ as Dictionary
		threads_summary.append(str(t.get("title", "")))

	var selector: CanonSelectorAgent = CanonSelectorAgent.new()
	selector.configure(_get_provider_for_tier("light"))

	var selector_input: Dictionary = {
		"location_name": location.get("name", ""),
		"location_description": location.get("description", ""),
		"player_action": player_dict.get("action", ""),
		"characters_on_scene": char_names,
		"threads_summary": " | ".join(threads_summary),
		"canon_candidates": candidates,
	}

	var selector_result: Dictionary = await selector.run(selector_input)
	var prioritized_ids: Array = selector_result.get("prioritized_ids", []) as Array

	if prioritized_ids.size() > 0:
		var prioritized_canon: Array = []
		for pid in prioritized_ids:
			for cand_ in candidates:
				var cand: Dictionary = cand_ as Dictionary
				if str(cand.get("id", "")) == str(pid):
					prioritized_canon.append(cand)
					break
		if prioritized_canon.size() > 0:
			ctx["required_canon"] = prioritized_canon


# ============================================================
# v4: P0-2 Best-of-3 Director
# ============================================================

## 并行 3 个 Director (不同 temperature) + 1 个 Scorer 选最优
## [param prompt_key] 可选 prompt 文件名键，默认 "director"，多视角时传 "director_plot" / "director_char"
func _run_director_best_of_3(ctx: Dictionary, prompt_key: String = "director") -> Dictionary:
	var bo3_config: Dictionary = _config.get_best_of_3_config()
	var sample_count: int = bo3_config.get("sample_count", 3) as int
	var min_total: int = bo3_config.get("scorer_min_total", 8) as int

	# 构建 temperature 序列
	var temps: Array = [0.4, 0.6, 0.8]
	if sample_count == 2:
		temps = [0.4, 0.7]
	elif sample_count == 1:
		temps = [0.6]

	# 逐个执行 Director 任务
	var plans: Array = []
	for t in temps:
		var director: SceneDirector = SceneDirector.new()
		director.configure(_get_provider_for_tier("strong"))
		if not _oracle_context.is_empty():
			director._oracle_context = _oracle_context
		var d_input: Dictionary = {
			"system_prompt": _load_prompt(prompt_key),
			"scene_context": ctx,
		}
		var result: Dictionary = await director.run(d_input)
		if result.get("ok", false):
			var raw: Dictionary = result.get("raw", {}) as Dictionary
			if not raw.is_empty():
				plans.append(raw)

	if plans.size() == 0:
		MananaLogger.log_error("SceneDirector", "Best-of-3: all directors failed")
		EventBus.agent_error.emit("SceneDirector", "all Best-of-3 directors failed")
		return {"error": "All directors failed", "raw": {}}

	if plans.size() == 1:
		return {"ok": true, "raw": plans[0]}

	# 用 Scorer 评分选择最优
	var scorer: PlanScorerAgent = PlanScorerAgent.new()
	scorer.configure(_get_provider_for_tier("light"))

	var best_plan: Dictionary = plans[0]
	var best_total: int = 0
	for plan_ in plans:
		var plan: Dictionary = plan_ as Dictionary
		var score_result: Dictionary = await scorer.run(plan)
		var total: int = score_result.get("total", 0) as int
		if total > best_total:
			best_total = total
			best_plan = plan

	# 检查最低分阈值，全不达标则取最高分
	if best_total < min_total and plans.size() > 1:
		MananaLogger.log_warning("SceneDirector", "Best-of-3: all plans below min_total (%d), using best available" % min_total)

	MananaLogger.log_layer("L1", "Best-of-3 选中: total=%d (from %d candidates)" % [best_total, plans.size()])
	return {"ok": true, "raw": best_plan}


# ============================================================
# v4: P1-3 多视角 Director 合成
# ============================================================

## plot-driven + character-driven 双视角 Best-of-3 + Synthesizer 融合
func _run_director_multi_view(ctx: Dictionary) -> Dictionary:
	# ── plot-driven 视角 Best-of-3 ──
	MananaLogger.log_layer("L1", "Multi-View: 启动 plot-driven Best-of-3")
	var plot_ctx: Dictionary = ctx.duplicate(true)
	plot_ctx["_director_mode"] = "plot_driven"
	var plot_result: Dictionary = await _run_director_best_of_3(plot_ctx, "director_plot")
	var plot_plan: Dictionary = plot_result.get("raw", {}) as Dictionary

	# ── character-driven 视角 Best-of-3 ──
	MananaLogger.log_layer("L1", "Multi-View: 启动 character-driven Best-of-3")
	var char_ctx: Dictionary = ctx.duplicate(true)
	char_ctx["_director_mode"] = "character_driven"
	var char_result: Dictionary = await _run_director_best_of_3(char_ctx, "director_char")
	var char_plan: Dictionary = char_result.get("raw", {}) as Dictionary

	# ── Synthesizer 融合 ──
	MananaLogger.log_layer("L1", "Multi-View: Synthesizer 融合双视角")
	var synthesizer: PlanSynthesizerAgent = PlanSynthesizerAgent.new()
	synthesizer.configure(_get_provider_for_tier("medium"))

	var synth_input: Dictionary = {
		"scene_context": ctx,
		"plot_plan": plot_plan,
		"character_plan": char_plan,
	}
	var synth_result: Dictionary = await synthesizer.run(synth_input)
	var final_plan: Dictionary = synth_result.get("raw", {}) as Dictionary

	if final_plan.is_empty():
		# 降级: 取非空视角
		final_plan = char_plan
		if final_plan.is_empty():
			final_plan = plot_plan

	MananaLogger.log_layer("L1", "Multi-View: 合成完成")
	return final_plan


# ============================================================
# v4: P0-1 Composer 精炼循环
# ============================================================

## Composer + Auditor 精炼循环: PASS → 交付, WARNING → 微调1轮, FAIL → 重写最多2轮
func _run_composer_with_refinement(ctx: Dictionary, character_outputs: Array, plan: Dictionary) -> Dictionary:
	var limits: Dictionary = _config.get_refinement_limits()
	var max_warning_refine: int = limits.get("max_warning_refine", 1) as int
	var max_fail_rewrite: int = limits.get("max_fail_rewrite", 2) as int

	# ── 第一轮: Composer → Auditor ──
	var composer: SceneComposer = SceneComposer.new()
	composer.configure(_get_provider_for_tier("strong"))
	var composer_input: Dictionary = _build_composer_input(plan, character_outputs, ctx)
	var result: Dictionary = await composer.run(composer_input)

	if not result.get("ok", false):
		return result  # Composer 失败，直接返回

	var narrative_text: String = result.get("content", "") as String

	# 运行 Auditor 检查
	var auditor: ConsistencyAuditor = ConsistencyAuditor.new()
	auditor.configure(_get_provider_for_tier("medium"))
	var auditor_input: Dictionary = _build_auditor_input(narrative_text, plan, ctx)
	var audit_result: Dictionary = await auditor.run(auditor_input)
	var audit_data: Dictionary = audit_result.get("raw", {}) as Dictionary
	var verdict: String = str(audit_data.get("verdict", "PASS"))

	if verdict == "PASS":
		MananaLogger.log_layer("L3", "精炼循环: PASS — 无需精炼")
		return result

	# ── WARNING: 微调1轮 ──
	if verdict == "WARNING":
		MananaLogger.log_layer("L3", "精炼循环: WARNING — 微调1轮")
		for i in range(max_warning_refine):
			var refinement_hints: Array = audit_data.get("refinement_hints", []) as Array
			composer_input["refinement_hints"] = refinement_hints
			composer_input["mode"] = "refine"
			result = await composer.run(composer_input)
			if result.get("ok", false):
				return result
		# 微调全部失败，返回原始结果
		return result

	# ── FAIL: 最多重写 max_fail_rewrite 轮，取最优 ──
	MananaLogger.log_layer("L3", "精炼循环: FAIL — 重写最多%d轮" % max_fail_rewrite)
	var initial_quality: float = audit_data.get("overall_quality", 0.0) as float
	var candidates: Array = [{"result": result, "quality": initial_quality}]
	var best_quality: float = initial_quality

	for i in range(max_fail_rewrite):
		var refinement_hints: Array = audit_data.get("refinement_hints", []) as Array
		var rewrite_input: Dictionary = _build_composer_input(plan, character_outputs, ctx)
		rewrite_input["refinement_hints"] = refinement_hints
		rewrite_input["mode"] = "rewrite"

		var rewrite_result: Dictionary = await composer.run(rewrite_input)
		if not rewrite_result.get("ok", false):
			continue

		var rewrite_text: String = rewrite_result.get("content", "") as String
		var re_auditor_input: Dictionary = _build_auditor_input(rewrite_text, plan, ctx)
		var re_audit_result: Dictionary = await auditor.run(re_auditor_input)
		var re_audit_data: Dictionary = re_audit_result.get("raw", {}) as Dictionary
		var re_verdict: String = str(re_audit_data.get("verdict", "FAIL"))
		var re_quality: float = re_audit_data.get("overall_quality", 0.0) as float

		candidates.append({"result": rewrite_result, "quality": re_quality})

		if re_verdict == "PASS":
			return rewrite_result

		if re_quality > best_quality:
			best_quality = re_quality

		audit_data = re_audit_data

	# 取评分最高的候选
	var picked: Dictionary = candidates[0]["result"] as Dictionary
	var picked_quality: float = candidates[0]["quality"] as float
	for cand_ in candidates:
		var cand: Dictionary = cand_ as Dictionary
		var cand_quality: float = cand.get("quality", 0.0) as float
		if cand_quality > picked_quality:
			picked_quality = cand_quality
			picked = cand["result"] as Dictionary

	MananaLogger.log_layer("L3", "精炼循环: 从%d个候选中选取最优 (quality=%.2f)" % [candidates.size(), picked_quality])
	return picked


# ============================================================
# v4: P1-1 Micro-Oracle 拍末反馈
# ============================================================

## 每拍结束后运行 Micro-Oracle，反馈存入缓冲区和下一拍上下文
func _run_micro_oracle(narrative_text: String, summary_text: String, ctx: Dictionary) -> void:
	var oracle_agent: MicroOracleAgent = MicroOracleAgent.new()
	oracle_agent.configure(_get_provider_for_tier("light"))

	var mo_input: Dictionary = {"narrative_summary": summary_text, "scene_context": ctx}
	var feedback: Dictionary = await oracle_agent.run(mo_input)

	_micro_oracle_buffer.append(feedback)
	if _micro_oracle_buffer.size() > 10:
		_micro_oracle_buffer.pop_front()

	# 传递给下一拍 Director 的隐藏上下文
	_next_beat_context["micro_feedback"] = str(feedback.get("one_line_feedback", ""))

	if feedback.get("has_issue", false):
		var severity: String = str(feedback.get("severity", "info"))
		if severity == "alert" or severity == "warning":
			MananaLogger.log_warning("MicroOracle", "Beat %d: [%s] %s" % [_beat_count, severity, feedback.get("one_line_feedback", "")])


# ============================================================
# v4: P1-2 复杂度评分
# ============================================================

## 计算当前拍复杂度 (0.0~1.0)
func _compute_complexity(ctx: Dictionary, plan: Dictionary) -> float:
	var score: float = 0.0

	# 新角色登场
	if _has_new_character(ctx, plan):
		score += 0.3

	# 多线索交织
	var involved_threads: Array = plan.get("priority_thread_ids", []) as Array
	if involved_threads.size() >= 2:
		score += 0.25

	# 高偏离度
	var divergence: float = ctx.get("divergence", 0.0) as float
	if divergence >= 0.4:
		score += 0.2

	# 冲突场景
	var pairs: Array = plan.get("interaction_pairs", []) as Array
	for p_ in pairs:
		var p: Dictionary = p_ as Dictionary
		if str(p.get("pair_type", "")) == "conflict":
			score += 0.15
			break

	# 玩家直接介入
	var player_dict: Dictionary = ctx.get("player", {}) as Dictionary
	var action: String = str(player_dict.get("action", ""))
	if _contains_intervention_keywords(action):
		score += 0.1

	return min(score, 1.0)


## 检查是否有新角色 (不在 WorldState 已知角色中)
func _has_new_character(ctx: Dictionary, _plan: Dictionary) -> bool:
	var chars: Array = ctx.get("characters", []) as Array
	for c_ in chars:
		var c: Dictionary = c_ as Dictionary
		var char_id: String = str(c.get("char_id", ""))
		if char_id != "" and not WorldState.characters_state.has(char_id):
			return true
	return false


## 检查玩家行动是否包含介入关键词
func _contains_intervention_keywords(action: String) -> bool:
	var keywords: Array[String] = ["阻止", "改变", "干涉", "打断", "阻止", "制止", "干预", "插手"]
	for kw in keywords:
		if action.find(kw) != -1:
			return true
	return false


# ============================================================
# v4: P1-2 动态 Tier 覆写
# ============================================================

## 根据复杂度分数应用 tier 覆写
func _apply_tier_overrides(complexity: float) -> void:
	var overrides: Dictionary = _config.get_tier_overrides(complexity)
	if overrides.is_empty():
		return

	# overrides 包含导演建议的 tier 分配，当前简化实现仅记录日志
	# 实际的 tier 切换在 Agent 创建时通过 _get_provider_for_tier 完成
	MananaLogger.log_layer("L1", "动态Tier: complexity=%.2f → overrides=%s" % [complexity, JSON.stringify(overrides)])


# ============================================================
# 公共查询
# ============================================================

func get_beat_count() -> int:
	return _beat_count


func get_last_narrative() -> String:
	return _last_narrative


func get_oracle_context() -> Dictionary:
	return _oracle_context
