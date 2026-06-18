extends RefCounted

## 叙事状态机 — 根据世界状态判定当前叙事阶段
##
## EXPLORATION → DIALOGUE → CONFLICT → REVELATION → RESOLUTION
##
## 判定因子: 线索进度、偏离度、角色关系变化、地点切换

enum State {EXPLORATION, DIALOGUE, CONFLICT, REVELATION, RESOLUTION}

static var _last_location: String = ""
static var _last_divergence: float = 0.0
static var _in_conflict: bool = false


## 判定当前叙事状态
static func determine() -> int:
	var dv: float = _get_divergence()
	var active: Array = _get_active_threads()
	var avg_progress: float = _avg_thread_progress(active)
	var has_recent_change: bool = _has_significant_change(dv)
	var relation_volatile: bool = _has_volatile_relations()

	# RESOLUTION: 偏离度极高或所有线索收束
	if dv >= 0.8 or (active.size() == 0 and _has_closed_main_threads()):
		return State.RESOLUTION

	# REVELATION: 线索逼近完成 + 世界关系发生重大变化
	if avg_progress >= 0.7 and has_recent_change:
		return State.REVELATION

	# CONFLICT: 偏离度突然跃升或关系剧烈波动
	if has_recent_change or relation_volatile:
		if not _in_conflict and dv - _last_divergence > 0.05:
			_in_conflict = true
		if _in_conflict:
			# 冲突退出的条件: 至少完成一条线索或关系稳定
			if _recent_thread_completed() or not relation_volatile:
				_in_conflict = false
			else:
				return State.CONFLICT

	# DIALOGUE: 有活跃线索 + 场景中有多个角色
	if active.size() > 0 and _scene_has_multiple_characters():
		return State.DIALOGUE

	# EXPLORATION: 默认
	_remember_state(dv)
	return State.EXPLORATION


static func _remember_state(dv: float) -> void:
	_last_divergence = dv


# ===== 判定因子 =====

static func _get_divergence() -> float:
	if not WorldState:
		return 0.0
	return WorldState.get_divergence()


static func _get_active_threads() -> Array:
	if not WorldState:
		return []
	return WorldState.get_active_threads()


static func _avg_thread_progress(threads: Array) -> float:
	if threads.size() == 0:
		return 0.0
	var total: float = 0.0
	for t in threads:
		var d: Dictionary = t as Dictionary
		total += d.get("progress", 0.0) as float
	return total / threads.size()


static func _has_closed_main_threads() -> bool:
	if not WorldState:
		return false
	var threads = WorldState.narrative_threads as Dictionary
	var closed = threads.get("closed", []) as Array
	for t in closed:
		var closed_entry: Dictionary = t as Dictionary
		if closed_entry.get("type", "") == "main":
			return true
	return false


static func _recent_thread_completed() -> bool:
	"""是否有线索最近完成（最近 1 轮内）"""
	var history: Array = []
	if WorldState:
		history = WorldState.narrative_history as Array
	# 检查最近 2 条历史中是否有 THREAD_CLOSE
	for entry in history.slice(-2):
		var e: Dictionary = entry as Dictionary
		var summary: String = str(e.get("summary", ""))
		if "关闭" in summary or "完成" in summary or "收束" in summary:
			return true
	return false


static func _has_significant_change(dv: float) -> bool:
	"""偏离度最近有显著跃升"""
	return abs(dv - _last_divergence) > 0.03


static func _has_volatile_relations() -> bool:
	"""是否有 NPC 关系剧烈变化"""
	if not WorldState:
		return false
	var rep: Dictionary = WorldState.player_reputation as Dictionary
	for val in rep.values():
		if abs(val as float) > 0.5:  # 关系强度超过 ±0.5
			return true
	return false


static func _scene_has_multiple_characters() -> bool:
	"""当前场景是否有多个角色（玩家+至少1个NPC）"""
	if not WorldState:
		return false
	var dpcs: Dictionary = WorldState.dynamic_npcs as Dictionary
	return dpcs.size() > 0 or _has_canon_chars_nearby()


static func _has_canon_chars_nearby() -> bool:
	if not WorldState:
		return false
	var loc: String = WorldState.player_location as String
	var chars: Array = WorldState.canon.get("characters", []) as Array
	for c_ in chars:
		var c: Dictionary = c_ as Dictionary
		var cs: Dictionary = WorldState.get_character_state(str(c.get("id", "")))
		var char_loc: String = str(cs.get("location", str(c.get("starting_location", ""))))
		if char_loc == loc:
			return true
	return false


## 重置状态（新游戏或读档后调用）
static func reset() -> void:
	_last_location = ""
	_last_divergence = 0.0
	_in_conflict = false
