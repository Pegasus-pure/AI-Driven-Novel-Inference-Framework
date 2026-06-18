class_name PlanScorerAgent
extends BaseMananaAgent

## P0-2 Best-of-3 评分器 — 对 Director 产出的 beat_plan 做三维评分。
## model_tier: light, temperature: 0, max_tokens: 80, json_mode: true

func _init() -> void:
	agent_name = "PlanScorer"
	model_tier = "light"


## 评估节拍计划，返回三维分数 + 总分
## [param beat_plan] Director 产出的 beat_plan Dictionary
## [returns] {ok, total: int, scores: {thread_progress, character_naturalness, causal_link}, raw}
func run(beat_plan: Dictionary) -> Dictionary:
	var system_prompt: String = _load_prompt_text("res://prompts/scorer.md")
	var user_prompt: String = "评估以下节拍计划：\n" + JSON.stringify(beat_plan, "  ")

	var result: Dictionary = await _call_llm(system_prompt, user_prompt, {
		"temperature": 0.0,
		"max_tokens": 80,
		"json_mode": true,
	})

	var parsed: Dictionary = _parse_json_response(result)
	if not parsed.get("ok", false):
		return {
			"ok": false,
			"error": str(parsed.get("error", "scorer parse failed")),
			"raw": beat_plan,
		}

	var data: Dictionary = parsed.get("data", {}) as Dictionary
	return {
		"ok": true,
		"total": data.get("total", 0) as int,
		"scores": {
			"thread_progress": data.get("thread_progress", 0) as int,
			"character_naturalness": data.get("character_naturalness", 0) as int,
			"causal_link": data.get("causal_link", 0) as int,
		},
		"raw": beat_plan,
	}


## 加载 prompt 模板文件，读取失败时返回默认 prompt
func _load_prompt_text(path: String) -> String:
	var f: FileAccess = FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("PlanScorer: cannot load prompt " + path)
		return "评分以下节拍计划，输出 JSON: {\"thread_progress\":int,\"character_naturalness\":int,\"causal_link\":int,\"total\":int}"
	var text: String = f.get_as_text()
	f.close()
	return text
