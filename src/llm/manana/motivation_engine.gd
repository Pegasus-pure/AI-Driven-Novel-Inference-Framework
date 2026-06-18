class_name MotivationEngine
extends BaseMananaAgent

## Layer 1 — 动机引擎 Agent (model_tier: medium)
## 为每个角色独立分析内部状态、情绪、隐藏意图和潜台词。
## 角色之间完全隔离——不传入其他角色的数据，保证信息隔离。

func _init() -> void:
	agent_name = "MotivationEngine"
	model_tier = "medium"


## 返回动机分析系统提示词
func build_system_prompt() -> String:
	return """你是一个互动叙事系统的**动机分析引擎**。

你的任务是：根据单个角色的性格、当前状态和所处场景，分析其内心世界。

## 关键原则

1. **角色隔离**: 你只知道这一个角色的信息。不要假设其他角色知道什么或怎么想。
2. **一致性**: 角色的内部状态必须与其性格特点和已知事实一致。
3. **叙事驱动**: 不要平淡——角色应该有明确的目标和情感取向，推动叙事发展。
4. **潜台词**: 角色的真实想法可能与外显情绪不同。subtext 和 hidden_intent 是角色的内心秘密，不对外暴露。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "internal_state": {
	"mood": "喜悦|愤怒|恐惧|悲伤|好奇|中性",
	"mood_intensity": 0.0,
	"dominant_emotion": "描述当前最强烈的情绪",
	"subtext": "角色的潜台词——表面之下真正的想法",
	"hidden_intent": "角色的隐藏意图——不为人知的真实目标",
	"immediate_goal": "角色在当前场景中的直接目标"
  },
  "stance_toward_player": {
	"attitude": "友善|中立|冷淡|敌视|戒备",
	"trust_level": 0.0,
	"wants_to": "主动交谈|保持距离|观察玩家|无视玩家|试探玩家|寻求帮助"
  }
}
```

## 字段说明

- **mood**: 角色当前基础情绪
- **mood_intensity**: 0.0-1.0，情绪强烈程度
- **dominant_emotion**: 用自然语言描述角色当下的主导情绪（如 "隐隐不安"、"满怀期待"）
- **subtext**: 角色的潜台词。外显情绪之下真正的内心活动。这不会被其他角色看到
- **hidden_intent**: 角色的隐藏意图。真正的目标是什么？这会驱动其行为但不直接暴露
- **immediate_goal**: 在当前场景/节拍中想达成什么
- **attitude**: 对玩家的外显态度
- **trust_level**: 0.0-1.0，对玩家的信任程度
- **wants_to**: 在本节拍中想和玩家产生怎样的互动

如果一个角色对玩家没有特别的感受（如路人级 NPC），stance 设为中立即可，不要编造。
"""


## 构建用户提示词: 单角色 + 场景摘要
func build_user_prompt(input_data: Dictionary) -> String:
	var character: Dictionary = input_data.get("character", {}) as Dictionary
	var scene_summary: String = str(input_data.get("scene_summary", ""))
	var player_action: String = str(input_data.get("player_action", ""))
	var scene_tone: String = str(input_data.get("scene_tone", "平淡"))

	var lines: Array[String] = []

	lines.append("## 场景上下文")
	lines.append("场景基调: %s" % scene_tone)
	if scene_summary != "":
		lines.append("节拍摘要: %s" % scene_summary)
	if player_action != "":
		lines.append("玩家行动: %s" % player_action)
	lines.append("")

	lines.append("## 角色信息")
	lines.append("角色 ID: %s" % character.get("char_id", "?"))
	lines.append("名字: %s" % character.get("name", "?"))

	var personality: String = str(character.get("personality", ""))
	if personality != "":
		lines.append("性格: %s" % personality)

	var role: String = str(character.get("role", ""))
	if role != "":
		lines.append("原著角色定位: %s" % role)

	# 当前状态
	var cs: Dictionary = character.get("current_state", {}) as Dictionary
	lines.append("当前地点: %s" % str(cs.get("location", "?")))
	lines.append("当前情绪: %s" % str(cs.get("mood", "中性")))
	if cs.has("goal") and str(cs.get("goal", "")) != "":
		lines.append("当前目标: %s" % cs["goal"])

	# 已知事实
	var facts: Array = character.get("known_facts", []) as Array
	if facts.size() > 0:
		lines.append("已知事实: %s" % "；".join(facts))

	# 对玩家关系
	var rel: String = str(character.get("relation_to_player", ""))
	if rel != "":
		lines.append("对玩家的态度: %s" % rel)

	# v4: 行为禁区
	var anti_rules: Array = character.get("anti_rules", []) as Array
	if anti_rules.size() > 0:
		lines.append("")
		lines.append("## 行为禁区（绝对不能违反）")
		for rule_ in anti_rules:
			var rule: String = str(rule_)
			lines.append("- %s" % rule)

	lines.append("")
	lines.append("请分析此角色在本节拍中的内心状态。输出 JSON。")

	return "\n".join(lines)


## 执行动机分析
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	var char_name: String = str(input_data.get("character", {}).get("name", "?"))
	_log_info("→ 分析 %s ..." % char_name)

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.7})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 确保 character_id 与输入一致
	if not data.has("character_id") or data.get("character_id", "") == "":
		data["character_id"] = str(input_data.get("character", {}).get("char_id", ""))

	var validation: Dictionary = MananaSchema.validate_motivation_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证失败: %s" % str(validation.get("errors", [])))

	var mood: String = str(data.get("internal_state", {}).get("mood", "?"))
	_log_info("→ %s: 情绪=%s" % [char_name, mood])

	return {"ok": true, "content": result.get("content", ""), "raw": data}
