class_name PlanSynthesizerAgent
extends BaseMananaAgent

## P1-3 多视角融合器 — 将 plot-driven 和 character-driven 两个 beat_plan 融合为单一方案。
## model_tier: medium, temperature: 0.4, max_tokens: 1024, json_mode: true

func _init() -> void:
	agent_name = "PlanSynthesizer"
	model_tier = "medium"


## 融合两个视角的节拍方案
## [param input_data] {plot_plan: Dictionary, character_plan: Dictionary, scene_context: Dictionary}
## [returns] {ok, raw: Dictionary}
func run(input_data: Dictionary) -> Dictionary:
	var system_prompt: String = _load_prompt_text("res://prompts/synthesizer.md")

	var plot_plan: Dictionary = input_data.get("plot_plan", {}) as Dictionary
	var char_plan: Dictionary = input_data.get("character_plan", {}) as Dictionary
	var scene_context: Dictionary = input_data.get("scene_context", {}) as Dictionary

	var user_prompt: String = "场景上下文:\n" + JSON.stringify(scene_context, "  ") + "\n\n剧情视角方案:\n" + JSON.stringify(plot_plan, "  ") + "\n\n角色视角方案:\n" + JSON.stringify(char_plan, "  ")

	var result: Dictionary = await _call_llm(system_prompt, user_prompt, {
		"temperature": 0.4,
		"max_tokens": 1024,
		"json_mode": true,
	})

	var parsed: Dictionary = _parse_json_response(result)
	if not parsed.get("ok", false):
		# 降级: 取非空的视角方案作为回退
		var fallback: Dictionary = char_plan
		if fallback.is_empty():
			fallback = plot_plan
		return {"ok": true, "raw": fallback}

	return {"ok": true, "raw": parsed.get("data", {}) as Dictionary}


## 加载 prompt 模板文件
func _load_prompt_text(path: String) -> String:
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		return "融合两个节拍方案为单一方案，输出标准 beat_plan JSON。"
	var text: String = f.get_as_text()
	f.close()
	return text
