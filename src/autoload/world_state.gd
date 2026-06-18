extends Node

## 世界状态管理器 (Autoload 单例)
## 追踪游戏时间、角色状态、叙事线索、世界变量等运行时状态
##
## 所有状态读写通过此单例，确保数据一致性
## 对外通过 EventBus signal 广播状态变化

# ===== 时间系统 =====
var game_time: String = "第一月·第一日·清晨"
var time_index: int = 0               # 内部时间刻度，每次场景推进 +1

# ===== 玩家状态 =====
var player_location: String = ""
var player_known_info: Array = []     # String[]
var player_reputation: Dictionary = {} # {char_id: float}
var player_inventory: Array = []
var player_profile: Dictionary = {    # LLM 动态构建的玩家人格卡
	"traits": ["好奇", "谨慎"],
	"motivation": "搞清楚自己为何来到这个世界",
	"tendency": "中立"
}

# ===== 角色状态 =====
# {char_id: {location, hp, goal, mood, relations: {char_id: float}}}
var characters_state: Dictionary = {}

# ===== 叙事线索池 =====
var narrative_threads: Dictionary = {
	"active": [],
	"closed": []
}

var thread_pool_config: Dictionary = {
	"max_active_main": 1,
	"max_active_side": 2,
	"max_child_threads": 5,
	"close_stale_after_scenes": 30,
	"min_progress_per_scene": 0.05
}

# ===== 世界变量 =====
var world_variables: Dictionary = {
	"世界偏离度": 0.0
}

# ===== 叙事历史 =====
var narrative_history: Array = []     # [{time, summary, event_id}]

# ===== 分层记忆 =====
var scene_memory: Array = []          # 当前场景关键事件摘要（压缩版）
var long_term_memory: Array = []      # 跨场景重要事件摘要（关键词压缩版）
const MAX_SCENE_MEMORY: int = 5
const MAX_LONG_TERM: int = 8

# ===== 运行时 Canon（动态快照，反映游戏运行后的世界变化）=====
var dynamic_canon: Dictionary = {
	"character_states": {},    # {char_id: {location, mood, alive, note}}
	"closed_threads": [],      # [{title, closed_at}]
	"new_npcs": [],            # [{name, role, location}]
	"divergence_events": []    # ["事件描述1", "事件描述2"]
}

# ===== 动态 NPC（LLM 在叙事中创造的路人角色）=====
var dynamic_npcs: Dictionary = {}     # {dyn_001: {name, location, role, traits, first_met}} 上限10

# ===== 知识图谱（跨 NPC 信息隔离）=====
var knowledge_graph: Array = []  # [{fact_id, content, known_by: [char_ids], time}]
const MAX_KNOWLEDGE_FACTS: int = 20

# ===== 自定义世界规则（F7 编辑器）=====
var custom_world_rules: Array = []  # [{keys, content, enabled, priority}]

# ===== 正典引用 =====
var canon: Dictionary = {}            # Canon.json 内容，由 CanonLoader 填充


func _ready() -> void:
	_connect_signals()


func _connect_signals() -> void:
	EventBus.narrative_ready.connect(_on_narrative_ready)
	EventBus.player_action_submitted.connect(_on_player_action)
	EventBus.thread_updated.connect(_on_thread_updated)


# ===== 时间操作 =====

func advance_time(ticks: int = 1) -> void:
	time_index += ticks
	decay_npc_moods()
	_update_game_time_string()


func _update_game_time_string() -> void:
	var month: int = (time_index / 30) + 1
	var day: int = (time_index % 30) + 1
	var time_of_day: String = _time_of_day_str(time_index % 4)
	game_time = "第%d月·第%d日·%s" % [month, day, time_of_day]
	EventBus.world_time_changed.emit(game_time)


func _time_of_day_str(quarter: int) -> String:
	match quarter:
		0: return "清晨"
		1: return "正午"
		2: return "黄昏"
		3: return "深夜"
	return "正午"


# ===== 角色操作 =====

func get_character_state(char_id: String) -> Dictionary:
	return characters_state.get(char_id, {}) as Dictionary


func set_character_state(char_id: String, state: Dictionary) -> void:
	characters_state[char_id] = state
	EventBus.character_state_changed.emit(char_id)


func update_character_field(char_id: String, field: String, value: Variant) -> void:
	if not characters_state.has(char_id):
		characters_state[char_id] = {"relations": {}}
	characters_state[char_id][field] = value
	EventBus.character_state_changed.emit(char_id)


# ===== NPC 情绪系统 =====

const MOODS: Array = ["中性", "喜悦", "愤怒", "恐惧", "悲伤", "好奇"]

func set_npc_mood(char_id: String, mood: String, intensity: float, cause: String) -> void:
	if not characters_state.has(char_id):
		characters_state[char_id] = {"relations": {}}
	characters_state[char_id]["mood"] = mood
	characters_state[char_id]["mood_intensity"] = clampf(intensity, 0.0, 1.0)
	characters_state[char_id]["mood_cause"] = cause


func decay_npc_moods() -> void:
	for cid in characters_state:
		var cs: Dictionary = characters_state[cid] as Dictionary
		if not cs.has("mood_intensity"):
			continue
		var intensity: float = cs.get("mood_intensity", 0.0) as float
		intensity -= 0.05
		if intensity <= 0.0:
			cs["mood"] = "中性"
			cs["mood_intensity"] = 0.0
			cs["mood_cause"] = ""
		else:
			cs["mood_intensity"] = intensity


func get_npc_mood_text(char_id: String) -> String:
	var char_st: Dictionary = characters_state.get(char_id, {}) as Dictionary
	var mood: String = str(char_st.get("mood", "中性"))
	var mood_intensity_val: float = char_st.get("mood_intensity", 0.0) as float
	if mood_intensity_val < 0.2 or mood == "中性":
		return ""
	var cause: String = str(char_st.get("mood_cause", ""))
	var text: String = "当前情绪：%s" % mood
	if cause != "":
		text += " · 因为" + cause
	return text


func _apply_mood_from_rep(char_id: String, delta: float) -> void:
	if abs(delta) < 0.05:
		return
	if delta > 0:
		set_npc_mood(char_id, "喜悦", clampf(abs(delta) * 3, 0.3, 1.0), "你对他的态度改善")
	else:
		set_npc_mood(char_id, "愤怒", clampf(abs(delta) * 3, 0.3, 1.0), "你对他的态度恶化")


# ===== 知识图谱 =====

func add_knowledge(content: String, known_by: Array) -> void:
	if content == "":
		return
	var fid: String = "fact_%d" % knowledge_graph.size()
	knowledge_graph.append({
		"fact_id": fid,
		"content": content,
		"known_by": known_by.duplicate(),
		"time": game_time
	})
	if knowledge_graph.size() > MAX_KNOWLEDGE_FACTS:
		knowledge_graph.pop_front()


func get_known_facts(char_id: String) -> Array:
	var facts: Array = []
	for entry in knowledge_graph:
		var e: Dictionary = entry as Dictionary
		var known: Array = e.get("known_by", []) as Array
		if known.has(char_id) or known.has("all"):
			facts.append(e["content"])
	return facts


func get_known_facts_text(char_id: String) -> String:
	var known_facts: Array = get_known_facts(char_id)
	if known_facts.size() == 0:
		return ""
	return "；".join(known_facts)


func set_relation(char_a: String, char_b: String, value: float) -> void:
	if not characters_state.has(char_a):
		characters_state[char_a] = {"relations": {}}
	if not characters_state[char_a].has("relations"):
		characters_state[char_a]["relations"] = {}
	characters_state[char_a]["relations"][char_b] = value


func get_relation(char_a: String, char_b: String) -> float:
	var rel_char_st: Dictionary = characters_state.get(char_a, {}) as Dictionary
	var rels: Dictionary = rel_char_st.get("relations", {}) as Dictionary
	return rels.get(char_b, 0.0) as float


# ===== 玩家声誉 =====

## 调整玩家对某角色的好感度 (delta: -0.3 到 +0.3)
func adjust_player_reputation(char_id: String, delta: float) -> void:
	var current: float = player_reputation.get(char_id, 0.0) as float
	var new_val: float = clamp(current + delta, -1.0, 1.0)
	player_reputation[char_id] = new_val
	_recalculate_divergence()


## 将好感度转为人可读的态度描述
func get_reputation_text(char_id: String) -> String:
	var val: float = player_reputation.get(char_id, 0.0) as float
	if val >= 0.7:
		return "对你非常友善，主动相助"
	elif val >= 0.3:
		return "对你有好感，愿意交谈"
	elif val >= -0.3:
		return "态度中立，不咸不淡"
	elif val >= -0.7:
		return "对你冷淡，话不投机"
	else:
		return "对你敌视，随时可能翻脸"


# 剧情1: 叙事线索操作

func add_thread(thread: Dictionary) -> String:
	var active: Array = narrative_threads["active"] as Array
	active.append(thread)
	EventBus.thread_updated.emit(thread["id"])
	return thread["id"]


func advance_thread(thread_id: String, progress_delta: float) -> void:
	var active_threads: Array = narrative_threads["active"] as Array
	for i in active_threads.size():
		var t: Dictionary = active_threads[i] as Dictionary
		if t["id"] == thread_id:
			t["progress"] = min(1.0, (t["progress"] as float) + progress_delta)
			t["last_advanced_at"] = game_time
			if t["progress"] >= 1.0:
				_close_thread(i)
			else:
				EventBus.thread_updated.emit(thread_id)
			return


func _close_thread(active_index: int) -> void:
	var close_active: Array = narrative_threads["active"] as Array
	var closed: Array = narrative_threads["closed"] as Array
	var close_entry: Dictionary = close_active[active_index] as Dictionary
	close_entry["closed_at"] = game_time
	closed.append(close_entry)
	close_active.remove_at(active_index)
	EventBus.thread_updated.emit(close_entry["id"])
	_recalculate_divergence()


## 按 ID 关闭线索（LLM 触发）
func close_thread_by_id(thread_id: String) -> void:
	var by_id_active: Array = narrative_threads["active"] as Array
	for i in by_id_active.size():
		var by_id_entry: Dictionary = by_id_active[i] as Dictionary
		if by_id_entry["id"] == thread_id:
			_close_thread(i)
			return


## 从叙事中创建新线索（LLM 触发）
func create_thread_from_narrative(title: String, ttype: String) -> void:
	var create_active: Array = narrative_threads["active"] as Array
	var thread_count: int = create_active.size()

	# 自动生成唯一 ID
	var ids: Array = []
	for t_ in create_active:
		var create_entry: Dictionary = t_ as Dictionary
		ids.append(create_entry["id"])
	var new_id: String = "thread_dyn_%d" % (create_active.size() + 1)
	while new_id in ids:
		new_id = "thread_dyn_%d" % (ids.size() + 1)
		ids.append(new_id)

	# 超限时关闭最不重要的线索
	if thread_count >= 3:
		var to_close: int = -1
		var lowest_priority: float = 1.0
		for i in create_active.size():
			var low_pri_entry: Dictionary = create_active[i] as Dictionary
			var pri: float = low_pri_entry.get("priority", 0.5) as float
			if pri < lowest_priority:
				lowest_priority = pri
				to_close = i
		if to_close >= 0:
			_close_thread(to_close)

	add_thread({
		"id": new_id,
		"title": title,
		"type": ttype if ttype in ["main", "side"] else "side",
		"progress": 0.05,
		"question": "",
		"involved_characters": [],
		"involved_locations": [],
		"parent_thread": "",
		"child_threads": [],
		"key_milestones": [],
		"tension": 0.3,
		"player_attention": 0.5,
		"priority": 0.5,
		"created_at": game_time,
		"last_advanced_at": game_time
	})


func get_active_threads() -> Array:
	return narrative_threads["active"] as Array


func get_thread(thread_id: String) -> Dictionary:
	for t in narrative_threads["active"]:
		var thread_data: Dictionary = t as Dictionary
		if thread_data["id"] == thread_id:
			return thread_data
	for t in narrative_threads["closed"]:
		var closed_data: Dictionary = t as Dictionary
		if closed_data["id"] == thread_id:
			return closed_data
	return {}


func get_threads_summary() -> String:
	var lines: Array = []
	for t in narrative_threads["active"]:
		var summary_data: Dictionary = t as Dictionary
		lines.append("- [%s] %s (%.0f%%)" % [summary_data["id"], summary_data["title"], summary_data["progress"] * 100])
	return "\n".join(lines)


## 设置指定线索的张力值
func set_thread_tension(thread_id: String, new_tension: float) -> void:
	var tension_active: Array = narrative_threads["active"] as Array
	for i in tension_active.size():
		var tension_entry: Dictionary = tension_active[i] as Dictionary
		if tension_entry["id"] == thread_id:
			tension_entry["tension"] = clampf(new_tension, 0.0, 1.0)
			return


# ===== 叙事历史 =====

func add_narrative_event(summary: String, event_id: String = "") -> void:
	narrative_history.append({
		"time": game_time,
		"summary": summary,
		"event_id": event_id
	})


func get_recent_history(num_events: int = 5) -> String:
	var history_lines: Array = []
	var history: Array = narrative_history as Array
	var start: int = max(0, history.size() - num_events)
	for i in range(start, history.size()):
		var evt: Dictionary = history[i] as Dictionary
		history_lines.append("[%s] %s" % [evt["time"], evt["summary"]])
	return "\n".join(history_lines)


# ===== 世界偏离度 =====

func set_divergence(value: float) -> void:
	world_variables["世界偏离度"] = clamp(value, 0.0, 1.0)


## 自动重算偏离度：基于线索关闭数 + 声誉离散度
func _recalculate_divergence() -> void:
	var closed_threads_arr: Array = narrative_threads["closed"] as Array
	var recalc_active: Array = narrative_threads["active"] as Array

	# 每条已关闭的线索贡献 0.08
	var thread_contribution: float = min(closed_threads_arr.size() * 0.08, 0.5)

	# 活跃线索的进度也贡献（完成度越高偏离越大）
	var active_contribution: float = 0.0
	for t_ in recalc_active:
		var recalc_entry: Dictionary = t_ as Dictionary
		active_contribution += (recalc_entry.get("progress", 0.0) as float) * 0.1

	# 声誉离散度（玩家对 NPC 态度差异越大，偏离越高）
	var rep_spread: float = 0.0
	var rep_vals: Array = []
	for v in player_reputation.values():
		rep_vals.append(abs(v as float))
	if rep_vals.size() >= 2:
		rep_vals.sort()
		rep_spread = (rep_vals[rep_vals.size() - 1] as float) * 0.15

	var dv: float = clamp(thread_contribution + active_contribution + rep_spread, 0.0, 1.0)
	set_divergence(dv)


func get_divergence() -> float:
	return world_variables.get("世界偏离度", 0.0) as float


## 返回偏离度的人可读描述，供 LLM 理解当前世界状态
func get_divergence_text() -> String:
	var divergence_val: float = get_divergence()
	if divergence_val < 0.1:
		return "世界紧密沿着原著轨迹运行"
	elif divergence_val < 0.3:
		return "局部微小偏离，整体风向未变"
	elif divergence_val < 0.5:
		return "中度偏离，部分关键事件已偏离原著"
	elif divergence_val < 0.7:
		return "重大偏离，原著轨迹已不可靠"
	else:
		return "世界已彻底脱离原著，未来完全未知"


# ===== 动态 Canon 同步 =====

## 每次关键事件后调用，更新运行时 canon 快照
func sync_dynamic_canon() -> void:
	# 同步角色状态
	var chars: Array = canon.get("characters", []) as Array
	for c_ in chars:
		var c: Dictionary = c_ as Dictionary
		var cid: String = str(c.get("id", ""))
		var sync_char_st: Dictionary = get_character_state(cid)
		dynamic_canon["character_states"][cid] = {
			"name": str(c.get("name", "")),
			"original_role": str(c.get("role", "")),
			"current_location": str(sync_char_st.get("location", str(c.get("starting_location", "")))),
			"current_mood": str(sync_char_st.get("mood", "正常")),
			"alive": sync_char_st.get("alive", true) as bool,
			"reputation": player_reputation.get(cid, 0.0) as float
		}

	# 同步已关闭线索
	var threads: Dictionary = narrative_threads as Dictionary
	var sync_closed_arr: Array = threads.get("closed", []) as Array
	dynamic_canon["closed_threads"] = []
	for t_ in sync_closed_arr:
		var sync_entry: Dictionary = t_ as Dictionary
		dynamic_canon["closed_threads"].append({
			"title": str(sync_entry.get("title", "??")),
			"closed_at": game_time
		})

	# 同步动态 NPC
	dynamic_canon["new_npcs"] = []
	for npc_id in dynamic_npcs:
		var n: Dictionary = dynamic_npcs[npc_id] as Dictionary
		dynamic_canon["new_npcs"].append({
			"name": str(n.get("name", "??")),
			"role": str(n.get("role", "?")),
			"location": str(n.get("location", "?")),
			"first_met": str(n.get("first_met", ""))
		})


## 返回动态 canon 和静态 canon 的差异摘要（供 prompt 使用）
func get_canon_diff_text() -> String:
	if dynamic_canon["character_states"].size() == 0 and dynamic_canon["closed_threads"].size() == 0:
		return ""
	var diff_lines: Array = []
	var char_states: Dictionary = dynamic_canon["character_states"] as Dictionary
	for cid in char_states:
		var diff_char_st: Dictionary = char_states[cid] as Dictionary
		var note: String = ""
		if diff_char_st.get("current_mood", "正常") != "正常":
			note += "情绪: %s " % diff_char_st["current_mood"]
		var rep: float = diff_char_st.get("reputation", 0.0) as float
		if abs(rep) > 0.1:
			note += "对你的态度: %+.1f " % rep
		if note != "":
			diff_lines.append("  %s — %s" % [diff_char_st["name"], note])

	if diff_lines.size() > 0:
		diff_lines.insert(0, "[世界已发生的变化]")
	return "\n".join(diff_lines)


# ===== 分层记忆 =====

## 添加事件到 Scene Memory（LLM 每次叙事完成后调用）
func add_to_scene_memory(summary: String) -> void:
	scene_memory.append(summary)
	if scene_memory.size() > MAX_SCENE_MEMORY:
		var old: String = scene_memory.pop_front() as String
		add_to_long_term(old)


## 场景切换时压缩 Scene Memory → Long-term
func compress_scene_memory() -> void:
	for summary in scene_memory:
		add_to_long_term(summary as String)
	scene_memory.clear()


func add_to_long_term(summary: String) -> void:
	if summary == "":
		return
	long_term_memory.append(summary)
	if long_term_memory.size() > MAX_LONG_TERM:
		long_term_memory.pop_front()


## 获取分层记忆文本（供 prompt 使用）
func get_memory_text() -> String:
	var mem_lines: Array = []
	if scene_memory.size() > 0:
		mem_lines.append("[场景记忆] 最近发生在本场景的事件：%s" % " · ".join(scene_memory))
	if long_term_memory.size() > 0:
		mem_lines.append("[长期记忆] 过去的重大事件：%s" % " · ".join(long_term_memory.slice(-4)))
	return "\n".join(mem_lines)


# ===== 玩家动态档案 =====

## LLM 每轮输出 <!-- PLAYER: trait=X, motivation=Y --> 后调用此方法更新
func update_player_profile(traits: Array, motivation: String, tendency: String) -> void:
	# 合并 traits，去重保留最近在前的
	var existing: Array = player_profile.get("traits", []) as Array
	for t in traits:
		var t_str: String = t as String
		# 如果已存在，移到最前面（最近出现的最重要）
		var idx: int = existing.find(t_str)
		if idx >= 0:
			existing.remove_at(idx)
		existing.push_front(t_str)
	# 保留最近 5 个特质
	if existing.size() > 5:
		existing.resize(5)
	player_profile["traits"] = existing

	if motivation != "":
		player_profile["motivation"] = motivation
	if tendency != "":
		player_profile["tendency"] = tendency


## 返回可用于 prompt 的玩家档案文本
func get_player_profile_text() -> String:
	var traits: Array = player_profile.get("traits", []) as Array
	var motiv: String = str(player_profile.get("motivation", ""))
	var tend: String = str(player_profile.get("tendency", "中立"))
	var trait_str: String = "、".join(traits)
	if trait_str == "":
		trait_str = "未知"
	return "  已展现性格：%s\n  当前动机：%s\n  行为倾向：%s" % [trait_str, motiv, tend]


# ===== 动态 NPC =====

## LLM 输出 <!-- NPC_NEW: "名字" loc=地点 role=身份 trait=特征 --> 后调用
func add_dynamic_npc(npc_data: Dictionary) -> void:
	var name: String = str(npc_data.get("name", ""))
	if name == "":
		return
	# 检查是否和 canon 角色重名
	var canon_chars: Array = canon.get("characters", []) as Array
	for c_ in canon_chars:
		var canon_char: Dictionary = c_ as Dictionary
		if canon_char.get("name", "") == name:
			return  # 不能覆盖原著角色

	# 检查是否已存在（重名 NPC 更新信息）
	var existing_id: String = ""
	for npc_id in dynamic_npcs:
		var npc_entry: Dictionary = dynamic_npcs[npc_id] as Dictionary
		if npc_entry.get("name", "") == name:
			existing_id = npc_id
			break

	if existing_id != "":
		# 更新已有 NPC 的信息
		var existing_npc: Dictionary = dynamic_npcs[existing_id] as Dictionary
		if npc_data.has("location"):
			existing_npc["location"] = npc_data["location"]
		if npc_data.has("role"):
			existing_npc["role"] = npc_data["role"]
		existing_npc["last_seen"] = game_time
		return

	# 新建 NPC，LRU 淘汰
	var count: int = dynamic_npcs.size()
	if count >= 10:
		var oldest_id: String = ""
		var oldest_time: String = game_time
		for npc_id in dynamic_npcs:
			var old_npc_entry: Dictionary = dynamic_npcs[npc_id] as Dictionary
			var seen: String = str(old_npc_entry.get("last_seen", ""))
			if seen < oldest_time:
				oldest_time = seen
				oldest_id = npc_id
		if oldest_id != "":
			dynamic_npcs.erase(oldest_id)

	var dyn_npc_id: String = "dyn_%03d" % (dynamic_npcs.size() + 1)
	while dynamic_npcs.has(dyn_npc_id):
		dyn_npc_id = "dyn_%03d" % (dynamic_npcs.size() + int(dyn_npc_id.right(3)) + 1)
	dynamic_npcs[dyn_npc_id] = {
		"name": name,
		"location": str(npc_data.get("location", "")),
		"role": str(npc_data.get("role", "")),
		"traits": npc_data.get("traits", []) as Array,
		"first_met": game_time,
		"last_seen": game_time
	}


## 返回当前地点附近已知 NPC 的 prompt 文本（上限 5 人）
func get_nearby_npcs_text(location: String) -> String:
	var nearby: Array = []
	for npc_id in dynamic_npcs:
		var nearby_entry: Dictionary = dynamic_npcs[npc_id] as Dictionary
		if nearby_entry.get("location", "") == location:
			nearby.append(nearby_entry)

	if nearby.size() == 0:
		var others: Array = []
		for npc_id in dynamic_npcs:
			var other_entry: Dictionary = dynamic_npcs[npc_id] as Dictionary
			others.append(other_entry)
		if others.size() == 0:
			return ""
		nearby = others

	nearby = nearby.slice(0, min(5, nearby.size()))
	var npc_lines: Array = []
	for n_ in nearby:
		var npc_row: Dictionary = n_ as Dictionary
		var npc_traits: Array = npc_row.get("traits", []) as Array
		var npc_trait_str: String = "、".join(npc_traits)
		npc_lines.append("- %s（%s）性格：%s" % [npc_row.get("name", ""), npc_row.get("role", ""), npc_trait_str])
	return "\n".join(npc_lines)


# ===== 存档 / 读档 =====

func to_dict() -> Dictionary:
	return {
		"game_time": game_time,
		"time_index": time_index,
		"player_location": player_location,
		"player_known_info": player_known_info.duplicate(),
		"player_reputation": player_reputation.duplicate(true),
		"player_inventory": player_inventory.duplicate(),
		"player_profile": player_profile.duplicate(true),
		"dynamic_canon": dynamic_canon.duplicate(true),
		"scene_memory": scene_memory.duplicate(),
		"long_term_memory": long_term_memory.duplicate(),
		"knowledge_graph": knowledge_graph.duplicate(true),
		"custom_world_rules": custom_world_rules.duplicate(true),
		"characters_state": characters_state.duplicate(true),
		"narrative_threads": narrative_threads.duplicate(true),
		"dynamic_npcs": dynamic_npcs.duplicate(true),
		"world_variables": world_variables.duplicate(true),
		"narrative_history": narrative_history.duplicate(true)
	}


func from_dict(data: Dictionary) -> void:
	game_time = str(data.get("game_time", game_time))
	time_index = data.get("time_index", time_index) as int
	player_location = str(data.get("player_location", player_location))
	player_known_info = data.get("player_known_info", []) as Array
	player_reputation = data.get("player_reputation", {}) as Dictionary
	player_inventory = data.get("player_inventory", []) as Array
	player_profile = data.get("player_profile", {"traits":["好奇","谨慎"],"motivation":"","tendency":"中立"}) as Dictionary
	dynamic_canon = data.get("dynamic_canon", {"character_states":{}, "closed_threads":[], "new_npcs":[], "divergence_events":[]}) as Dictionary
	scene_memory = data.get("scene_memory", []) as Array
	long_term_memory = data.get("long_term_memory", []) as Array
	knowledge_graph = data.get("knowledge_graph", []) as Array
	custom_world_rules = data.get("custom_world_rules", []) as Array
	characters_state = data.get("characters_state", {}) as Dictionary
	narrative_threads = data.get("narrative_threads", {"active":[],"closed":[]}) as Dictionary
	dynamic_npcs = data.get("dynamic_npcs", {}) as Dictionary
	world_variables = data.get("world_variables", {}) as Dictionary
	narrative_history = data.get("narrative_history", []) as Array


# ===== Signal Handlers =====

func _on_narrative_ready(text: String) -> void:
	add_narrative_event(text)


func _on_player_action(action: String) -> void:
	add_narrative_event("玩家行动: " + action)


func _on_thread_updated(_thread_id: String) -> void:
	pass


# ============================================================
# MaNA Pipeline 集成 — 状态变更原子化应用
# ============================================================

## 原子化应用 MaNA Pipeline 产出的状态变更。
## 所有 mood 采用 delta 叠加模式（不覆盖），reputation 采用 delta 累加模式。
## [param patch] StateExtractor 产出的 raw Dictionary
func apply_state_patch(patch: Dictionary) -> void:
	# 1. reputation_changes — delta 叠加
	for change in patch.get("reputation_changes", []):
		var rep_change: Dictionary = change as Dictionary
		var rep_cid: String = str(rep_change.get("char_id", ""))
		var delta: float = rep_change.get("delta", 0.0) as float
		if rep_cid == "" or delta == 0.0:
			continue
		var current_rep: float = player_reputation.get(rep_cid, 0.0) as float
		player_reputation[rep_cid] = clamp(current_rep + delta, -1.0, 1.0)
		# 同步情绪转换
		_apply_mood_from_rep(rep_cid, delta)

	# 2. mood_changes — delta 叠加（不覆盖旧情绪）
	for change in patch.get("mood_changes", []):
		var mood_change: Dictionary = change as Dictionary
		var mood_cid: String = str(mood_change.get("char_id", ""))
		if mood_cid == "":
			continue
		var new_mood: String = str(mood_change.get("new_mood", ""))
		var new_intensity: float = mood_change.get("intensity", 0.5) as float
		var mood_cause: String = str(mood_change.get("cause", ""))
		if new_mood != "":
			set_npc_mood(mood_cid, new_mood, clampf(new_intensity, 0.0, 1.0), mood_cause)

	# 3. location_changes — 更新位置
	for change in patch.get("location_changes", []):
		var loc_change: Dictionary = change as Dictionary
		var loc_cid: String = str(loc_change.get("char_id", ""))
		var to_loc: String = str(loc_change.get("to", ""))
		if loc_cid != "" and to_loc != "":
			update_character_field(loc_cid, "location", to_loc)
			if loc_cid == "player":
				player_location = to_loc

	# 4. new_knowledge — 去重追加
	for k_ in patch.get("new_knowledge", []):
		var k: Dictionary = k_ as Dictionary
		var content: String = str(k.get("content", ""))
		var known_by: Array = k.get("known_by", []) as Array
		if content == "":
			continue
		# 去重：检查是否已存在相同内容
		var exists: bool = false
		for entry in knowledge_graph:
			var entry_dict: Dictionary = entry as Dictionary
			if entry_dict.get("content", "") == content:
				exists = true
				break
		if not exists:
			add_knowledge(content, known_by)

	# 5. new_dynamic_npcs — 注册新 NPC
	for npc_ in patch.get("new_dynamic_npcs", []):
		var npc: Dictionary = npc_ as Dictionary
		if npc.get("name", "") != "":
			add_dynamic_npc(npc)

	# 6. player_profile_updates — 合并
	var ppu: Variant = patch.get("player_profile_updates", null)
	if ppu != null and ppu is Dictionary:
		var profile_update: Dictionary = ppu as Dictionary
		var new_trait: String = str(profile_update.get("new_trait", ""))
		var updated_motivation: String = str(profile_update.get("updated_motivation", ""))
		var tendency_shift: String = str(profile_update.get("tendency_shift", ""))
		var traits_input: Array = []
		if new_trait != "":
			traits_input.append(new_trait)
		update_player_profile(traits_input, updated_motivation, tendency_shift)

	# 7. narrative_summary — 已由 Pipeline 调用 add_narrative_event，此处跳过

	# 8. scene_memory_entry — 已由 Pipeline 调用 add_to_scene_memory，此处跳过

	# 重新计算偏离度
	_recalculate_divergence()

	EventBus.world_time_changed.emit(game_time)
