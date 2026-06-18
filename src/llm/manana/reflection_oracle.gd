class_name ReflectionOracle
extends BaseMananaAgent

## Layer 5 — 反思神谕 Agent (model_tier: strong, 低频)
## 高阶叙事评估——每 5 节拍或场景切换时由 T05 Pipeline 条件触发调用。
##
## 不在 Pipeline 主线中。输出通过 oracle_context 字段作为隐藏上下文
## 注入下一个 Director 的 system_prompt（具体连接由 T05 实现）。
##
## 评估维度:
## - 节奏评估: 叙事推进速度是否合理
## - 角色观察: 每个角色的弧线进展和隐藏机会
## - 线索健康: 各叙事线索的新鲜度
## - 叙事机会: 潜在的新叙事方向
## - 基调建议: 下一场景的情绪建议


func _init() -> void:
	agent_name = "ReflectionOracle"
	model_tier = "strong"


func build_system_prompt() -> String:
	return """你是一位**叙事反思神谕**（Narrative Reflection Oracle）。

你的视角高于场景导演和编剧——你从宏观层面审视整部小说的叙事健康度。你不是在写故事，而是在**评估**故事的运行状况，发现被忽略的机会，预警潜在的问题。

## 评估维度

### 1. 节奏评估 (pacing_assessment)
审视最近 5 个节拍的叙事节奏：
- **too_fast**: 情节推进过快，缺少铺垫、角色发展或环境描写
- **balanced**: 节奏合理，情节/角色/环境比例恰当
- **too_slow**: 情节停滞，过度描写或对话冗长

### 2. 角色观察 (character_observations)
对每个活跃角色：
- **arc_progress**: 角色弧线的当前进展评估
- **hidden_opportunity**: 一个被忽略的叙事机会——这个角色的性格/背景/当前处境中隐藏的戏剧可能性

### 3. 线索健康 (thread_health)
对每条活跃线索：
- **staleness**:
  - fresh: 最近被积极推进或新创建
  - stale: 有一段时间未被推进，但仍有潜力
  - stuck: 长期停滞，可能存在问题需要解决
- **suggestion**: 如何激活 stale/stuck 线索的建议

### 4. 叙事机会 (narrative_opportunities)
从全局视角发现的潜在叙事方向。例如：
- 两个尚未互动的角色之间可能存在冲突
- 一个被忽略的地点可能蕴含秘密
- 一个角色的隐藏动机可能引发故事转折

### 5. 基调建议 (tone_recommendation)
针对下一场景的情绪/氛围建议。考虑到叙事的起伏节奏——在紧张之后需要舒缓，在平静之后需要高潮。

## 输出 JSON 格式

```json
{
  "pacing_assessment": {
    "rating": "balanced",
    "suggestion": "当前节奏适中，下一场景可以适当加速切入主线冲突"
  },
  "character_observations": [
    {
      "char_id": "char_001",
      "arc_progress": "角色正在从被动接受到主动探索的转变中",
      "hidden_opportunity": "角色的核心恐惧尚未被触发——可以设计一个场景让其直面恐惧"
    }
  ],
  "thread_health": [
    {
      "thread_id": "thread_001",
      "staleness": "fresh",
      "suggestion": "继续保持当前的推进节奏"
    }
  ],
  "narrative_opportunities": [
    "图书馆的秘密通道尚未被发现——可以将探索作为下一个场景的主题",
    "角色A和角色B之间微妙的不信任感可以发展为一场对峙"
  ],
  "tone_recommendation": "建议下一场景使用悬疑基调——当前的平静中应该埋下不安的种子"
}
```

## 评估原则

1. **建设性**: 发现问题时，必须同时给出具体可行的建议
2. **全局视角**: 你不是在评判单个节拍，而是审视整体趋势
3. **尊重创作者**: 你的建议是参考性的，不是强制性的——最终的叙事决策权在导演
4. **数据驱动**: 基于实际的角色发展和线索进度，不是主观偏好
5. **鼓励创新**: 积极发现被忽略的叙事可能性和隐藏的戏剧冲突
"""


func build_user_prompt(input_data: Dictionary) -> String:
	var recent_beats: Array = input_data.get("recent_beats_summary", []) as Array
	var threads_summary: String = str(input_data.get("active_threads_summary", ""))
	var character_arcs: Array = input_data.get("character_arcs", []) as Array
	var divergence: float = input_data.get("divergence_trend", 0.0) as float
	var player: Dictionary = input_data.get("player_profile", {}) as Dictionary

	var lines: Array[String] = []

	# 最近节拍摘要
	lines.append("## 最近节拍 (%d个)" % recent_beats.size())
	for i in range(recent_beats.size()):
		lines.append("### 节拍 %d" % (i + 1))
		lines.append(str(recent_beats[i]))
		lines.append("")

	# 角色弧线
	if character_arcs.size() > 0:
		lines.append("## 角色弧线追踪")
		for i in range(character_arcs.size()):
			var arc: Dictionary = character_arcs[i] as Dictionary
			lines.append("### %s (%s)" % [str(arc.get("name", "??")), str(arc.get("char_id", "??"))])
			lines.append("情绪轨迹: %s" % " → ".join(arc.get("mood_progression", []) as Array))
			var actions: Array = arc.get("key_actions", []) as Array
			if actions.size() > 0:
				lines.append("关键行动: %s" % "；".join(actions))
			var shift: String = str(arc.get("stance_shift", ""))
			if shift != "":
				lines.append("态度转变: %s" % shift)
			lines.append("")

	# 线索状态摘要
	lines.append("## 线索状态")
	lines.append(threads_summary)
	lines.append("")

	# 世界偏离度趋势
	lines.append("## 世界偏离度趋势")
	lines.append("当前偏离度: %.2f" % divergence)
	lines.append("")

	# 玩家画像
	if not player.is_empty():
		lines.append("## 玩家画像")
		for key in player:
			lines.append("- %s: %s" % [key, str(player[key])])
		lines.append("")

	lines.append("---")
	lines.append("请从宏观层面评估以上叙事，给出你的神谕报告 JSON。")

	return "\n".join(lines)


## 执行反思评估
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	var beat_count: int = (input_data.get("recent_beats_summary", []) as Array).size()
	_log_info("→ 反思评估 (%d 节拍回顾)..." % beat_count)
	MananaLogger.log_layer("L5", "ReflectionOracle 启动 — %d 节拍回顾, 偏离度 %.2f" % [
		beat_count, input_data.get("divergence_trend", 0.0)
	])

	# Oracle 使用强模型，higher temperature 鼓励创造性洞察
	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.9, "max_tokens": 3072})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 补充默认值
	_ensure_defaults(data)

	var validation: Dictionary = MananaSchema.validate_oracle_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证警告: %s" % str(validation.get("errors", [])))

	var pacing: Dictionary = data.get("pacing_assessment", {}) as Dictionary
	var observations: Array = data.get("character_observations", []) as Array
	var thread_health: Array = data.get("thread_health", []) as Array
	var opportunities: Array = data.get("narrative_opportunities", []) as Array

	_log_info("→ 节奏: %s, 角色观察: %d, 线索诊断: %d, 机会: %d" % [
		pacing.get("rating", "?"), observations.size(), thread_health.size(), opportunities.size()
	])

	MananaLogger.log_layer("L5", "ReflectionOracle 完成 — 节奏评级: %s, %d 叙事机会" % [
		pacing.get("rating", "?"), opportunities.size()
	])

	return {"ok": true, "content": result.get("content", ""), "raw": data}


## 为缺失字段补充默认值
func _ensure_defaults(data: Dictionary) -> void:
	var defaults: Dictionary = {
		"pacing_assessment": {"rating": "balanced", "suggestion": ""},
		"character_observations": [],
		"thread_health": [],
		"narrative_opportunities": [],
		"tone_recommendation": "",
	}
	for key in defaults:
		if not data.has(key):
			data[key] = defaults[key]
