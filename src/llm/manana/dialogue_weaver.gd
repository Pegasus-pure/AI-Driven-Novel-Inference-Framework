class_name DialogueWeaver
extends BaseMananaAgent

## Layer 2 — 对话编织者 Agent (model_tier: medium)
## 为每个角色生成对话内容、语气、措辞和情绪弧线。
## 交互对中的角色会收到 counterpart 的动机摘要（仅情绪基调和可见目标，不含 hidden_intent）。
## 独立角色则仅基于自身动机和场景基调生成独白/旁白。

func _init() -> void:
	agent_name = "DialogueWeaver"
	model_tier = "medium"


## 返回对话编织系统提示词
func build_system_prompt() -> String:
	return """你是一个互动叙事系统的**对话编织者 (Dialogue Weaver)**。

你的任务是：为一个角色生成在当前场景中的对话和情绪弧线。

## 关键原则

1. **角色一致性**: 对话必须符合角色的性格、身份和语言风格
2. **情绪流动**: 对话是动态的——情绪可能在对话过程中发生变化（emotional_arc）
3. **潜台词**: 角色说的和心里想的可能不一样。利用动机分析中的 subtext
4. **互动性**: 如果角色在对话中（有 counterpart），注意反应和互动
5. **玩家驱动**: 玩家的行动是触发因素。角色应对玩家的行为有语言上的回应

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "dialogue": [
    {
      "text": "角色说出的对白文本",
      "tone": "愤怒|平静|讽刺|热情|冷淡|紧张|温柔|戏谑|严肃|悲伤|好奇|威胁",
      "target": "char_id 或 player",
      "subtext": "这句话背后的真正含义"
    }
  ],
  "actions": [
    {
      "type": "gesture|movement|facial|interaction",
      "description": "动作描述",
      "target": "动作对象"
    }
  ],
  "emotional_arc": "情绪弧线描述——从对话开始时到结束时的情绪变化",
  "stance_change": {
    "new_attitude": "友善|中立|冷淡|敌视|戒备",
    "reason": "态度变化的原因"
  }
}
```

## 字段说明

- **dialogue**: 对话数组。每个元素是一条对白。可以有多条（角色可能说多句话、换语气）
- **dialogue[].text**: 角色说出的具体话语。用中文
- **dialogue[].tone**: 说这句话时的语气
- **dialogue[].target**: 说话对象。可以是其他角色 char_id 或 "player"
- **dialogue[].subtext**: 这句话的潜台词——角色真正的意思
- **actions**: 伴随对话的肢体动作。由 DialogueWeaver 生成基础版，ActionDirector 会细化
- **emotional_arc**: 情绪弧线，描述对话全程的情绪变化（如 "由警惕逐渐转为好奇"）
- **stance_change**: 可选。如果角色对玩家的态度在对话中发生变化则填写，无变化则为 null

## 注意事项

- 对话应当自然、有呼吸感——不要写成长篇大论
- 角色的性格要体现在措辞和语气中
- 如果有 interaction_context（对手机制），回应对方的话语和情绪
- 如果没有 interaction_context（独立角色），可以是自言自语、观察反应或环境互动
"""


## 构建用户提示词: 角色动机 + 交互上下文 + 场景信息
func build_user_prompt(input_data: Dictionary) -> String:
	var character: Dictionary = input_data.get("character", {}) as Dictionary
	var interaction: Dictionary = input_data.get("interaction_context", {}) as Dictionary
	var beat_summary: String = str(input_data.get("beat_summary", ""))
	var player_action: String = str(input_data.get("player_action", ""))
	var scene_tone: String = str(input_data.get("scene_tone", "平淡"))

	var lines: Array[String] = []

	lines.append("## 场景信息")
	lines.append("场景基调: %s" % scene_tone)
	if beat_summary != "":
		lines.append("节拍摘要: %s" % beat_summary)
	if player_action != "":
		lines.append("玩家行动: %s" % player_action)
	lines.append("")

	# 角色基本信息
	var char_id: String = str(character.get("char_id", ""))
	lines.append("## 当前角色")
	lines.append("角色 ID: %s" % char_id)
	lines.append("名字: %s" % character.get("name", "?"))

	var personality: String = str(character.get("personality", ""))
	if personality != "":
		lines.append("性格: %s" % personality)

	var role: String = str(character.get("role", ""))
	if role != "":
		lines.append("原著定位: %s" % role)

	# 动机分析结果
	var motivation: Dictionary = character.get("motivation_output", {}) as Dictionary
	if not motivation.is_empty():
		lines.append("")
		lines.append("### 动机分析")
		var internal: Dictionary = motivation.get("internal_state", {}) as Dictionary
		lines.append("情绪: %s (强度: %.1f)" % [str(internal.get("mood", "?")), internal.get("mood_intensity", 0.5) as float])
		lines.append("主导情绪: %s" % str(internal.get("dominant_emotion", "?")))
		lines.append("潜台词: %s" % str(internal.get("subtext", "(无)")))
		lines.append("隐藏意图: %s" % str(internal.get("hidden_intent", "(无)")))
		lines.append("直接目标: %s" % str(internal.get("immediate_goal", "(无)")))

		var stance: Dictionary = motivation.get("stance_toward_player", {}) as Dictionary
		if not stance.is_empty():
			lines.append("对玩家态度: %s (信任: %.1f)" % [str(stance.get("attitude", "?")), stance.get("trust_level", 0.5) as float])
			lines.append("想对玩家: %s" % stance.get("wants_to", "?"))

	lines.append("")

	# 交互上下文
	if not interaction.is_empty():
		var counterpart: Dictionary = interaction.get("counterpart", {}) as Dictionary
		if not counterpart.is_empty():
			lines.append("## 对话对象")
			lines.append("正在与 **%s** 对话" % str(counterpart.get("name", "?")))
			lines.append("对方情绪: %s" % str(counterpart.get("emotional_tone", "?")))
			lines.append("对方可见目标: %s" % str(counterpart.get("visible_goal", "?")))
			lines.append("")
			lines.append("请生成 %s 对 %s 的回应对话。要体现角色的性格和真实意图。" % [character.get("name", "?"), counterpart.get("name", "?")])
	else:
		lines.append("## 交互模式: 独立")
		lines.append("此角色当前不参与对话交互。可以是对环境的反应、自言自语、或对玩家行动的观察。")
		lines.append("")

	lines.append("输出 JSON。")

	# v4: 行为禁区
	var anti_rules: Array = character.get("anti_rules", []) as Array
	if anti_rules.size() > 0:
		lines.append("")
		lines.append("## 行为禁区（绝对不能违反）")
		for rule_ in anti_rules:
			var rule: String = str(rule_)
			lines.append("- %s" % rule)

	return "\n".join(lines)


## 执行对话编织
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	var char_name: String = str(input_data.get("character", {}).get("name", "?"))
	_log_info("→ 编织 %s 的对话..." % char_name)

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.85})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 确保 character_id 一致
	if not data.has("character_id") or data.get("character_id", "") == "":
		data["character_id"] = str(input_data.get("character", {}).get("char_id", ""))

	var validation: Dictionary = MananaSchema.validate_dialogue_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证失败: %s" % str(validation.get("errors", [])))

	var dialogue_count: int = (data.get("dialogue", []) as Array).size()
	_log_info("→ %s: %d 条对话" % [char_name, dialogue_count])

	return {"ok": true, "content": result.get("content", ""), "raw": data}
