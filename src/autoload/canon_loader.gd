extends Node

## 正典加载器
## 读取 Canon.json 并填充到 WorldState.canon 中
## 同时初始化 WorldState 的角色状态、地点等基础数据

var _file_path: String = "res://src/data/canon.json"


func load_canon(file_path: String = "") -> Dictionary:
	if file_path != "":
		_file_path = file_path

	if not FileAccess.file_exists(_file_path):
		push_error("Canon file not found: " + _file_path)
		return {}

	var f: FileAccess = FileAccess.open(_file_path, FileAccess.READ)
	if f == null:
		push_error("Cannot open canon file: " + _file_path)
		return {}

	var raw: String = f.get_as_text()
	f.close()

	var json: JSON = JSON.new()
	var err: int = json.parse(raw)
	if err != OK:
		push_error("JSON parse error at line %d: %s" % [json.get_error_line(), json.get_error_message()])
		return {}

	var data: Variant = json.get_data()
	if not (data is Dictionary):
		push_error("Canon.json root must be a Dictionary")
		return {}

	var canon: Dictionary = data as Dictionary
	WorldState.canon = canon
	_initialize_world_state(canon)
	return canon


func _initialize_world_state(canon: Dictionary) -> void:
	# 初始化角色状态
	var characters: Array = canon.get("characters", []) as Array
	for c_ in characters:
		var c: Dictionary = c_ as Dictionary
		var char_id: String = str(c.get("id", ""))
		if char_id == "":
			continue
		WorldState.characters_state[char_id] = {
			"location": str(c.get("starting_location", "")),
			"hp": "健康",
			"goal": _extract_character_goal(c),
			"mood": "平静",
			"relations": _init_relations(c, characters)
		}

	# 初始化玩家起始位置
	var locations: Array = canon.get("locations", []) as Array
	if locations.size() > 0:
		var first_loc: Dictionary = locations[0] as Dictionary
		WorldState.player_location = str(first_loc.get("id", ""))

	# 从时间线初始化叙事线索
	var timeline: Array = canon.get("timeline", []) as Array
	_seed_initial_threads(timeline)


func _init_relations(char: Dictionary, all_chars: Array) -> Dictionary:
	var rels: Dictionary = {}
	var relationships: Array = char.get("relationships", []) as Array
	for r_ in relationships:
		var r: Dictionary = r_ as Dictionary
		var target: String = str(r.get("target", ""))
		var intensity: float = r.get("intensity", 0.0) as float
		rels[target] = intensity
	return rels


func _extract_character_goal(char: Dictionary) -> String:
	var personality: Dictionary = char.get("personality", {}) as Dictionary
	return str(personality.get("core_motivation", ""))


func _seed_initial_threads(timeline: Array) -> void:
	if timeline.size() == 0:
		return

	# 防止重复播种（游戏启动和选书都可能触发 load_canon）
	var active: Array = WorldState.narrative_threads["active"] as Array
	if active.size() > 0:
		return

	# 主线：第一个关键事件
	var first_event: Dictionary = timeline[0] as Dictionary
	var main_thread: Dictionary = {
		"id": "thread_main",
		"title": str(first_event.get("title", "主线剧情")),
		"type": "main",
		"progress": 0.0,
		"question": str(first_event.get("description", "命运将如何展开？")),
		"involved_characters": first_event.get("involved_characters", []) as Array,
		"involved_locations": _extract_location_ids(timeline),
		"parent_thread": "",
		"child_threads": [],
		"key_milestones": _extract_milestones(timeline),
		"tension": 0.3,
		"player_attention": 0.5,
		"priority": 0.5,
		"created_at": WorldState.game_time,
		"last_advanced_at": WorldState.game_time
	}
	WorldState.add_thread(main_thread)

	# 支线种子：如果有 2+ 的事件，取第二、三个作为支线
	if timeline.size() >= 2:
		var e2: Dictionary = timeline[1] as Dictionary
		WorldState.add_thread({
			"id": "thread_side_a",
			"title": str(e2.get("title", "支线A")),
			"type": "side",
			"progress": 0.0,
			"question": str(e2.get("description", "")),
			"involved_characters": e2.get("involved_characters", []) as Array,
			"involved_locations": [],
			"parent_thread": "",
			"child_threads": [],
			"key_milestones": [],
			"tension": 0.2,
			"player_attention": 0.3,
			"priority": 0.3,
			"created_at": WorldState.game_time,
			"last_advanced_at": WorldState.game_time
		})

	if timeline.size() >= 3:
		var e3: Dictionary = timeline[2] as Dictionary
		WorldState.add_thread({
			"id": "thread_side_b",
			"title": str(e3.get("title", "支线B")),
			"type": "side",
			"progress": 0.0,
			"question": str(e3.get("description", "")),
			"involved_characters": e3.get("involved_characters", []) as Array,
			"involved_locations": [],
			"parent_thread": "",
			"child_threads": [],
			"key_milestones": [],
			"tension": 0.2,
			"player_attention": 0.3,
			"priority": 0.3,
			"created_at": WorldState.game_time,
			"last_advanced_at": WorldState.game_time
		})


func _extract_location_ids(timeline: Array) -> Array:
	var locs: Array = []
	for e_ in timeline:
		var e: Dictionary = e_ as Dictionary
		var loc: String = str(e.get("location", ""))
		if loc != "" and not locs.has(loc):
			locs.append(loc)
	return locs


func _extract_milestones(timeline: Array) -> Array:
	var milestones: Array = []
	var total: int = timeline.size()
	for i in range(min(4, total)):
		var event_entry: Dictionary = timeline[i] as Dictionary
		var progress: float = float(i + 1) / float(min(4, total))
		milestones.append({
			"at_progress": progress,
			"description": str(event_entry.get("description", ""))
		})
	return milestones


# ===== 读取 Canon 中的角色信息 =====

func get_character_canon(char_id: String) -> Dictionary:
	var lookup_characters: Array = WorldState.canon.get("characters", []) as Array
	for c_ in lookup_characters:
		var lookup_c: Dictionary = c_ as Dictionary
		if str(lookup_c.get("id", "")) == char_id:
			return lookup_c
	return {}


func get_location_info(loc_id: String) -> Dictionary:
	var lookup_locations: Array = WorldState.canon.get("locations", []) as Array
	for loc_ in lookup_locations:
		var lookup_loc: Dictionary = loc_ as Dictionary
		if str(lookup_loc.get("id", "")) == loc_id:
			return lookup_loc
	return {}


func get_world_rules_text() -> String:
	var rules: Dictionary = WorldState.canon.get("world_rules", {}) as Dictionary
	if rules.is_empty():
		return "未知世界"
	var lines: Array = []
	var era: String = str(rules.get("era", ""))
	if era != "":
		lines.append("时代背景: " + era)
	var magic: Dictionary = rules.get("magic_system", {}) as Dictionary
	if not magic.is_empty():
		lines.append("力量体系: " + str(magic.get("name", "未知")))
	return "\n".join(lines)


## 获取角色的行为禁区列表（v4 anti_rules）
## [param char_id] 角色 ID
## [returns] Array[String] — 反例规则列表；缺失时返回空数组
func get_character_anti_rules(char_id: String) -> Array:
	var char_data: Dictionary = get_character_canon(char_id)
	if char_data.is_empty():
		return []
	var personality: Dictionary = char_data.get("personality", {}) as Dictionary
	var rules: Array = personality.get("anti_rules", []) as Array
	return rules
