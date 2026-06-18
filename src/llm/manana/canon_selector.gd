class_name CanonSelectorAgent
extends BaseMananaAgent

## P2-1 Canon 语义选择器 — 从候选 canon 中选出与当前场景最相关的 Top-K。
## model_tier: light, temperature: 0, max_tokens: 200, json_mode: true

func _init() -> void:
	agent_name = "CanonSelector"
	model_tier = "light"


## 从候选 canon 中语义选择最相关项
## [param input_data] {location_name, location_description, player_action, characters_on_scene, threads_summary, canon_candidates}
## [returns] {prioritized_ids: Array[String], excluded_reason: String}
func run(input_data: Dictionary) -> Dictionary:
	var system_prompt: String = _load_prompt_text("res://prompts/canon_selector.md")
	var user_prompt: String = JSON.stringify(input_data, "  ")

	var result: Dictionary = await _call_llm(system_prompt, user_prompt, {
		"temperature": 0.0,
		"max_tokens": 200,
		"json_mode": true,
	})

	var parsed: Dictionary = _parse_json_response(result)
	if not parsed.get("ok", false):
		return {
			"prioritized_ids": [],
			"excluded_reason": "selector parse failed",
		}

	var data: Dictionary = parsed.get("data", {}) as Dictionary
	return {
		"prioritized_ids": data.get("prioritized_ids", []) as Array,
		"excluded_reason": str(data.get("excluded_reason", "")),
	}


## 加载 prompt 模板文件
func _load_prompt_text(path: String) -> String:
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return "从候选canon中选Top-K最相关，输出: {\"prioritized_ids\":[],\"excluded_reason\":\"\"}"
	var text: String = f.get_as_text()
	f.close()
	return text
