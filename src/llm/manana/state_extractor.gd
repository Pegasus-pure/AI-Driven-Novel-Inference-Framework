class_name StateExtractor
extends BaseMananaAgent

## Layer 4a — 状态提取 Agent (model_tier: light)
## 从叙事文本 + 角色原始输出中提取结构化 JSON 状态变更。
## 强制使用 json_mode: true，输出严格的 JSON 格式。
##
## 重要的 mood 管理规则:
## mood 采用 delta 叠加 —— 输出 new_mood + intensity，
## 不覆盖旧 mood。WorldState 的 mood 管理由 T05 Pipeline 根据 delta 规则叠加。


func _init() -> void:
	agent_name = "StateExtractor"
	model_tier = "light"


func build_system_prompt() -> String:
	return """你是一个**结构化状态提取器**。你的任务是从叙事文本和角色输出中提取所有状态变更，输出严格的 JSON 格式。

## 提取规则

### 1. 声望变化 (reputation_changes)
从叙事中推断角色对玩家好感度的变化。基于角色的言行反应：
- 正面互动 → delta 为正值 (如 +0.1)
- 负面互动 → delta 为负值 (如 -0.1)
- delta 范围建议 [-0.3, +0.3]
- 必须提供具体的原因

### 2. 情绪变化 (mood_changes)
**重要**: 采用 delta 叠加模式。
- new_mood: 角色当前的情绪状态（如"愤怒"、"欣喜"、"忧虑"、"平静"）
- intensity: 情绪强度 0.0~1.0（0 = 极弱, 1 = 极强）
- cause: 导致情绪变化的直接原因
- 如果角色情绪没有明显变化，可以留空

### 3. 位置变化 (location_changes)
- 只有当角色在叙事中明确发生了位置移动时才记录
- from 和 to 尽量使用标准地点名称

### 4. 新知识 (new_knowledge)
- content: 角色在叙事中认识到的新事实/信息
- known_by: 知道此信息的角色 ID 列表
- 不重复已确立的事实

### 5. 新动态 NPC (new_dynamic_npcs)
- 叙事中首次出现的新角色（非主角、非已有角色）
- 即使只有一句话提及也要记录
- 包含 name / location / role / traits

### 6. 叙事摘要 (narrative_summary)
- 1-2 句话概括本节拍发生的关键事件
- 用于后续的记忆检索和上下文构建

### 7. 场景记忆条目 (scene_memory_entry)
- 一个适合存入场景记忆的简短事实记录
- 格式: "[时间/地点] 关键事实"

## 输出 JSON 格式

```json
{
  "reputation_changes": [
    {"char_id": "char_001", "delta": 0.1, "reason": "玩家帮助了该角色"}
  ],
  "mood_changes": [
    {"char_id": "char_001", "new_mood": "感激", "intensity": 0.6, "cause": "获得了意想不到的帮助"}
  ],
  "location_changes": [
    {"char_id": "char_001", "from": "图书馆", "to": "花园"}
  ],
  "new_knowledge": [
    {"content": "黑森林在月圆之夜会出现神秘通道", "known_by": ["char_001", "char_002"]}
  ],
  "new_dynamic_npcs": [
    {"name": "酒馆老板", "location": "镇中酒馆", "role": "信息提供者", "traits": ["健谈", "好客"]}
  ],
  "player_profile_updates": null,
  "narrative_summary": "角色A和角色B在花园中相遇，谈论了黑森林的秘密。",
  "scene_memory_entry": "[午夜/花园] 角色A告知角色B黑森林通道的存在"
}
```

**player_profile_updates**: 正常情况下为 null。每 3-5 节拍可输出一次，格式为:
```json
{
  "new_trait": "好奇心强",
  "updated_motivation": "寻找失踪的导师",
  "tendency_shift": "更倾向于冒险"
}
```

## 重要原则

1. **只记录发生了变化的状态**: 没有变化就输出空数组
2. **基于文本证据**: 不要臆测没有在叙事中体现的变化
3. **delta 要谨慎**: 声望变化不应过大，单次 ±0.3 为上限
4. **情绪来自上下文**: 从角色的言行、潜台词中推断情绪
5. **new_knowledge 不重复**: 检查 existing_state 中已有的 knowledge_graph
"""


func build_user_prompt(input_data: Dictionary) -> String:
	var narrative_text: String = input_data.get("narrative_text", "") as String
	var character_outputs: Array = input_data.get("character_outputs", []) as Array
	var existing_state: Dictionary = input_data.get("existing_state", {}) as Dictionary

	var lines: Array[String] = []

	lines.append("## 本次叙事文本")
	lines.append("---")
	lines.append(narrative_text)
	lines.append("---")
	lines.append("")

	# 角色原始输出（含 subtext / stance_change 等重要信号）
	if character_outputs.size() > 0:
		lines.append("## 角色原始输出（含潜台词和态度变化信号）")
		for i in range(character_outputs.size()):
			var co: Dictionary = character_outputs[i] as Dictionary
			lines.append("### %s" % co.get("character_id", "未知"))
			var dlgs_raw = co.get("dialogue", [])
			if dlgs_raw is Array:
				for d in dlgs_raw:
					if d is Dictionary:
						lines.append("  - 说: %s" % d.get("text", str(d)))
					else:
						lines.append("  - 说: %s" % str(d))
			else:
				lines.append("对话: %s" % str(dlgs_raw))
			var stance: Variant = co.get("stance_change", null)
			if stance != null and stance is Dictionary:
				lines.append("态度变化信号: %s → %s" % [stance.get("new_attitude", ""), stance.get("reason", "")])
			elif stance != null:
				lines.append("态度变化信号: %s" % str(stance))
			var arc: Variant = co.get("emotional_arc", "")
			if typeof(arc) != TYPE_NIL and str(arc) != "":
				lines.append("情感弧线: %s" % str(arc))
			lines.append("")

	# 已有状态（用于 delta 参考和去重）
	if not existing_state.is_empty():
		lines.append("## 已有状态（仅供参考，不要输出未变化的内容）")
		var moods: Dictionary = existing_state.get("character_moods", {}) as Dictionary
		if moods.size() > 0:
			lines.append("当前角色情绪:")
			for char_id in moods:
				lines.append("  %s: %s" % [char_id, moods[char_id]])
		var locs: Dictionary = existing_state.get("character_locations", {}) as Dictionary
		if locs.size() > 0:
			lines.append("当前角色位置:")
			for char_id in locs:
				lines.append("  %s: %s" % [char_id, locs[char_id]])
		var rep: Dictionary = existing_state.get("player_reputation", {}) as Dictionary
		if rep.size() > 0:
			lines.append("当前玩家声望:")
			for char_id in rep:
				lines.append("  %s: %s" % [char_id, str(rep[char_id])])
		var threads: Array = existing_state.get("active_threads", []) as Array
		if threads.size() > 0:
			lines.append("活跃线索: %d 条" % threads.size())
		var kg: Array = existing_state.get("knowledge_graph", []) as Array
		if kg.size() > 0:
			lines.append("已有知识图谱: %d 条" % kg.size())
		lines.append("")

	lines.append("请提取所有状态变更，输出严格的 JSON 格式。")

	return "\n".join(lines)


## 执行状态提取
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	_log_info("→ 提取状态变更...")
	MananaLogger.log_layer("L4a", "StateExtractor 启动 — %d 角色输出" % (input_data.get("character_outputs", []) as Array).size())

	# 强制 json_mode: true
	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.2, "max_tokens": 2048})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + (parsed.get("error", "") as String)}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 补充缺失字段的默认值
	_ensure_defaults(data)

	var validation: Dictionary = MananaSchema.validate_extractor_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证警告: %s" % str(validation.get("errors", [])))

	var changes_summary: String = _summarize_changes(data)
	_log_info("→ %s" % changes_summary)
	MananaLogger.log_layer("L4a", "StateExtractor 完成 — %s" % changes_summary)

	return {"ok": true, "content": result.get("content", ""), "raw": data}


## 为缺失字段补充默认值
func _ensure_defaults(data: Dictionary) -> void:
	var defaults: Dictionary = {
		"reputation_changes": [],
		"mood_changes": [],
		"location_changes": [],
		"new_knowledge": [],
		"new_dynamic_npcs": [],
		"player_profile_updates": {},
		"narrative_summary": "",
		"scene_memory_entry": "",
	}
	for key in defaults:
		if not data.has(key):
			data[key] = defaults[key]

	# Data sanitization: ensure player_profile_updates is always a Dictionary
	if not (data.get("player_profile_updates", {}) is Dictionary):
		data["player_profile_updates"] = {}


## 生成变更摘要字符串
func _summarize_changes(data: Dictionary) -> String:
	var parts: Array[String] = []

	var rep_changes: Array = data.get("reputation_changes", []) as Array
	if rep_changes.size() > 0:
		parts.append("声望变更×%d" % rep_changes.size())

	var mood: Array = data.get("mood_changes", []) as Array
	if mood.size() > 0:
		parts.append("情绪变更×%d" % mood.size())

	var loc: Array = data.get("location_changes", []) as Array
	if loc.size() > 0:
		parts.append("位置变更×%d" % loc.size())

	var know: Array = data.get("new_knowledge", []) as Array
	if know.size() > 0:
		parts.append("新知识×%d" % know.size())

	var npcs: Array = data.get("new_dynamic_npcs", []) as Array
	if npcs.size() > 0:
		parts.append("新NPC×%d" % npcs.size())

	if parts.size() == 0:
		return "无状态变更"

	return "；".join(parts)
