class_name SceneComposer
extends BaseMananaAgent

## Layer 3 — 场景编织者 Agent (model_tier: strong)
## 将 Director 的计划 + 所有 Character Engine 输出编织为最终叙事散文。
## 输出为纯文本散文 + 末尾 JSON 元数据块（以 ---JSON--- 分隔）。
##
## 特殊处理: 不使用 _parse_json_response，而是自建混合输出解析逻辑。
## narrative_text 为完整散文（4-8段），末尾 JSON 块含 action_hints / ending_hook / music_mood。

const JSON_SEPARATOR: String = "---JSON---"


func _init() -> void:
	agent_name = "SceneComposer"
	model_tier = "strong"


func build_system_prompt() -> String:
	return """你是一位小说叙事大师。你的任务是根据导演计划和所有角色的输出，将场景编织为流畅自然的叙事散文。

## 叙事要求

1. **纯文学散文风格**: 用优美的中文写出 4-8 段叙事散文。像一本真正的文学小说那样写作——描写细腻、节奏有致、情感层次丰富。

2. **对话格式**: 所有对话必须使用以下格式：
   【角色名】
   "对话内容"

   每段对话独立成段，角色名放在【】中，对话内容放在双引号内。

3. **禁止 HTML 标记**: 输出必须是纯文本，不要使用任何 HTML 标签（如 <p>、<br>、<span> 等）。使用空行分隔段落。

4. **自然地整合**: 将导演的计划、各个角色的对话和行动自然地编织在一起。不要逐条罗列——让它们像小说一样流畅展开。

5. **环境描写**: 用 1-2 句话描写场景环境、气氛、光线、天气等，让读者身临其境。

6. **心理描写**: 适度加入角色的内心感受和微表情，但不要过度解释。

7. **结尾钩子**: 在叙事末尾留下悬念或一个待解答的问题，激发玩家继续。

## 输出格式

你的响应分为两部分：

### 第一部分: 叙事散文（正文）
写出完整的叙事散文，4-8 段。对话使用【角色名】/引号格式。

### 第二部分: 元数据 JSON
在散文结束后，添加分隔符 `---JSON---`，然后输出一个 JSON 对象：

```json
{
  "ending_hook": "结尾钩子——暗示下一步发展的悬念句",
  "action_hints": ["玩家可能的行动方向 1", "玩家可能的行动方向 2", "玩家可能的行动方向 3"],
  "music_mood": "场景情绪标签，如: 紧张、温馨、悲伤、神秘、欢快、庄严、平淡"
}
```

**重要**: JSON 块必须是最后一个内容，位于 `---JSON---` 之后。叙事散文中不要包含任何 JSON 或代码块。
"""


func build_user_prompt(input_data: Dictionary) -> String:
	var director: Dictionary = input_data.get("director_output", {}) as Dictionary
	var character_outputs: Array = input_data.get("character_outputs", []) as Array
	var scene_ctx: Dictionary = input_data.get("scene_context_summary", {}) as Dictionary
	var recent: String = input_data.get("recent_narrative", "") as String

	var lines: Array[String] = []

	# 场景上下文
	lines.append("## 场景信息")
	lines.append("当前时间: %s" % scene_ctx.get("game_time", "未知"))
	lines.append("地点: %s" % scene_ctx.get("location_name", "未知"))
	lines.append("氛围: %s" % scene_ctx.get("location_atmosphere", ""))
	lines.append("")

	# 写作风格
	var style: Dictionary = scene_ctx.get("writing_style", {}) as Dictionary
	if not style.is_empty():
		lines.append("写作风格指引: 语气=%s, 节奏=%s, 对话风格=%s" % [
			style.get("tone", "中性") as String, style.get("pace", "适中") as String, style.get("dialogue_style", "自然") as String
		])
		lines.append("")

	# 玩家行动
	lines.append("玩家行动: %s" % scene_ctx.get("player_action", "(无)"))
	lines.append("")

	# 导演计划
	lines.append("## 导演计划")
	lines.append("节拍摘要: %s" % director.get("beat_summary", ""))
	lines.append("叙事模式: %s" % director.get("narrative_mode", ""))
	lines.append("场景基调: %s" % director.get("scene_tone", ""))
	lines.append("")

	# 角色输出
	lines.append("## 角色输出")
	for i in range(character_outputs.size()):
		var co: Dictionary = character_outputs[i] as Dictionary
		lines.append("### 角色: %s" % co.get("character_id", "未知"))
		# dialogue 是 Array[{text, tone, target, subtext}] 或 String
		var dlgs_raw = co.get("dialogue", [])
		var dlgs: Array = dlgs_raw if dlgs_raw is Array else [dlgs_raw]
		for d in dlgs:
			if d is Dictionary:
				lines.append("  - 说: %s [%s]" % [d.get("text", ""), d.get("tone", "")])
			else:
				lines.append("  - 说: %s" % str(d))
		var actions_raw = co.get("actions", [])
		var actions: Array = actions_raw if actions_raw is Array else [actions_raw]
		if actions.size() > 0:
			var action_strs: Array = []
			for a in actions:
				if a is Dictionary:
					action_strs.append(a.get("description", str(a)))
				else:
					action_strs.append(str(a))
			lines.append("行动: %s" % "；".join(action_strs))
		var arc: String = str(co.get("emotional_arc", ""))
		if arc != "":
			lines.append("情感弧线: %s" % arc)
		var stance: Variant = co.get("stance_change", null)
		if stance != null and stance is Dictionary:
			lines.append("态度变化: %s → 原因: %s" % [stance.get("new_attitude", ""), stance.get("reason", "")])
		lines.append("")

	# 最近叙事（保持连贯性）
	if recent != "":
		lines.append("## 最近叙事（接续上文）")
		lines.append(recent)
		lines.append("")

	lines.append("---")
	lines.append("请根据以上所有信息，创作本场景的叙事散文。先写散文正文，然后用 ---JSON--- 分隔，最后输出元数据 JSON。")

	return "\n".join(lines)


## 执行编织
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	_log_info("→ 编织叙事散文...")
	MananaLogger.log_layer("L3", "SceneComposer 启动 — %d 角色输出" % (input_data.get("character_outputs", []) as Array).size())

	# json_mode: false — 输出是散文，不是 JSON
	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": false, "temperature": 0.9})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var content: String = result.get("content", "") as String

	# 提取散文和末尾元数据 JSON
	var narrative_only: String = _strip_json_suffix(content)
	var json_data: Dictionary = _extract_ending_json(content)

	# 验证提取的 JSON
	if not json_data.is_empty():
		var validation: Dictionary = MananaSchema.validate_composer_output(json_data)
		if not validation.get("valid", false):
			_log_warn("元数据验证警告: %s" % str(validation.get("errors", [])))

	# 确保 narrative_text 不为空
	if narrative_only.strip_edges() == "":
		# 回退: 整个内容作为叙事文本
		narrative_only = content
		json_data = {"ending_hook": "", "action_hints": [], "music_mood": ""}

	_log_info("→ 叙事散文 (%d 字符), 钩子: %s" % [narrative_only.length(), json_data.get("ending_hook", "")])

	MananaLogger.log_layer("L3", "SceneComposer 完成 — %d 字符叙事" % narrative_only.length())

	return {
		"ok": true,
		"content": narrative_only,
		"raw": json_data,
	}


## 从文本末尾提取 ---JSON--- 之后的 JSON 块
func _extract_ending_json(text: String) -> Dictionary:
	var idx: int = text.find(JSON_SEPARATOR)
	if idx == -1:
		# 尝试另一种分隔符: 三个空行后 JSON
		idx = text.find("\n\n\n{")
		if idx != -1:
			idx += 2  # 定位到第三个 \n
		else:
			# 尝试直接在末尾找 JSON 花括号
			return _try_extract_trailing_json(text)

	var json_text: String = ""
	if text.find(JSON_SEPARATOR) != -1:
		json_text = text.substr(idx + JSON_SEPARATOR.length()).strip_edges()
	else:
		json_text = text.substr(idx + 1).strip_edges()

	# 如果以 { 开头，尝试提取完整 JSON 对象
	if json_text.begins_with("{"):
		var brace_block: String = _extract_brace_block(json_text)
		if brace_block != "":
			json_text = brace_block

	return _try_parse_json(json_text)


## 去掉文本末尾的 ---JSON--- 及其后的所有内容
func _strip_json_suffix(text: String) -> String:
	var suffix_idx: int = text.find(JSON_SEPARATOR)
	if suffix_idx == -1:
		# 尝试在末尾找到 {
		var last_brace: int = text.rfind("\n{")
		if last_brace != -1:
			var after: String = text.substr(last_brace + 1).strip_edges()
			if after.begins_with("{") and after.ends_with("}"):
				return text.substr(0, last_brace).strip_edges()
		return text.strip_edges()

	return text.substr(0, suffix_idx).strip_edges()


## 尝试从文本末尾提取最后一个 JSON 对象作为回退策略
func _try_extract_trailing_json(text: String) -> Dictionary:
	# 从后往前找 {，看最后一段是否是完整 JSON
	var trailing_brace: int = text.rfind("{")
	if trailing_brace == -1:
		return {}

	var candidate: String = text.substr(trailing_brace)
	var trailing_block: String = _extract_brace_block(candidate)
	if trailing_block != "":
		return _try_parse_json(trailing_block)

	return {}
