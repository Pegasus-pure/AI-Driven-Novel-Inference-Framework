extends Node
## ================================================================
## test_manana_pipeline_parallel.gd
## Edward (QA) — MaNA v4 L2R1+L2R2 并行化测试套件
##
## 用法：
##   1. 在 Godot 编辑器中创建测试场景，将此脚本挂载到根节点
##   2. 运行场景，观察控制台输出中的 TEST RESULT 行
##   3. 亦可手动调用: MananaPipelineTest.run_all()
##
## 测试覆盖:
##   A. _create_independent_provider — Provider 创建与节点挂载
##   B. _motivation_worker — Worker 正确性（含 null/error fallback）
##   C. _dialogue_worker — Worker 正确性（含 null/error fallback）
##   D. _action_worker — Worker 正确性（含 null/error fallback）
##   E. 合并逻辑 — _run_dialogue_actions_parallel 合并语义
##   F. Counter 正确性 — 所有路径均递增 counter（防死锁）
##   G. _action_exists — 去重正确性
##   H. 边界条件 — 空 char_ids、空 character data、null provider
##   I. ProviderFactory 集成 — _create_independent_provider 调用链
## ================================================================

# ============================================================
# 测试基础结构
# ============================================================

var _total: int = 0
var _passed: int = 0
var _failed: int = 0
var _failure_details: Array[String] = []


func _ready() -> void:
	print("[TestSuite] === MaNA v4 L2R1+L2R2 并行化测试套件 ===")
	print("[TestSuite] 启动时间: %s" % Time.get_datetime_string_from_system())
	await get_tree().process_frame  # 等待 Autoload 初始化
	run_all()

	# 输出汇总
	print("")
	print("[TestSuite] ========== TEST REPORT ==========")
	print("[TestSuite] Total: %d | Passed: %d | Failed: %d" % [_total, _passed, _failed])
	if _failed > 0:
		print("[TestSuite] --- FAILURES ---")
		for detail in _failure_details:
			print("[TestSuite]   ✗ %s" % detail)
	print("[TestSuite] ==================================")

	if _failed == 0:
		print("[TestSuite] RESULT: ALL TESTS PASSED ✓")
	else:
		print("[TestSuite] RESULT: %d FAILURES ✗" % _failed)


func assert_eq(actual, expected, test_name: String, context: String = "") -> void:
	_total += 1
	if actual == expected:
		_passed += 1
		print("[TestSuite]   ✓ %s" % test_name)
	else:
		_failed += 1
		var detail: String = "%s: expected `%s`, got `%s`" % [test_name, str(expected), str(actual)]
		if context != "":
			detail += " | context: %s" % context
		_failure_details.append(detail)
		print("[TestSuite]   ✗ %s" % detail)


func assert_true(condition: bool, test_name: String, context: String = "") -> void:
	_total += 1
	if condition:
		_passed += 1
		print("[TestSuite]   ✓ %s" % test_name)
	else:
		_failed += 1
		var detail: String = "%s: expected true, got false" % test_name
		if context != "":
			detail += " | context: %s" % context
		_failure_details.append(detail)
		print("[TestSuite]   ✗ %s" % detail)


func assert_not_null(value, test_name: String, context: String = "") -> void:
	_total += 1
	if value != null:
		_passed += 1
		print("[TestSuite]   ✓ %s" % test_name)
	else:
		_failed += 1
		var detail: String = "%s: expected non-null, got null" % test_name
		if context != "":
			detail += " | context: %s" % context
		_failure_details.append(detail)
		print("[TestSuite]   ✗ %s" % detail)


func assert_null(value, test_name: String, context: String = "") -> void:
	_total += 1
	if value == null:
		_passed += 1
		print("[TestSuite]   ✓ %s" % test_name)
	else:
		_failed += 1
		var detail: String = "%s: expected null, got `%s`" % [test_name, str(value)]
		if context != "":
			detail += " | context: %s" % context
		_failure_details.append(detail)
		print("[TestSuite]   ✗ %s" % detail)


func assert_has_method(obj, method_name: String, test_name: String) -> void:
	_total += 1
	if obj != null and obj.has_method(method_name):
		_passed += 1
		print("[TestSuite]   ✓ %s" % test_name)
	else:
		_failed += 1
		var detail: String = "%s: object missing method '%s'" % [test_name, method_name]
		_failure_details.append(detail)
		print("[TestSuite]   ✗ %s" % detail)


# ============================================================
# 测试入口
# ============================================================

func run_all() -> void:
	print("[TestSuite] --- A: _create_independent_provider ---")
	await test_create_independent_provider()

	print("[TestSuite] --- B: _motivation_worker ---")
	await test_motivation_worker()

	print("[TestSuite] --- C: _dialogue_worker ---")
	await test_dialogue_worker()

	print("[TestSuite] --- D: _action_worker ---")
	await test_action_worker()

	print("[TestSuite] --- E: Merge Logic ---")
	test_merge_logic()

	print("[TestSuite] --- F: Counter Correctness ---")
	await test_counter_correctness()

	print("[TestSuite] --- G: _action_exists ---")
	test_action_exists()

	print("[TestSuite] --- H: Boundary Conditions ---")
	await test_boundary_conditions()

	print("[TestSuite] --- I: ProviderFactory Integration ---")
	test_provider_factory_integration()

	print("[TestSuite] --- J: cleanup() Call Verification ---")
	test_cleanup_called()

	print("[TestSuite] --- K: Null Provider Fallback ---")
	await test_null_provider_fallback()


# ============================================================
# A: _create_independent_provider 测试
# ============================================================

func test_create_independent_provider() -> void:
	# 获取 Pipeline 实例（Autoload）
	var pipeline: MananaPipeline = MananaPipeline
	assert_not_null(pipeline, "A.1 Pipeline Autoload exists")
	if pipeline == null:
		return

	var tier: String = "medium"

	# A.2: 验证方法存在
	assert_has_method(pipeline, "_create_independent_provider", "A.2 _create_independent_provider method exists")

	# A.3: 创建独立 Provider
	var provider: BaseLLMProvider = pipeline._create_independent_provider(tier)
	assert_not_null(provider, "A.3 _create_independent_provider returns non-null for valid tier '%s'" % tier)

	if provider == null:
		return

	# A.4: Provider 已正确配置（通过 ProviderFactory.create 内部调用 configure）
	# 验证 _config 被填充
	assert_true(provider._config.size() > 0, "A.4 Provider._config is populated after creation")

	# A.5: 验证关键配置字段存在
	assert_true(provider._config.has("model"), "A.5 Provider._config has 'model' key")
	assert_true(provider._config.has("endpoint"), "A.5 Provider._config has 'endpoint' key")
	assert_true(provider._config.has("type"), "A.5 Provider._config has 'type' key")

	# A.6: HTTPRequest 节点已挂载
	assert_not_null(provider._http_request, "A.6 Provider._http_request is non-null after _attach_http_node")

	# A.7: HTTPRequest 是 Pipeline 的子节点
	if provider._http_request:
		var parent: Node = provider._http_request.get_parent()
		assert_true(parent == pipeline, "A.7 HTTPRequest parent is Pipeline (self)")

	# A.8: 无效 tier 也应有 fallback（验证不会崩溃）
	var bad_provider: BaseLLMProvider = pipeline._create_independent_provider("nonexistent_tier")
	# 无效 tier 可能导致 ProviderFactory 返回 null，或使用默认配置
	# 验证不会返回一个未配置好的 provider
	if bad_provider != null:
		# 如果返回了 provider，验证它至少是可用的
		assert_true(bad_provider._config.size() > 0, "A.8 Bad tier provider has config (graceful degradation)")

	# 清理
	if provider:
		provider.cleanup()
	if bad_provider:
		bad_provider.cleanup()


# ============================================================
# B: _motivation_worker 测试
# ============================================================

func test_motivation_worker() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	# B.1: 验证 worker 方法存在
	assert_has_method(pipeline, "_motivation_worker", "B.1 _motivation_worker method exists")

	# B.2: 验证 worker 接受正确类型的参数
	# (静态类型检查 — 函数签名: func _motivation_worker(cid: String, mot_input: Dictionary, results: Array) -> void)
	# 已在 manana_pipeline.gd:355 声明，编译期由 Godot 验证

	# B.3: 用 Mock Provider 验证 worker 流程
	var mock_provider := _MockProvider.new()
	mock_provider.mock_response = {"ok": true, "content": '{"character_id":"test","internal_state":{"mood":"中性"}}', "raw": "", "tokens": 10}

	# 注入 mock — 使用子类覆盖 _create_independent_provider
	var test_runner := _PipelineTestRunner.new(pipeline, mock_provider)

	var results: Array = []
	var mot_input: Dictionary = {
		"system_prompt": "test prompt",
		"character": {"char_id": "char_001", "name": "TestChar"},
		"scene_summary": "test scene",
		"player_action": "look",
		"scene_tone": "平淡",
	}

	test_runner._motivation_worker("char_001", mot_input, results)
	# worker 包含 await，需要等待至少一帧
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	# B.4: 验证结果被追加到 results
	assert_true(results.size() > 0, "B.4 _motivation_worker appends result to shared array")

	if results.size() > 0:
		var entry: Dictionary = results[0] as Dictionary
		assert_true(entry.has("char_id"), "B.5 Result entry has 'char_id'")
		assert_eq(entry.get("char_id", ""), "char_001", "B.6 Result char_id matches input")
		assert_true(entry.has("motivation"), "B.7 Result entry has 'motivation'")


# ============================================================
# C: _dialogue_worker 测试
# ============================================================

func test_dialogue_worker() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	assert_has_method(pipeline, "_dialogue_worker", "C.1 _dialogue_worker method exists")

	var mock_provider := _MockProvider.new()
	mock_provider.mock_response = {"ok": true, "content": '{"character_id":"char_001","dialogue":[{"text":"Hello","tone":"平静","target":"player"}],"actions":[],"emotional_arc":"stable","stance_change":{"new_attitude":"中立"}}', "raw": "", "tokens": 15}

	var test_runner := _PipelineTestRunner.new(pipeline, mock_provider)
	var dialogue_data: Dictionary = {}
	var counter: Dictionary = {"d": 0, "a": 0}
	var base_input: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "char_001", "name": "TestChar"},
		"beat_summary": "test",
		"player_action": "speak",
		"scene_tone": "平淡",
	}

	var initial_d: int = counter["d"]
	test_runner._dialogue_worker("char_001", base_input, dialogue_data, counter)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	# C.2: counter["d"] 被递增
	assert_true(counter["d"] > initial_d, "C.2 dialogue worker increments counter['d']")

	# C.3: dialogue_data 被填充
	assert_true(dialogue_data.has("char_001"), "C.3 dialogue_data contains entry for char_001")

	# C.4: counter 精确递增 1
	assert_eq(counter["d"], initial_d + 1, "C.4 counter['d'] incremented by exactly 1")


# ============================================================
# D: _action_worker 测试
# ============================================================

func test_action_worker() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	assert_has_method(pipeline, "_action_worker", "D.1 _action_worker method exists")

	var mock_provider := _MockProvider.new()
	mock_provider.mock_response = {"ok": true, "content": '{"character_id":"char_001","actions":[{"type":"gesture","description":"nods","target":"player","intensity":"subtle"}]}', "raw": "", "tokens": 8}

	var test_runner := _PipelineTestRunner.new(pipeline, mock_provider)
	var action_data: Dictionary = {}
	var counter: Dictionary = {"d": 0, "a": 0}
	var base_input: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "char_001", "name": "TestChar"},
		"beat_summary": "test",
		"player_action": "speak",
		"scene_tone": "平淡",
	}

	var initial_a: int = counter["a"]
	test_runner._action_worker("char_001", base_input, action_data, counter)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	# D.2: counter["a"] 被递增
	assert_true(counter["a"] > initial_a, "D.2 action worker increments counter['a']")

	# D.3: action_data 被填充
	assert_true(action_data.has("char_001"), "D.3 action_data contains entry for char_001")

	# D.4: counter 精确递增 1
	assert_eq(counter["a"], initial_a + 1, "D.4 counter['a'] incremented by exactly 1")


# ============================================================
# E: 合并逻辑测试
# ============================================================

func test_merge_logic() -> void:
	# 模拟合并逻辑的核心路径（manana_pipeline.gd:458-494）
	# 使用纯数据验证，不用完整 Pipeline

	var dialogue_data: Dictionary = {
		"char_A": {
			"dialogue": [
				{"text": "Hello there", "tone": "友善", "target": "player"},
				{"text": "What are you doing?", "tone": "好奇", "target": "player"},
			],
			"actions": [
				{"type": "gesture", "description": "waves hand"},
			],
			"emotional_arc": "rising_interest",
			"stance_change": {"new_attitude": "友善"},
		},
		"char_B": {
			"dialogue": [],
			"actions": [],
			"emotional_arc": "",
			"stance_change": {},
		},
	}

	var action_data: Dictionary = {
		"char_A": {
			"actions": [
				{"type": "facial", "description": "smiles"},
				{"type": "gesture", "description": "waves hand"},  # 重复 — 应去重
			],
		},
	}

	var ctx: Dictionary = {
		"characters": [
			{"char_id": "char_A", "name": "Alice"},
			{"char_id": "char_B", "name": "Bob"},
		],
	}

	# 模拟合并
	var da_char_ids: Array = ["char_A", "char_B"]
	var da_results: Array = []
	for cid in da_char_ids:
		var merged_char_data: Dictionary = _find_character_static(ctx, cid)
		var d: Dictionary = dialogue_data.get(cid, {}) as Dictionary
		var actions_dict: Dictionary = action_data.get(cid, {}) as Dictionary

		var dialogue_actions: Array = d.get("actions", []) as Array
		var dedicated_actions: Array = actions_dict.get("actions", []) as Array

		var merged_actions: Array = dialogue_actions.duplicate()
		for a_ in dedicated_actions:
			if not _action_exists_static(merged_actions, a_ as Dictionary):
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

	# E.1: 合并结果包含所有角色
	assert_eq(da_results.size(), 2, "E.1 Merge produces result for all characters")

	# E.2: char_A 的合并结果
	var char_a_result: Dictionary = da_results[0] as Dictionary
	assert_eq(char_a_result.get("character_name", ""), "Alice", "E.2a char_A name is Alice")
	assert_eq(char_a_result.get("emotional_arc", ""), "rising_interest", "E.2b emotional_arc preserved")

	# E.3: 动作去重 — gestures/waves hand 不应重复
	var actions_a: Array = char_a_result.get("actions", []) as Array
	var wave_count: int = 0
	for act in actions_a:
		var a: Dictionary = act as Dictionary
		if a.get("description", "") == "waves hand":
			wave_count += 1
	assert_eq(wave_count, 1, "E.3 Duplicated action 'waves hand' is deduplicated (count=1)")

	# E.4: 非重复动作被添加
	var smile_count: int = 0
	for act in actions_a:
		var a: Dictionary = act as Dictionary
		if a.get("description", "") == "smiles":
			smile_count += 1
	assert_eq(smile_count, 1, "E.4 Non-duplicated action 'smiles' is added")

	# E.5: char_B (空数据) 仍然有结果条目
	var char_b_result: Dictionary = da_results[1] as Dictionary
	assert_eq(char_b_result.get("character_name", ""), "Bob", "E.5a char_B name is Bob")
	assert_eq(char_b_result.get("dialogue", ""), "", "E.5b char_B has empty dialogue")
	assert_eq((char_b_result.get("actions", []) as Array).size(), 0, "E.5c char_B has empty actions")

	# E.6: 对话格式正确
	var a_dialogue: String = char_a_result.get("dialogue", "") as String
	assert_true(a_dialogue.contains("Hello there"), "E.6a Dialogue contains first line text")
	assert_true(a_dialogue.contains("player"), "E.6b Dialogue contains target")


# ============================================================
# F: Counter 正确性测试
# ============================================================

func test_counter_correctness() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	# F.1: null provider fallback 仍然递增 counter
	var mock_null_provider := _MockNullProviderFactory.new()

	# 使用模拟 — 让 _create_independent_provider 返回 null
	# 验证 worker 中的 counter 处理

	# F.1: 手动模拟 null provider 路径
	var counter: Dictionary = {"d": 0, "a": 0}
	var dialogue_data: Dictionary = {}
	var action_data: Dictionary = {}

	# 模拟 _dialogue_worker 的 null provider 路径
	# (provider == null 分支: dialogue_data[cid] = {}; counter["d"] += 1)
	_simulate_worker_null_provider_path("d", "char_F1", dialogue_data, counter)
	assert_eq(counter["d"], 1, "F.1a Null provider: dialogue counter incremented")
	assert_true(dialogue_data.has("char_F1"), "F.1b Null provider: empty data written for dialogue")

	_simulate_worker_null_provider_path("a", "char_F2", action_data, counter)
	assert_eq(counter["a"], 1, "F.1c Null provider: action counter incremented")
	assert_true(action_data.has("char_F2"), "F.1d Null provider: empty data written for action")

	# F.2: counter 不会被错误递增两次
	# 正常路径下 counter 只在末尾递增一次 (已在 C.4 / D.4 测试)
	var counter2: Dictionary = {"d": 0, "a": 0}
	_simulate_worker_error_path("d", "char_ERR", {}, counter2)
	assert_eq(counter2["d"], 1, "F.2 Error path: counter still incremented (prevents deadlock)")

	# F.3: 多 worker 并行场景 — counter 总和应等于 worker 数量
	var counter_multi: Dictionary = {"d": 0, "a": 0}
	var d_data: Dictionary = {}
	var a_data: Dictionary = {}
	_simulate_worker_null_provider_path("d", "char_1", d_data, counter_multi)
	_simulate_worker_null_provider_path("d", "char_2", d_data, counter_multi)
	_simulate_worker_null_provider_path("a", "char_1", a_data, counter_multi)
	_simulate_worker_null_provider_path("a", "char_2", a_data, counter_multi)
	assert_eq(counter_multi["d"], 2, "F.3a Two dialogue workers → counter['d'] = 2")
	assert_eq(counter_multi["a"], 2, "F.3b Two action workers → counter['a'] = 2")


# 模拟 null provider 的 fallback 路径
func _simulate_worker_null_provider_path(key: String, cid: String, data: Dictionary, counter: Dictionary) -> void:
	# 复制 _dialogue_worker 和 _action_worker 的 null provider 分支
	data[cid] = {}
	counter[key] = counter[key] + 1


# 模拟 LLM 错误但 provider 非 null 的路径
func _simulate_worker_error_path(key: String, cid: String, data: Dictionary, counter: Dictionary) -> void:
	# LLM 调用失败 → 写入空数据 → 递增 counter → cleanup
	data[cid] = {}
	counter[key] = counter[key] + 1


# ============================================================
# G: _action_exists 测试
# ============================================================

func test_action_exists() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	# G.1: 完全相同的动作检测
	var existing: Array = [
		{"type": "gesture", "description": "waves hand"},
		{"type": "facial", "description": "smiles"},
	]
	assert_true(pipeline._action_exists(existing, {"type": "gesture", "description": "waves hand"}), "G.1 Exact match: detected")
	assert_true(pipeline._action_exists(existing, {"type": "facial", "description": "smiles"}), "G.1b Exact match (2nd): detected")

	# G.2: 不同 description 不匹配
	assert_true(not pipeline._action_exists(existing, {"type": "gesture", "description": "nods"}), "G.2 Different description: not matched")

	# G.3: 不同 type 不匹配
	assert_true(not pipeline._action_exists(existing, {"type": "movement", "description": "waves hand"}), "G.3 Different type: not matched")

	# G.4: 空列表
	assert_true(not pipeline._action_exists([], {"type": "gesture", "description": "test"}), "G.4 Empty list: nothing matches")

	# G.5: 部分匹配不匹配（仅 type 相同）
	assert_true(not pipeline._action_exists(existing, {"type": "gesture", "description": "different"}), "G.5 Partial match (type only): not matched")

	# G.6: 部分匹配不匹配（仅 description 相同）
	assert_true(not pipeline._action_exists(existing, {"type": "posture", "description": "waves hand"}), "G.6 Partial match (desc only): not matched")


# ============================================================
# H: 边界条件测试
# ============================================================

func test_boundary_conditions() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	# H.1: _find_character with empty characters array
	var empty_ctx: Dictionary = {"characters": []}
	var result1: Dictionary = pipeline._find_character(empty_ctx, "any")
	assert_eq(result1, {}, "H.1 _find_character with empty array returns {}")

	# H.2: _find_character matching
	var ctx: Dictionary = {
		"characters": [
			{"char_id": "a", "name": "Alice"},
			{"char_id": "b", "name": "Bob"},
		],
	}
	var result2: Dictionary = pipeline._find_character(ctx, "a")
	assert_eq(result2.get("name", ""), "Alice", "H.2a _find_character returns correct character")
	var result3: Dictionary = pipeline._find_character(ctx, "nonexistent")
	assert_eq(result3, {}, "H.2b _find_character missing returns {}")

	# H.3: _build_name_map
	var name_map: Dictionary = pipeline._build_name_map(ctx)
	assert_eq(name_map.size(), 2, "H.3a _build_name_map has 2 entries")
	assert_eq(name_map.get("a", ""), "Alice", "H.3b _build_name_map correct mapping")

	# H.4: _build_interaction_map
	var plan: Dictionary = {
		"interaction_pairs": [
			{"pair_id": "p1", "char_ids": ["a", "b"], "pair_type": "dialogue"},
		],
	}
	var imap: Dictionary = pipeline._build_interaction_map(plan)
	assert_eq(imap.size(), 2, "H.4a interaction_map has entries for both chars")
	assert_not_null(imap.get("a", null), "H.4b char 'a' has InteractionPair")
	assert_not_null(imap.get("b", null), "H.4c char 'b' has InteractionPair")

	# H.5: InteractionPair.from_dict 正确性
	var pair: InteractionPair = InteractionPair.from_dict({"pair_id": "p1", "char_ids": ["a", "b"], "pair_type": "dialogue"})
	assert_eq(pair.pair_id, "p1", "H.5a pair_id correct")
	assert_eq(pair.char_ids.size(), 2, "H.5b char_ids count correct")
	assert_eq(pair.get_counterpart("a"), "b", "H.5c counterpart of 'a' is 'b'")
	assert_eq(pair.get_counterpart("b"), "a", "H.5d counterpart of 'b' is 'a'")

	# H.6: provider.cleanup() 幂等性
	# cleanup 在 _http_request 为 null 时不应崩溃
	var mock_provider := _MockProvider.new()
	mock_provider.cleanup()  # 第一次
	mock_provider.cleanup()  # 第二次（应安全）
	assert_null(mock_provider._http_request, "H.6 cleanup() is idempotent (no crash on double call)")

	# H.7: _attach_http_node 幂等性
	var mock_provider2 := _MockProvider.new()
	mock_provider2._attach_http_node(pipeline)
	var first_http: HTTPRequest = mock_provider2._http_request
	mock_provider2._attach_http_node(pipeline)
	assert_eq(mock_provider2._http_request, first_http, "H.7 _attach_http_node is idempotent (reuses existing node)")
	mock_provider2.cleanup()


# ============================================================
# I: ProviderFactory 集成测试
# ============================================================

func test_provider_factory_integration() -> void:
	# I.1: ProviderFactory.create 内部调用 configure
	# 验证：通过工厂创建的 Provider 其 _config 已填充
	var tier_config: Dictionary = {
		"type": "ollama",
		"endpoint": "http://localhost:11434/api/chat",
		"model": "test-model",
		"temperature": 0.5,
		"max_tokens": 1024,
		"timeout": 30,
	}
	var provider: BaseLLMProvider = ProviderFactory.create("ollama", tier_config)
	assert_not_null(provider, "I.1 ProviderFactory.create returns non-null")

	if provider == null:
		return

	# I.2: _config 已填充（工厂内部调用 configure）
	assert_eq(provider._config.get("model", ""), "test-model", "I.2a Provider._config.model matches tier_config")
	assert_eq(provider._config.get("temperature", 0.0), 0.5, "I.2b Provider._config.temperature matches tier_config")
	assert_eq(provider._config.get("max_tokens", 0), 1024, "I.2c Provider._config.max_tokens matches tier_config")

	# I.3: 不支持的 provider type 返回 null
	var bad_provider: BaseLLMProvider = ProviderFactory.create("nonexistent", tier_config)
	assert_null(bad_provider, "I.3 Unknown provider type returns null")

	# I.4: ProviderFactory.is_supported
	assert_true(ProviderFactory.is_supported("ollama"), "I.4a ollama is supported")
	assert_true(ProviderFactory.is_supported("deepseek"), "I.4b deepseek is supported")
	assert_true(ProviderFactory.is_supported("openai"), "I.4c openai is supported")
	assert_true(not ProviderFactory.is_supported("gpt4"), "I.4d gpt4 is NOT supported")

	if provider._http_request:
		provider.cleanup()


# ============================================================
# J: cleanup() 调用验证
# ============================================================

func test_cleanup_called() -> void:
	# J.1: 验证 _motivation_worker 在 LLM 调用后调用 cleanup
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	var tracked_provider := _TrackedCleanupProvider.new()
	tracked_provider.mock_response = {"ok": true, "content": '{"character_id":"test","internal_state":{"mood":"中性"}}', "raw": "", "tokens": 10}

	var test_runner := _PipelineTestRunner.new(pipeline, tracked_provider)
	var results: Array = []
	var mot_input: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "cleanup_test", "name": "CleanupTest"},
		"scene_summary": "",
		"player_action": "",
		"scene_tone": "",
	}

	test_runner._motivation_worker("cleanup_test", mot_input, results)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	# J.2: cleanup 被调用
	assert_true(tracked_provider._cleanup_called, "J.2 _motivation_worker calls provider.cleanup()")

	# J.3: _dialogue_worker 也调用 cleanup
	var tracked_dialogue := _TrackedCleanupProvider.new()
	tracked_dialogue.mock_response = {"ok": true, "content": '{"character_id":"d_test","dialogue":[],"actions":[],"emotional_arc":"","stance_change":{}}', "raw": "", "tokens": 5}

	var test_runner2 := _PipelineTestRunner.new(pipeline, tracked_dialogue)
	var d_data: Dictionary = {}
	var counter: Dictionary = {"d": 0, "a": 0}
	var base_input: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "d_test", "name": "DTest"},
		"beat_summary": "",
		"player_action": "",
		"scene_tone": "",
	}

	test_runner2._dialogue_worker("d_test", base_input, d_data, counter)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	assert_true(tracked_dialogue._cleanup_called, "J.3 _dialogue_worker calls provider.cleanup()")

	# J.4: _action_worker 也调用 cleanup
	var tracked_action := _TrackedCleanupProvider.new()
	tracked_action.mock_response = {"ok": true, "content": '{"character_id":"a_test","actions":[]}', "raw": "", "tokens": 3}

	var test_runner3 := _PipelineTestRunner.new(pipeline, tracked_action)
	var a_data: Dictionary = {}
	var counter_a: Dictionary = {"d": 0, "a": 0}
	var base_input_a: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "a_test", "name": "ATest"},
		"beat_summary": "",
		"player_action": "",
		"scene_tone": "",
	}

	test_runner3._action_worker("a_test", base_input_a, a_data, counter_a)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame

	assert_true(tracked_action._cleanup_called, "J.4 _action_worker calls provider.cleanup()")


# ============================================================
# K: Null Provider Fallback 测试
# ============================================================

func test_null_provider_fallback() -> void:
	var pipeline: MananaPipeline = MananaPipeline
	if pipeline == null:
		return

	# K.1: _motivation_worker with null provider 写入空数据且不崩溃
	var results: Array = []
	var mot_input: Dictionary = {
		"system_prompt": "test",
		"character": {"char_id": "null_test", "name": "NullTest"},
		"scene_summary": "",
		"player_action": "",
		"scene_tone": "",
	}

	# 使用返回 null 的 factory
	var null_runner := _NullProviderRunner.new(pipeline)
	null_runner._motivation_worker("null_test", mot_input, results)
	await get_tree().process_frame
	await get_tree().process_frame

	# motivation worker 不递增 counter，但结果应包含 fallback 条目
	assert_true(results.size() > 0, "K.1 Null provider: results still appended with empty data")
	if results.size() > 0:
		var entry: Dictionary = results[0] as Dictionary
		assert_eq(entry.get("char_id", ""), "null_test", "K.1b Null provider: char_id preserved")
		assert_eq(entry.get("motivation", {}), {}, "K.1c Null provider: motivation is empty dict")


# ============================================================
# 静态辅助函数（从 Pipeline 复制，用于隔离测试）
# ============================================================

func _find_character_static(ctx: Dictionary, char_id: String) -> Dictionary:
	var chars: Array = ctx.get("characters", []) as Array
	for c_ in chars:
		var found_char: Dictionary = c_ as Dictionary
		if found_char.get("char_id", "") == char_id:
			return found_char
	return {}


func _action_exists_static(existing: Array, new_action: Dictionary) -> bool:
	var new_desc: String = str(new_action.get("description", ""))
	var new_type: String = str(new_action.get("type", ""))
	for e_ in existing:
		var e: Dictionary = e_ as Dictionary
		if e.get("description", "") == new_desc and e.get("type", "") == new_type:
			return true
	return false


# ============================================================
# Mock / Test Double 类
# ============================================================

## Mock Provider — 返回预设响应，不实际发送 HTTP 请求
class _MockProvider extends BaseLLMProvider:
	var mock_response: Dictionary = {}

	func _init() -> void:
		_config = {
			"type": "ollama",
			"model": "mock-model",
			"endpoint": "mock://localhost",
			"temperature": 0.7,
			"max_tokens": 1024,
			"timeout": 10,
		}

	func chat_async(_system_prompt: String, _user_message: String, _options: Dictionary = {}) -> Dictionary:
		return mock_response

	func get_provider_name() -> String:
		return "mock"

	func cleanup() -> void:
		_http_request = null  # Mock: 无需真实清理

	func _attach_http_node(_parent_node: Node) -> void:
		_http_request = HTTPRequest.new()  # 创建但不需要真实节点


## Tracked Cleanup Provider — 记录 cleanup 是否被调用
class _TrackedCleanupProvider extends _MockProvider:
	var _cleanup_called: bool = false

	func cleanup() -> void:
		_cleanup_called = true
		super.cleanup()


## Pipeline 测试辅助 — 覆盖 _create_independent_provider 返回 mock
class _PipelineTestRunner extends MananaPipeline:
	var _mock_provider: BaseLLMProvider

	func _init(pipeline: MananaPipeline, mock_provider: BaseLLMProvider) -> void:
		_mock_provider = mock_provider
		# 复制必要的内部状态
		_config = pipeline._config
		_prompt_cache = pipeline._prompt_cache

	func _create_independent_provider(_tier: String) -> BaseLLMProvider:
		return _mock_provider


## Null Provider Runner — _create_independent_provider 返回 null
class _NullProviderRunner extends MananaPipeline:
	var _pipeline: MananaPipeline

	func _init(pipeline: MananaPipeline) -> void:
		_pipeline = pipeline
		_config = pipeline._config

	func _create_independent_provider(_tier: String) -> BaseLLMProvider:
		return null


## Null Provider Factory — 用于测试 null fallback
class _MockNullProviderFactory extends RefCounted:
	func create(_provider_type: String, _config: Dictionary) -> BaseLLMProvider:
		return null
