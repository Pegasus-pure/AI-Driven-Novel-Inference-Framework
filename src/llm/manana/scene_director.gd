class_name SceneDirector
extends BaseMananaAgent

## Layer 1 — 场景导演 Agent (model_tier: strong)
## 接收完整 SceneContext，决定节拍计划、交互对分组、出场角色、场景基调。
## 是整个 MaNA 管线的叙事决策中枢。

func _init() -> void:
	agent_name = "SceneDirector"
	model_tier = "strong"


## 返回导演系统提示词（默认值，T05 可外移到 res://prompts/director.md）
func build_system_prompt() -> String:
	return """你是一个互动叙事系统的**场景导演**。

你的任务是：根据当前世界状态和玩家的行动，决定下一个叙事节拍的走向。

你拥有绝对的叙事调度权——选择哪些角色出场、谁和谁产生交互、场景的基调是什么。

## 输出 JSON 格式

必须输出一个严格的 JSON 对象，包含以下字段：

```json
{
  "beat_id": "当前节拍唯一标识(字符串)",
  "narrative_mode": "exploration|dialogue|conflict|revelation 四选一",
  "beat_summary": "1-2 句话描述本节拍将发生什么",
  "featured_characters": ["char_id_1", "char_id_2"],
  "interaction_pairs": [
    {
      "pair_id": "pair_01",
      "char_ids": ["char_a", "char_b"],
      "pair_type": "dialogue|action|both"
    }
  ],
  "unpaired_characters": ["char_id"],
  "scene_tone": "紧张|友好|暧昧|悲伤|欢快|神秘|庄严|恐惧|平淡",
  "priority_thread_ids": ["thread_id"],
  "required_canon": ["char_id"]
}
```

## 字段说明

- **beat_id**: 当前节拍 ID，建议格式 "beat_场景_序号"
- **narrative_mode**: 
  - exploration: 探索环境、收集信息
  - dialogue: 对话为主、角色交流
  - conflict: 冲突/对抗/紧张局面
  - revelation: 揭示/发现/真相揭露
- **beat_summary**: 简练概括本节拍的核心叙事事件
- **featured_characters**: 所有在本节拍中出场的角色 char_id 列表
- **interaction_pairs**: 角色之间的交互对。两个角色对话/互动为一对。玩家总是隐式在场，不需要放入 pair
- **unpaired_characters**: 出场但不参与交互对的独立角色
- **scene_tone**: 场景整体氛围
- **priority_thread_ids**: 本节拍应推进的叙事线索 ID 列表
- **required_canon**: 需要完整 personality 信息的角色 char_id 列表

## 导演原则

1. 每次节拍推进 1-2 个线索，不要试图一次性推进所有线索
2. 交互对最多 2 组（4 个角色），避免场景过于拥挤
3. 根据世界偏离度调整叙事策略——偏离度低时忠实原著，偏离度高时大胆创新
4. 优先选择与玩家当前行动相关的角色出场
5. 场景基调应与当前情绪和位置氛围一致
"""


## 构建用户提示词: 将 SceneContext 序列化后交给 LLM
func build_user_prompt(input_data: Dictionary) -> String:
	var scene_context: Dictionary = input_data.get("scene_context", {}) as Dictionary
	var lines: Array[String] = []

	lines.append("## 当前世界状态")
	lines.append("")

	# 基本信息
	lines.append("游戏时间: %s" % scene_context.get("game_time", "未知"))
	lines.append("世界偏离度: %.2f" % scene_context.get("divergence", 0.0))
	lines.append("")

	# 地点
	var location: Dictionary = scene_context.get("location", {}) as Dictionary
	lines.append("### 当前地点")
	lines.append("名称: %s" % location.get("name", "未知"))
	if location.get("description", "") != "":
		lines.append("描述: %s" % location["description"])
	if location.get("atmosphere", "") != "":
		lines.append("氛围: %s" % location["atmosphere"])
	lines.append("")

	# 玩家
	var player: Dictionary = scene_context.get("player", {}) as Dictionary
	lines.append("### 玩家")
	lines.append("玩家行动: %s" % player.get("action", "(无)"))
	var profile: Dictionary = player.get("profile", {}) as Dictionary
	var traits: Array = profile.get("traits", []) as Array
	lines.append("已发现性格: %s" % ("、".join(traits) if traits.size() > 0 else "未知"))
	lines.append("当前动机: %s" % profile.get("motivation", "未知"))
	lines.append("行为倾向: %s" % profile.get("tendency", "中立"))
	var rep: Dictionary = player.get("reputation", {}) as Dictionary
	if rep.size() > 0:
		lines.append("对各角色态度:")
		for char_id in rep:
			lines.append("  %s: %s" % [char_id, rep[char_id]])
	lines.append("")

	# 角色
	var characters: Array = scene_context.get("characters", []) as Array
	lines.append("### 当前场景角色 (%d人)" % characters.size())
	for c_ in characters:
		var c: Dictionary = c_ as Dictionary
		lines.append("- %s (id: %s)" % [str(c.get("name", "??")), str(c.get("char_id", "??"))])
		var cs: Dictionary = c.get("current_state", {}) as Dictionary
		lines.append("  地点: %s | 情绪: %s | 目标: %s" % [
			str(cs.get("location", "?")), str(cs.get("mood", "中性")), str(cs.get("goal", "无"))
		])
		if c.get("relation_to_player", "") != "":
			lines.append("  对玩家: %s" % c["relation_to_player"])
		if c.get("personality", "") != "":
			lines.append("  性格: %s" % c["personality"])
		var facts: Array = c.get("known_facts", []) as Array
		if facts.size() > 0:
			lines.append("  已知事实: %s" % "；".join(facts))
	lines.append("")

	# 活跃线索
	var threads: Array = scene_context.get("active_threads", []) as Array
	lines.append("### 活跃叙事线索 (%d条)" % threads.size())
	for t_ in threads:
		var t: Dictionary = t_ as Dictionary
		lines.append("- [%s] %s (进度: %.0f%%, 张力: %.1f)" % [
			str(t.get("id", "?")), str(t.get("title", "?")), t.get("progress", 0.0) as float * 100, t.get("tension", 0.3) as float
		])
	lines.append("")

	# 最近历史
	var history: Array = scene_context.get("recent_history", []) as Array
	if history.size() > 0:
		lines.append("### 最近叙事事件")
		for evt_ in history:
			var evt: Dictionary = evt_ as Dictionary
			lines.append("- [%s] %s" % [str(evt.get("time", "")), str(evt.get("summary", ""))])
		lines.append("")

	# 记忆
	var scene_mem: Array = scene_context.get("scene_memory", []) as Array
	var long_mem: Array = scene_context.get("long_term_memory", []) as Array
	if scene_mem.size() > 0:
		lines.append("### 场景记忆")
		for m in scene_mem:
			lines.append("- %s" % m)
		lines.append("")
	if long_mem.size() > 0:
		lines.append("### 长期记忆")
		for m in long_mem:
			lines.append("- %s" % m)
		lines.append("")

	# 世界规则
	var rules: String = str(scene_context.get("relevant_world_rules", ""))
	if rules != "":
		lines.append("### 相关世界规则")
		lines.append(rules)
		lines.append("")

	lines.append("请根据以上信息，输出你的导演计划 JSON。")

	return "\n".join(lines)


## 执行导演决策
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	_log_info("→ 调度节拍...")
	MananaLogger.log_layer("L1", "SceneDirector 启动 — 分析场景上下文 (%d 角色, %d 线索)" % [
		(input_data.get("scene_context", {}).get("characters", []) as Array).size(),
		(input_data.get("scene_context", {}).get("active_threads", []) as Array).size(),
	])

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.8})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary
	var validation: Dictionary = MananaSchema.validate_director_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证失败: %s" % str(validation.get("errors", [])))
		# 验证失败不阻断，仍然返回数据（LLM 可能未按 schema 输出，但内容可能有用）

	_log_info("→ 节拍: %s, 模式: %s, 出场: %d 角色" % [
		data.get("beat_id", "?"), data.get("narrative_mode", "?"),
		(data.get("featured_characters", []) as Array).size()
	])

	MananaLogger.log_layer("L1", "SceneDirector 完成 — 节拍: %s" % data.get("beat_id", "?"))

	return {"ok": true, "content": result.get("content", ""), "raw": data}
