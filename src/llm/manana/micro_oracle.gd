class_name MicroOracleAgent
extends BaseMananaAgent

## P1-1 微 Oracle — 每拍结束后对叙事质量做一句话评价。
## model_tier: light, temperature: 0, max_tokens: 80, json_mode: true

func _init() -> void:
	agent_name = "MicroOracle"
	model_tier = "light"


## 评估上一拍叙事质量
## [param input_data] {narrative_summary: String, scene_context: Dictionary}
## [returns] {has_issue: bool, one_line_feedback: String, severity: String}
func run(input_data: Dictionary) -> Dictionary:
	var narrative_summary: String = str(input_data.get("narrative_summary", ""))
	var system_prompt: String = _load_prompt_text("res://prompts/micro_oracle.md")
	var user_prompt: String = "上一拍摘要:\n" + narrative_summary

	var result: Dictionary = await _call_llm(system_prompt, user_prompt, {
		"temperature": 0.0,
		"max_tokens": 80,
		"json_mode": true,
	})

	var parsed: Dictionary = _parse_json_response(result)
	if not parsed.get("ok", false):
		return {
			"has_issue": false,
			"one_line_feedback": "",
			"severity": "info",
		}

	var data: Dictionary = parsed.get("data", {}) as Dictionary
	return {
		"has_issue": data.get("has_issue", false) as bool,
		"one_line_feedback": str(data.get("one_line_feedback", "")),
		"severity": str(data.get("severity", "info")),
	}


## 加载 prompt 模板文件
func _load_prompt_text(path: String) -> String:
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return "评估叙事质量，输出JSON: {\"has_issue\":bool,\"one_line_feedback\":\"\",\"severity\":\"info/warning/alert\"}"
	var text: String = f.get_as_text()
	f.close()
	return text
