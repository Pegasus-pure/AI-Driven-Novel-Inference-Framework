class_name MananaSchema
extends RefCounted

## MaNA 数据契约中心 — 全静态类。
## 定义所有 Agent 的输入/输出 Schema 常量，以及 SceneContext 构建和输出验证方法。
## 所有方法均为 static，不持有任何实例状态。

# ============================================================
# SceneContext Schema
# ============================================================

const SCENE_CONTEXT_SCHEMA: Dictionary = {
	"beat_id": "string",
	"scene_id": "string",
	"game_time": "string",
	"location": {"id": "", "name": "", "description": "", "atmosphere": ""},
	"player": {
		"action": "",
		"profile": {"traits": [], "motivation": "", "tendency": ""},
		"reputation": {}
	},
	"characters": [],
	"active_threads": [],
	"recent_history": [],
	"scene_memory": [],
	"long_term_memory": [],
	"divergence": 0.0,
	"relevant_world_rules": ""
}

# ============================================================
# Agent 输入/输出 Key 定义
# ============================================================

const DIRECTOR_INPUT_KEYS: Array[String] = ["system_prompt", "scene_context"]
const DIRECTOR_OUTPUT_KEYS: Array[String] = [
	"beat_id", "narrative_mode", "beat_summary", "featured_characters",
	"interaction_pairs", "unpaired_characters", "scene_tone",
	"priority_thread_ids", "required_canon"
]

const MOTIVATION_OUTPUT_KEYS: Array[String] = [
	"character_id", "internal_state", "stance_toward_player"
]

const DIALOGUE_WEAVER_OUTPUT_KEYS: Array[String] = [
	"character_id", "dialogue", "actions", "emotional_arc", "stance_change"
]

const COMPOSER_OUTPUT_KEYS: Array[String] = [
	"ending_hook", "action_hints", "music_mood"
]

const AUDITOR_OUTPUT_KEYS: Array[String] = [
	"verdict", "issues", "overall_quality"
]

const STATE_EXTRACTOR_OUTPUT_KEYS: Array[String] = [
	"reputation_changes", "mood_changes", "location_changes",
	"new_knowledge", "new_dynamic_npcs", "player_profile_updates",
	"narrative_summary", "scene_memory_entry"
]

const THREAD_MANAGER_OUTPUT_KEYS: Array[String] = [
	"thread_advances", "new_threads", "closed_threads", "tension_adjustments"
]

const ORACLE_OUTPUT_KEYS: Array[String] = [
	"pacing_assessment", "character_observations", "thread_health",
	"narrative_opportunities", "tone_recommendation"
]


# ============================================================
# SceneContext 构建
# ============================================================

## 从 WorldState 原始数据组装完整的 SceneContext Dictionary。
## [param chars] WorldState 中的角色数据列表
## [param threads] 活跃叙事线索列表
## [param location] 当前地点信息
## [param player] 玩家状态 {action, profile, reputation}
## [param history] 最近叙事历史
## [param memory] {scene_memory: Array, long_term_memory: Array}
## [param divergence] 世界偏离度 (0.0~1.0)
## [param world_rules] 相关世界规则文本 (可空)
## [param beat_id] 当前节拍 ID (可空)
## [param scene_id] 当前场景 ID (可空)
## [param game_time] 当前游戏时间 (可空)
## [returns] 完整 SceneContext Dictionary
static func build_scene_context(
	chars: Array,
	threads: Array,
	location: Dictionary,
	player: Dictionary,
	history: Array,
	memory: Dictionary,
	divergence: float,
	world_rules: String = "",
	beat_id: String = "",
	scene_id: String = "",
	game_time: String = ""
) -> Dictionary:
	return {
		"beat_id": beat_id,
		"scene_id": scene_id,
		"game_time": game_time,
		"location": location.duplicate(),
		"player": player.duplicate(true),
		"characters": chars.duplicate(true),
		"active_threads": threads.duplicate(true),
		"recent_history": history.duplicate(),
		"scene_memory": memory.get("scene_memory", []) if memory is Dictionary else [],
		"long_term_memory": memory.get("long_term_memory", []) if memory is Dictionary else [],
		"divergence": divergence,
		"relevant_world_rules": world_rules,
	}


# ============================================================
# 输出验证
# ============================================================

## 通用验证: 检查 data 是否包含所有 required_keys，并对每个 key 做基本类型检查。
## [returns] {"valid": bool, "errors": [String]}
static func _validate_keys(data: Dictionary, required_keys: Array, type_map: Dictionary = {}) -> Dictionary:
	var errors: Array[String] = []

	for key in required_keys:
		var key_str: String = key as String
		if not data.has(key_str):
			errors.append("Missing required key: '%s'" % key_str)
			continue

		if type_map.has(key_str):
			var expected: String = type_map[key_str] as String
			var value: Variant = data[key_str]
			match expected:
				"string":
					if not (value is String):
						errors.append("Key '%s' expected String, got %s" % [key_str, typeof(value)])
				"int", "float":
					if not (value is float or value is int):
						errors.append("Key '%s' expected number, got %s" % [key_str, typeof(value)])
				"array":
					if not (value is Array):
						errors.append("Key '%s' expected Array, got %s" % [key_str, typeof(value)])
				"dictionary":
					if not (value is Dictionary):
						errors.append("Key '%s' expected Dictionary, got %s" % [key_str, typeof(value)])
				"bool":
					if not (value is bool):
						errors.append("Key '%s' expected bool, got %s" % [key_str, typeof(value)])

	return {"valid": errors.size() == 0, "errors": errors}


## 验证 Director 输出
static func validate_director_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, DIRECTOR_OUTPUT_KEYS, {
		"beat_id": "string",
		"narrative_mode": "string",
		"beat_summary": "string",
		"featured_characters": "array",
		"interaction_pairs": "array",
		"unpaired_characters": "array",
		"scene_tone": "string",
		"priority_thread_ids": "array",
		"required_canon": "array",
	})


## 验证 Motivation 输出
static func validate_motivation_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, MOTIVATION_OUTPUT_KEYS, {
		"character_id": "string",
		"internal_state": "dictionary",
		"stance_toward_player": "string",
	})


## 验证 Dialogue 输出
static func validate_dialogue_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, DIALOGUE_WEAVER_OUTPUT_KEYS, {
		"character_id": "string",
		"dialogue": "string",
		"actions": "array",
		"emotional_arc": "string",
		"stance_change": "string",
	})


## 验证 Composer 输出
static func validate_composer_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, COMPOSER_OUTPUT_KEYS, {
		"ending_hook": "string",
		"action_hints": "array",
		"music_mood": "string",
	})


## 验证 Auditor 输出
static func validate_auditor_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, AUDITOR_OUTPUT_KEYS, {
		"verdict": "string",
		"issues": "array",
		"overall_quality": "dictionary",
	})


## 验证 StateExtractor 输出
static func validate_extractor_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, STATE_EXTRACTOR_OUTPUT_KEYS, {
		"reputation_changes": "array",
		"mood_changes": "array",
		"location_changes": "array",
		"new_knowledge": "array",
		"new_dynamic_npcs": "array",
		"player_profile_updates": "dictionary",
		"narrative_summary": "string",
		"scene_memory_entry": "string",
	})


## 验证 ThreadManager 输出
static func validate_thread_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, THREAD_MANAGER_OUTPUT_KEYS, {
		"thread_advances": "array",
		"new_threads": "array",
		"closed_threads": "array",
		"tension_adjustments": "array",
	})


## 验证 Oracle 输出
static func validate_oracle_output(data: Dictionary) -> Dictionary:
	return _validate_keys(data, ORACLE_OUTPUT_KEYS, {
		"pacing_assessment": "dictionary",
		"character_observations": "array",
		"thread_health": "array",
		"narrative_opportunities": "array",
		"tone_recommendation": "string",
	})
