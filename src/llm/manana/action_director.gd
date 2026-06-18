class_name ActionDirector
extends BaseMananaAgent

## Layer 2 — 动作指导 Agent (model_tier: light)
## 为每个角色生成肢体动作、表情变化和微表情。
## 用轻量模型 + 极简 prompt，只输出动作描述数组。
## 交互对中接收 counterpart 的动机摘要（同 DialogueWeaver 的交互上下文）。

func _init() -> void:
	agent_name = "ActionDirector"
	model_tier = "light"


## 返回动作指导系统提示词（极简版）
func build_system_prompt() -> String:
	return """你是一个动作指导。

只输出角色在当前场景中可能做出的肢体动作和表情变化。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "actions": [
    {
      "type": "gesture|movement|facial|interaction|posture",
      "description": "简短的动作描述",
      "target": "none|char_id|player|environment",
      "intensity": "subtle|moderate|dramatic"
    }
  ]
}
```

## 动作类型

- **gesture**: 手势/肢体动作（挥手、握拳、摆手）
- **movement**: 位置移动（走近、后退、转身）
- **facial**: 面部表情/微表情（皱眉、嘴角上扬、瞪大眼）
- **interaction**: 与物体/人的互动（推门、递东西、拍肩）
- **posture**: 身体姿态变化（挺直腰背、瘫坐、抱臂）

## 限制

- 只输出 JSON，不要对话，不要心理描写
- actions 数组 1-4 个元素即可
- 动作要符合角色的当前情绪和场景基调
"""


## 构建用户提示词: 角色信息 + 场景 + 交互上下文
func build_user_prompt(input_data: Dictionary) -> String:
	var character: Dictionary = input_data.get("character", {}) as Dictionary
	var interaction: Dictionary = input_data.get("interaction_context", {}) as Dictionary
	var scene_tone: String = str(input_data.get("scene_tone", "平淡"))
	var player_action: String = str(input_data.get("player_action", ""))

	var lines: Array[String] = []

	lines.append("场景基调: %s" % scene_tone)
	lines.append("")

	lines.append("角色: %s (id: %s)" % [character.get("name", "?"), character.get("char_id", "?")])

	# 性格
	var personality: String = str(character.get("personality", ""))
	if personality != "":
		lines.append("性格: %s" % personality)

	# 动机中的情绪信息
	var motivation: Dictionary = character.get("motivation_output", {}) as Dictionary
	if not motivation.is_empty():
		var internal: Dictionary = motivation.get("internal_state", {}) as Dictionary
		lines.append("情绪: %s (强度: %.1f)" % [str(internal.get("mood", "中性")), internal.get("mood_intensity", 0.5) as float])
		lines.append("直接目标: %s" % str(internal.get("immediate_goal", "无")))

		# 对话中已有的 dialogue 可选参考
		var dialogue: Array = (input_data.get("character", {}).get("dialogue_output", {})).get("dialogue", []) if input_data.get("character", {}).has("dialogue_output") else []
		# 不强制要求——ActionDirector 可能先于或并行于 DialogueWeaver 执行

	lines.append("")

	# 交互上下文
	if not interaction.is_empty():
		var counterpart: Dictionary = interaction.get("counterpart", {}) as Dictionary
		if not counterpart.is_empty():
			lines.append("正在与 %s 互动" % str(counterpart.get("name", "?")))
			lines.append("对方情绪: %s" % str(counterpart.get("emotional_tone", "?")))
			lines.append("")

	if player_action != "":
		lines.append("玩家刚刚: %s" % player_action)
		lines.append("")

	lines.append("请只输出此角色的动作描述 JSON。不要对话。")

	return "\n".join(lines)


## 执行动作指导
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	var char_name: String = str(input_data.get("character", {}).get("name", "?"))
	_log_info("→ 编排 %s 的动作..." % char_name)

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.6, "max_tokens": 512})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 确保 character_id 存在
	if not data.has("character_id") or data.get("character_id", "") == "":
		data["character_id"] = str(input_data.get("character", {}).get("char_id", ""))

	var action_count: int = (data.get("actions", []) as Array).size()
	_log_info("→ %s: %d 个动作" % [char_name, action_count])

	return {"ok": true, "content": result.get("content", ""), "raw": data}
