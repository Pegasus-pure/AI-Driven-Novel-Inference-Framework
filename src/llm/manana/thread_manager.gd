class_name ThreadManager
extends BaseMananaAgent

## Layer 4b — 叙事线索管理 Agent (model_tier: medium)
## 管理叙事线索的生命周期: 推进、创建、关闭、张力调节。
##
## 与 T05 Pipeline 协作:
## - Pipeline 传入当前活跃线索列表 + 线池配置
## - ThreadManager 返回线索变更方案
## - Pipeline 负责将变更应用到 WorldState


func _init() -> void:
	agent_name = "ThreadManager"
	model_tier = "medium"


func build_system_prompt() -> String:
	return """你是一位**叙事线索管理者**。你的任务是分析当前叙事节拍，决定如何管理故事线索——哪些该推进、哪些该关闭、是否应该开启新线索。

## 线索类型

- **main**: 主线——故事的核心驱动力，通常只有 1 条活跃主线
- **side**: 支线——丰富世界观和角色深度的辅助线索

## 线索生命周期

### 推进 (thread_advances)
- 线索在叙事中被提及/推进时，增加 progress（0.0~1.0）
- 本节拍直接解决了线索的核心问题 → 大幅推进 (+0.3~0.5)
- 本节拍只是提及或铺垫 → 小幅推进 (+0.05~0.15)
- 进度达到 1.0 的线索应该被关闭

### 新建 (new_threads)
- 每个新线索必须有一个核心问题 (question)
- 这个问题是驱动该线索发展的引擎
- 例如: "失踪的导师到底去了哪里？"

### 关闭 (closed_threads)
- 当线索的核心问题得到回答时关闭
- 进度达到 1.0 自动被视为完成
- 关闭的线索会被移入 WorldState 的 completed_threads

### 张力调节 (tension_adjustments)
- tension: 线索当前的紧张程度 (0.0~1.0)
- 揭露新信息 → 可能增加或减少张力
- 线索长期未被推进 → 张力自然衰减
- 线索被直接面对 → 张力急剧上升

## 线池限制
- 最多同时 1 条活跃主线
- 最多同时 2 条活跃支线
- 最多 5 条子线索
- 关闭旧线索后腾出空间才能开新线

## 输出 JSON 格式

```json
{
  "thread_advances": [
	{"thread_id": "thread_001", "delta": 0.15}
  ],
  "new_threads": [
	{"title": "新的谜团", "type": "side", "question": "谁在深夜的图书馆里？"}
  ],
  "closed_threads": ["thread_003"],
  "tension_adjustments": [
	{"thread_id": "thread_001", "new_tension": 0.7}
  ]
}
```

## 决策原则

1. **一次只做有意义的变化**: 不要为了变化而变化。没有线索被推进就是空数组。
2. **关闭要果断**: 如果一个线索的问题已经被回答，果断关闭它。
3. **新建要谨慎**: 新线索必须根植于当前叙事，不是凭空创造。
4. **张力要有起伏**: 不要让所有线索都在高张力——叙事需要节奏。
5. **主线优先**: 优先推进和调节主线，支线辅助。
"""


func build_user_prompt(input_data: Dictionary) -> String:
	var narrative_text: String = str(input_data.get("narrative_text", ""))
	var beat_summary: String = str(input_data.get("beat_summary", ""))
	var active_threads: Array = input_data.get("active_threads", []) as Array
	var pool_config: Dictionary = input_data.get("thread_pool_config", {}) as Dictionary

	var lines: Array[String] = []

	lines.append("## 当前节拍")
	lines.append("节拍摘要: %s" % beat_summary)
	lines.append("")

	# 叙事文本（截断过长文本以节省 token）
	lines.append("## 叙事文本")
	var truncated: String = narrative_text
	if narrative_text.length() > 3000:
		truncated = narrative_text.left(3000) + "\n...(后续内容已省略)"
	lines.append(truncated)
	lines.append("")

	# 活跃线索
	lines.append("## 当前活跃线索 (%d条)" % active_threads.size())
	if active_threads.size() == 0:
		lines.append("(暂无活跃线索)")
	else:
		for i in range(active_threads.size()):
			var t: Dictionary = active_threads[i] as Dictionary
			lines.append("### [%s] %s" % [str(t.get("id", "?")), str(t.get("title", "无标题"))])
			lines.append("- 类型: %s" % str(t.get("type", "side")))
			lines.append("- 进度: %.0f%%" % (t.get("progress", 0.0) as float * 100))
			lines.append("- 张力: %.1f" % (t.get("tension", 0.5) as float))
			lines.append("- 优先级: %.1f" % (t.get("priority", 0.5) as float))
			var question: String = str(t.get("question", ""))
			if question != "":
				lines.append("- 核心问题: %s" % question)
			lines.append("")

	# 线池配置
	lines.append("## 线池限制")
	lines.append("最大活跃主线: %d" % (pool_config.get("max_active_main", 1) as int))
	lines.append("最大活跃支线: %d" % (pool_config.get("max_active_side", 2) as int))
	lines.append("最大子线索: %d" % (pool_config.get("max_child_threads", 5) as int))
	lines.append("")

	lines.append("请根据当前叙事节拍，管理线索状态。输出 JSON 格式的变更方案。")

	return "\n".join(lines)


## 执行线索管理
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	var active_count: int = (input_data.get("active_threads", []) as Array).size()
	_log_info("→ 管理叙事线索 (%d 活跃)..." % active_count)
	MananaLogger.log_layer("L4b", "ThreadManager 启动 — %d 活跃线索" % active_count)

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.4})

	if not result.get("ok", false):
		return {"ok": false, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + str(parsed.get("error", ""))}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 补充默认值
	_ensure_defaults(data)

	var validation: Dictionary = MananaSchema.validate_thread_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证警告: %s" % str(validation.get("errors", [])))

	# 验证逻辑约束
	var constraint_msg: String = _validate_constraints(data, input_data)
	if constraint_msg != "":
		_log_warn("线索约束警告: %s" % constraint_msg)

	var summary: String = _summarize_thread_changes(data)
	_log_info("→ %s" % summary)
	MananaLogger.log_layer("L4b", "ThreadManager 完成 — %s" % summary)

	return {"ok": true, "content": result.get("content", ""), "raw": data}


## 为缺失字段补充默认值
func _ensure_defaults(data: Dictionary) -> void:
	var defaults: Dictionary = {
		"thread_advances": [],
		"new_threads": [],
		"closed_threads": [],
		"tension_adjustments": [],
	}
	for key in defaults:
		if not data.has(key):
			data[key] = defaults[key]


## 验证线索管理的基本约束
## [returns] 约束违反消息，空字符串表示通过
func _validate_constraints(data: Dictionary, input_data: Dictionary) -> String:
	var pool: Dictionary = input_data.get("thread_pool_config", {}) as Dictionary
	var max_main: int = pool.get("max_active_main", 1) as int
	var max_side: int = pool.get("max_active_side", 2) as int

	var all_active_threads: Array = input_data.get("active_threads", []) as Array
	var closed: Array = data.get("closed_threads", []) as Array
	var new_threads: Array = data.get("new_threads", []) as Array
	var advances: Array = data.get("thread_advances", []) as Array

	# 统计关闭后剩余的各类线索数量
	var remaining_main: int = 0
	var remaining_side: int = 0

	for t_ in all_active_threads:
		var thread_entry: Dictionary = t_ as Dictionary
		var tid: String = str(thread_entry.get("id", ""))
		if tid in closed:
			continue
		if thread_entry.get("type", "") == "main":
			remaining_main += 1
		else:
			remaining_side += 1

	# 统计新线索中的类型
	var new_main: int = 0
	var new_side: int = 0
	for n_ in new_threads:
		var n: Dictionary = n_ as Dictionary
		if n.get("type", "") == "main":
			new_main += 1
		else:
			new_side += 1

	# 检查是否超过线池容量
	if remaining_main + new_main > max_main:
		return "主线数量将超过上限 %d (当前 %d + 新建 %d)" % [max_main, remaining_main, new_main]
	if remaining_side + new_side > max_side:
		return "支线数量将超过上限 %d (当前 %d + 新建 %d)" % [max_side, remaining_side, new_side]

	# 检查进度推进的合理性
	for a_ in advances:
		var a: Dictionary = a_ as Dictionary
		var delta: float = a.get("delta", 0.0) as float
		var advanced_id: String = str(a.get("thread_id", ""))
		if advanced_id in closed:
			return "关闭的线索 %s 不应该再被推进" % advanced_id
		if delta <= 0.0:
			return "线索 %s 的推进量 %f 无效（必须 > 0）" % [advanced_id, delta]
		if delta > 0.5:
			return "线索 %s 的推进量 %f 过大（单次最大 0.5）" % [advanced_id, delta]

	return ""


## 生成线索变更摘要
func _summarize_thread_changes(data: Dictionary) -> String:
	var parts: Array[String] = []

	var summary_advances: Array = data.get("thread_advances", []) as Array
	for a_ in summary_advances:
		var summary_a: Dictionary = a_ as Dictionary
		parts.append("推进[%s] +%.0f%%" % [summary_a.get("thread_id", "?"), (summary_a.get("delta", 0.0) as float) * 100])

	var summary_new_threads: Array = data.get("new_threads", []) as Array
	for n_ in summary_new_threads:
		var summary_n: Dictionary = n_ as Dictionary
		parts.append("新建[%s] %s" % [summary_n.get("type", "side"), summary_n.get("title", "?")])

	var summary_closed: Array = data.get("closed_threads", []) as Array
	for c_ in summary_closed:
		var c: String = c_ as String
		parts.append("关闭[%s]" % c)

	var tensions: Array = data.get("tension_adjustments", []) as Array
	for t_ in tensions:
		var tension_entry: Dictionary = t_ as Dictionary
		parts.append("张力[%s] → %.1f" % [tension_entry.get("thread_id", "?"), tension_entry.get("new_tension", 0.0)])

	if parts.size() == 0:
		return "无线索变更"

	return "；".join(parts)
