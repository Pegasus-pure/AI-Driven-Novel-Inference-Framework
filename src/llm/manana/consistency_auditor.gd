class_name ConsistencyAuditor
extends BaseMananaAgent

## Layer 3b — 一致性审计 Agent (model_tier: medium)
## 检测 Composer 生成的叙事文本中的角色漂移、事实矛盾、规则违反和连续性断裂。
##
## 审计 FAIL 行为: 记录 WARNING 日志 + 发送 EventBus.agent_error 信号。
## 不自动触发重写——Pipeline (T05) 接收到 FAIL 后可选择手动触发重写。


func _init() -> void:
	agent_name = "ConsistencyAuditor"
	model_tier = "medium"


func build_system_prompt() -> String:
	return """你是一位**叙事一致性审计师**。你的任务是仔细审查一段叙事文本，检查其中是否存在以下四类问题：

## 检测标准

### 1. 角色漂移 (character_drift)
角色的言行与其设定性格、说话风格、核心恐惧不符。例如：
- 一个设定为"沉默寡言"的角色忽然滔滔不绝
- 角色表现出与已知性格矛盾的情感反应
- 角色的说话风格与其 speech_style 设定不一致

### 2. 事实矛盾 (fact_contradiction)
叙事文本与已确立的事实冲突。例如：
- 角色A已被确认在图书馆，叙事中却说在花园
- 某物品已被破坏/丢失，叙事中却在使用
- 时间线错乱——事件的先后顺序矛盾

### 3. 规则违反 (rule_violation)
违反世界规则。例如：
- 世界观设定魔法无法在白天使用，但叙事中却在正午施法
- 违反了社会规则（如某个角色的身份不可能进入某场所）

### 4. 连续性断裂 (continuity_break)
与上一段叙事的衔接出现问题。例如：
- 上一段结束时是白天，本段开头变成了夜晚（无过渡）
- 对话话题突然跳跃，缺乏逻辑转换
- 角色位置无故瞬移

## 判断标准

- **critical**: 严重破坏叙事可信度，必须修复
- **major**: 明显问题，建议修复
- **minor**: 小瑕疵，可忽略

## 输出 JSON 格式

```json
{
  "verdict": "PASS",
  "issues": [],
  "overall_quality": {
    "character_consistency": 0.85,
    "plot_coherence": 0.90,
    "world_fidelity": 0.95
  }
}
```

如果发现问题，verdict 为 "FAIL"，issues 数组填写具体问题。每个 issue 包含：
- type: "character_drift" | "fact_contradiction" | "rule_violation" | "continuity_break"
- severity: "critical" | "major" | "minor"
- description: 问题的中文描述
- location_hint: 叙事文本中大致位置指引
- fix_suggestion: 修复建议（供后续手动重写参考）

## 重要原则

1. **宁可放过，不可误杀**: 当不确定时，倾向给 PASS。只有明确矛盾时才标记 FAIL。
2. **关注角色一致性**: 这是最重要的维度。角色是最容易漂移的元素。
3. **不要吹毛求疵**: 文学性的模糊表达和合理的叙事留白不是问题。
4. **考虑上下文**: 如果前文叙事提供了合理的过渡，即使跳跃较大也不算连续性断裂。
"""


func build_user_prompt(input_data: Dictionary) -> String:
	var narrative_text: String = str(input_data.get("narrative_text", ""))
	var personas: Dictionary = input_data.get("character_personas", {}) as Dictionary
	var world_rules: String = str(input_data.get("world_rules", ""))
	var recent_facts: Array = input_data.get("recent_facts", []) as Array
	var previous_narrative: String = str(input_data.get("previous_narrative", ""))

	var lines: Array[String] = []

	# 角色设定
	lines.append("## 角色设定（参考标准）")
	for char_id in personas:
		var p: Dictionary = personas[char_id] as Dictionary
		lines.append("### %s (%s)" % [str(p.get("name", char_id)), char_id])
		lines.append("核心性格: %s" % "、".join(p.get("core_traits", []) as Array))
		var speech: String = str(p.get("speech_style", ""))
		if speech != "":
			lines.append("说话风格: %s" % speech)
		var fear: String = str(p.get("core_fear", ""))
		if fear != "":
			lines.append("核心恐惧: %s" % fear)
		var facts: Array = p.get("known_facts", []) as Array
		if facts.size() > 0:
			lines.append("已知事实: %s" % "；".join(facts))
		lines.append("")

	# 世界规则
	if world_rules != "":
		lines.append("## 世界规则")
		lines.append(world_rules)
		lines.append("")

	# 最近已确立的事实
	if recent_facts.size() > 0:
		lines.append("## 最近已确立的事实")
		for f_ in recent_facts:
			var f: String = f_ as String
			lines.append("- %s" % f)
		lines.append("")

	# 上文叙事（检测连续性）
	if previous_narrative != "":
		lines.append("## 上段叙事（参考，检测连续性）")
		lines.append(previous_narrative)
		lines.append("")

	# 待审计的叙事文本
	lines.append("## 待审计叙事文本")
	lines.append("---")
	lines.append(narrative_text)
	lines.append("---")
	lines.append("")

	lines.append("请审计以上叙事文本，输出 JSON 格式的审计结果。")

	return "\n".join(lines)


## 执行审计
func run(input_data: Dictionary) -> Dictionary:
	var sys: String = build_system_prompt()
	var usr: String = build_user_prompt(input_data)

	_log_info("→ 审计叙事一致性...")
	var narrative_len: int = str(input_data.get("narrative_text", "")).length()
	MananaLogger.log_layer("L3b", "ConsistencyAuditor 启动 — 叙事长度 %d 字符" % narrative_len)

	var result: Dictionary = await _call_llm(sys, usr, {"json_mode": true, "temperature": 0.3})

	if not result.get("ok", false):
		var err_msg: String = str(result.get("error", "LLM call failed"))
		_emit_agent_error("LLM调用失败: %s" % err_msg)
		return {"ok": false, "content": "", "raw": {}, "error": err_msg}

	var parsed: Dictionary = _parse_json_response(result)
	if parsed.get("error", "") != "":
		var parse_err: String = str(parsed.get("error", ""))
		_emit_agent_error("JSON解析失败: %s" % parse_err)
		return {"ok": false, "content": result.get("content", ""), "raw": {}, "error": "JSON parse failed: " + parse_err}

	var data: Dictionary = parsed.get("data", {}) as Dictionary

	# 补充默认值
	if not data.has("verdict"):
		data["verdict"] = "PASS"
	if not data.has("issues"):
		data["issues"] = []
	if not data.has("overall_quality"):
		data["overall_quality"] = {"character_consistency": 0.5, "plot_coherence": 0.5, "world_fidelity": 0.5}

	var validation: Dictionary = MananaSchema.validate_auditor_output(data)
	if not validation.get("valid", false):
		_log_warn("输出验证警告: %s" % str(validation.get("errors", [])))

	var verdict: String = str(data.get("verdict", "PASS"))
	var issues: Array = data.get("issues", []) as Array

	if verdict == "FAIL":
		_handle_audit_fail(data, issues)
	else:
		_log_info("→ 审计通过 ✓")
		var quality: Dictionary = data.get("overall_quality", {}) as Dictionary
		MananaLogger.log_layer("L3b", "ConsistencyAuditor PASS — 角色一致: %.2f, 情节连贯: %.2f, 世界保真: %.2f" % [
			quality.get("character_consistency", 0.0), quality.get("plot_coherence", 0.0), quality.get("world_fidelity", 0.0)
		])

	return {"ok": true, "content": result.get("content", ""), "raw": data}


## 处理审计 FAIL — 记录 WARNING + 发送 EventBus.agent_error 信号，不自动重写
func _handle_audit_fail(data: Dictionary, issues: Array) -> void:
	_log_warn("⚠ 审计 FAIL — 发现 %d 个问题:" % issues.size())

	for i in range(issues.size()):
		var issue: Dictionary = issues[i] as Dictionary
		var severity: String = str(issue.get("severity", "major"))
		var itype: String = str(issue.get("type", "unknown"))
		var desc: String = str(issue.get("description", "(无描述)"))
		var loc: String = str(issue.get("location_hint", ""))

		_log_warn("  [%s] %s: %s (位置: %s)" % [severity, itype, desc, loc])

	# 发送 agent_error 信号
	_emit_agent_error("审计 FAIL: %d 个问题" % issues.size())

	MananaLogger.log_warning(agent_name, "审计 FAIL — 发现 %d 个不一致问题，需人工审查" % issues.size())
	MananaLogger.log_layer("L3b", "ConsistencyAuditor FAIL — %d issues, %d critical" % [
		issues.size(),
		_count_critical(issues),
	])


## 统计 critical 级别问题数量
func _count_critical(issues: Array) -> int:
	var count: int = 0
	for i in range(issues.size()):
		var critical_issue: Dictionary = issues[i] as Dictionary
		if critical_issue.get("severity", "") == "critical":
			count += 1
	return count


## 发送 agent_error 到 EventBus（不直接依赖 Autoload，通过静态方法安全访问）
func _emit_agent_error(error_msg: String) -> void:
	# 通过 Engine.get_singleton 安全访问 EventBus Autoload
	var event_bus: Node = _get_event_bus()
	if event_bus:
		event_bus.agent_error.emit(agent_name, error_msg)
	else:
		# 回退: 仅记录日志
		_log_warn("EventBus 不可用，仅记录日志: %s" % error_msg)


## 安全获取 EventBus 单例
func _get_event_bus() -> Node:
	# 尝试通过 Engine.get_singleton 获取
	if Engine.has_singleton("EventBus"):
		return Engine.get_singleton("EventBus") as Node
	# 尝试通过主场景树获取
	var main_tree: SceneTree = Engine.get_main_loop() as SceneTree
	if main_tree and main_tree.root:
		return main_tree.root.get_node_or_null("/root/EventBus") as Node
	return null
