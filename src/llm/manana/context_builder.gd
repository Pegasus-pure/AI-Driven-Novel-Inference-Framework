class_name ContextBuilder
extends RefCounted

## Layer 0 — 从 WorldState 构建 SceneContext JSON。
## 纯 Godot 逻辑，不调用 LLM。所有数据通过 WorldState 引用传入（便于测试）。
##
## 注意: WorldState Autoload 可能缺少某些数据查询方法。
## 标记为 TODO_WS_* 的方法需要在 T05 中同步实现到 WorldState。

# ============================================================
# 公开方法
# ============================================================

## 从 WorldState 构建完整的 SceneContext Dictionary。
## [param player_action] 玩家当前输入
## [param world_state] WorldState Autoload 引用 (Node)，通过参数传入而非全局访问
## [param beat_id] 当前节拍 ID（Pipeline 传入）
## [param scene_id] 当前场景 ID（可选）
## [param location_info] 当前地点详细信息（可选，从 Canon 传入）
## [returns] 完整 SceneContext Dictionary，符合 MananaSchema.SCENE_CONTEXT_SCHEMA
func build(
	player_action: String,
	world_state: Node,
	beat_id: String = "",
	scene_id: String = "",
	location_info: Dictionary = {}
) -> Dictionary:
	# 提取各子系统数据
	var player: Dictionary = _build_player_context(player_action, world_state)
	var chars: Array = _build_character_context(world_state)
	var threads: Array = _build_thread_context(world_state)
	var location: Dictionary = _build_location_context(world_state, location_info)
	var history: Array = _build_history_context(world_state)
	var memory: Dictionary = _build_memory_context(world_state)
	var divergence: float = _get_divergence(world_state)
	var world_rules: String = _build_world_rules_context(world_state)

	var game_time: String = str(_get_property(world_state, "game_time", ""))

	return MananaSchema.build_scene_context(
		chars, threads, location, player, history, memory,
		divergence, world_rules, beat_id, scene_id, game_time
	)


# ============================================================
# 私有构建方法
# ============================================================

## 构建 player 子树: action, profile, reputation
func _build_player_context(action: String, ws: Node) -> Dictionary:
	var profile: Dictionary = _get_property(ws, "player_profile", {}) as Dictionary
	var reputation: Dictionary = _get_property(ws, "player_reputation", {}) as Dictionary

	# 将好感度数值转换为人可读的文本描述
	var reputation_text: Dictionary = {}
	for char_id in reputation:
		var val: float = reputation[char_id] as float
		reputation_text[char_id] = _reputation_to_text(val)

	return {
		"action": action,
		"profile": profile.duplicate(true),
		"reputation": reputation_text,
	}


## 构建角色列表: 从 WorldState 中提取当前场景相关的角色信息
func _build_character_context(ws: Node) -> Array:
	var result: Array = []
	var characters_state: Dictionary = _get_property(ws, "characters_state", {}) as Dictionary
	var canon: Dictionary = _get_property(ws, "canon", {}) as Dictionary
	var canon_chars: Array = canon.get("characters", []) as Array
	var player_location: String = str(_get_property(ws, "player_location", ""))
	var dynamic_npcs: Dictionary = _get_property(ws, "dynamic_npcs", {}) as Dictionary

	# 构建 canon 角色查找表 {char_id: canon_data}
	var canon_lookup: Dictionary = {}
	for c_ in canon_chars:
		var c: Dictionary = c_ as Dictionary
		var cid: String = str(c.get("id", ""))
		if cid != "":
			canon_lookup[cid] = c

	# 处理 WorldState 中已有的角色
	for char_id in characters_state:
		var cs: Dictionary = characters_state[char_id] as Dictionary
		var entry: Dictionary = _build_single_character(char_id, cs, canon_lookup, ws, player_location)
		if not entry.is_empty():
			result.append(entry)

	# 处理动态 NPC（尚未出现在 characters_state 中的）
	for npc_id in dynamic_npcs:
		if characters_state.has(npc_id):
			continue  # 已经在上面处理过
		var npc: Dictionary = dynamic_npcs[npc_id] as Dictionary
		# 仅在当前地点或附近时加入
		var npc_loc: String = str(npc.get("location", ""))
		if npc_loc == player_location or player_location == "":
			result.append({
				"char_id": npc_id,
				"name": npc.get("name", "??"),
				"personality": "",
				"role": npc.get("role", ""),
				"current_state": {
					"location": npc_loc,
					"mood": "中性",
					"goal": "",
				},
				"known_facts": [],
				"relation_to_player": "中立",
				"is_dynamic": true,
			})

	return result


## 构建单个角色条目
func _build_single_character(
	char_id: String,
	cs: Dictionary,
	canon_lookup: Dictionary,
	ws: Node,
	player_location: String
) -> Dictionary:
	# 获取 canon 数据中的角色名和性格
	var canon_data: Dictionary = canon_lookup.get(char_id, {}) as Dictionary
	var name: String = _safe_string(canon_data.get("name", char_id))
	var personality: String = _safe_string(canon_data.get("personality", ""))
	var role: String = _safe_string(canon_data.get("role", ""))

	# 获取角色对玩家的好感度文本
	var char_rep_text: String = ""
	if ws.has_method("get_reputation_text"):
		char_rep_text = ws.get_reputation_text(char_id) as String
	elif ws.has_method("get_reputation"):
		# fallback: 手动计算
		var rep_val: float = 0.0
		if ws.has_method("get_reputation"):
			rep_val = ws.get_reputation(char_id) as float
		char_rep_text = _reputation_to_text(rep_val)

	# 获取角色已知事实
	var known_facts: Array = []
	if ws.has_method("get_known_facts"):
		known_facts = ws.get_known_facts(char_id) as Array

	# 组装当前状态
	var current_state: Dictionary = {
		"location": str(cs.get("location", "")),
		"mood": str(cs.get("mood", "中性")),
		"goal": str(cs.get("goal", "")),
	}

	return {
		"char_id": char_id,
		"name": name,
		"personality": personality,
		"role": role,
		"current_state": current_state,
		"known_facts": known_facts,
		"relation_to_player": char_rep_text,
		"anti_rules": _get_anti_rules(char_id, canon_lookup),
		"is_dynamic": false,
	}


## 构建活跃叙事线索上下文
func _build_thread_context(ws: Node) -> Array:
	var active_threads: Array = []
	if ws.has_method("get_active_threads"):
		active_threads = ws.get_active_threads() as Array
	else:
		var threads_dict: Dictionary = _get_property(ws, "narrative_threads", {}) as Dictionary
		active_threads = threads_dict.get("active", []) as Array

	# 精简每个线索的数据，只保留 LLM 需要的字段
	var thread_result: Array = []
	for t_ in active_threads:
		var t: Dictionary = t_ as Dictionary
		thread_result.append({
			"id": str(t.get("id", "")),
			"title": str(t.get("title", "")),
			"type": str(t.get("type", "")),
			"progress": t.get("progress", 0.0) as float,
			"question": str(t.get("question", "")),
			"involved_characters": t.get("involved_characters", []) as Array,
			"tension": t.get("tension", 0.3) as float,
			"player_attention": t.get("player_attention", 0.5) as float,
			"priority": t.get("priority", 0.5) as float,
		})

	return thread_result


## 构建最近叙事历史
func _build_history_context(ws: Node) -> Array:
	var raw_history: Array = _get_property(ws, "narrative_history", []) as Array
	var recent_count: int = mini(raw_history.size(), 5)
	var history_result: Array = []

	var start: int = raw_history.size() - recent_count
	for i in range(start, raw_history.size()):
		var evt: Dictionary = raw_history[i] as Dictionary
		history_result.append({
			"time": str(evt.get("time", "")),
			"summary": str(evt.get("summary", "")),
			"event_id": str(evt.get("event_id", "")),
		})

	return history_result


## 构建分层记忆上下文
func _build_memory_context(ws: Node) -> Dictionary:
	var scene_mem: Array = _get_property(ws, "scene_memory", []) as Array
	var long_mem: Array = _get_property(ws, "long_term_memory", []) as Array

	return {
		"scene_memory": scene_mem.duplicate(),
		"long_term_memory": long_mem.duplicate(),
	}


## 构建当前地点上下文
func _build_location_context(ws: Node, location_info: Dictionary) -> Dictionary:
	if not location_info.is_empty():
		return location_info.duplicate()

	# 从 WorldState 和 Canon 构建基本地点信息
	var loc_player_location: String = str(_get_property(ws, "player_location", ""))
	var loc_canon: Dictionary = _get_property(ws, "canon", {}) as Dictionary
	var locations: Array = loc_canon.get("locations", []) as Array

	# 尝试从 canon 中找到匹配的地点
	for loc_ in locations:
		var loc: Dictionary = loc_ as Dictionary
		if str(loc.get("id", "")) == loc_player_location or str(loc.get("name", "")) == loc_player_location:
			return {
				"id": str(loc.get("id", "")),
				"name": str(loc.get("name", "")),
				"description": str(loc.get("description", "")),
				"atmosphere": str(loc.get("atmosphere", "")),
			}

	# fallback: 只返回地点名称
	return {
		"id": loc_player_location,
		"name": loc_player_location,
		"description": "",
		"atmosphere": "",
	}


## 构建世界规则上下文（取启用的规则拼接）
func _build_world_rules_context(ws: Node) -> String:
	var rules: Array = _get_property(ws, "custom_world_rules", []) as Array
	var enabled_rules: Array = []

	for r_ in rules:
		var r: Dictionary = r_ as Dictionary
		if r.get("enabled", false) as bool:
			var content: String = str(r.get("content", ""))
			if content != "":
				enabled_rules.append(content)

	if enabled_rules.size() == 0:
		return ""
	return "\n".join(enabled_rules)


## 获取世界偏离度
func _get_divergence(ws: Node) -> float:
	if ws.has_method("get_divergence"):
		return ws.get_divergence() as float
	return _get_property(ws, "world_variables", {}).get("世界偏离度", 0.0) as float


## 从 canon 数据中提取角色的 anti_rules
func _get_anti_rules(char_id: String, canon_lookup: Dictionary) -> Array:
	var canon_data: Dictionary = canon_lookup.get(char_id, {}) as Dictionary
	if canon_data.is_empty():
		return []
	var personality: Dictionary = canon_data.get("personality", {}) as Dictionary
	return personality.get("anti_rules", []) as Array


# ============================================================
# 辅助方法

## 安全转换为字符串，兼容 Dictionary/Array 类型
func _safe_string(value: Variant) -> String:
	if value is String:
		return value
	if value is Dictionary or value is Array:
		return JSON.stringify(value)
	return str(value)
# ============================================================

## 安全获取 Node 的属性值
func _get_property(node: Node, prop: String, default: Variant) -> Variant:
	if node == null:
		return default
	return node.get(prop) if prop in node else default


## 将好感度数值转为人可读的态度描述
func _reputation_to_text(value: float) -> String:
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
