class_name BaseMananaAgent
extends RefCounted

## MaNA 叙事管线中所有 Agent 的抽象基类。
## 提供 LLM 调用、JSON 解析、日志输出等通用能力。
## 子类只需重写 agent_name / model_tier / build_system_prompt / build_user_prompt / run。

# ============================================================
# 子类必须重写的属性
# ============================================================

## Agent 名称，用于日志和追踪
var agent_name: String = "base"

## 默认使用的模型层级: "strong" | "medium" | "light"
var model_tier: String = "medium"

# ============================================================
# 由 Pipeline 注入的依赖
# ============================================================

## 当前 Agent 绑定的 Provider 实例
var _provider: BaseLLMProvider = null

# ============================================================
# 依赖注入
# ============================================================

## 由 Pipeline 在初始化时调用，注入 Provider 实例（单 tier）。
## [param provider] 已配置好的 BaseLLMProvider 实例
func configure(provider: BaseLLMProvider) -> void:
	_provider = provider


## 获取当前 Agent 对应层级的模型名称。
func get_model_name() -> String:
	if _provider:
		return _provider.get_model_name(model_tier)
	return ""


# ============================================================
# 子类重写的方法
# ============================================================

## 构建系统提示词。子类必须重写。
## [returns] String — 完整的 system prompt
func build_system_prompt() -> String:
	return ""


## 构建用户提示词。子类必须重写。
## [param input_data] 输入数据，由 Pipeline 拼装后传入
## [returns] String — 完整的 user prompt
func build_user_prompt(_input_data: Dictionary) -> String:
	return ""


## 核心执行方法。子类必须重写。
## [param input_data] 输入数据，包含 scene_context 及其他 Agent 产出
## [returns] {"ok": bool, "content": String, "raw": Dictionary, "error": String}
func run(_input_data: Dictionary) -> Dictionary:
	return {"ok": false, "content": "", "raw": {}, "error": "NOT_IMPLEMENTED"}


# ============================================================
# 通用 LLM 调用
# ============================================================

## 封装 LLM 调用，统一日志格式和错误处理。
## [param system_prompt] 系统提示词
## [param user_prompt] 用户提示词
## [param options] 可选: {"model_tier": "strong", "temperature": 0.7, "max_tokens": 1024, "json_mode": false}
## [returns] {"ok": bool, "content": String, "raw": String, "tokens": int, "error": String}
func _call_llm(system_prompt: String, user_prompt: String, options: Dictionary = {}) -> Dictionary:
	var tier: String = options.get("model_tier", model_tier) as String

	# 模型名从 Provider 获取（多 Provider 架构下每个实例绑定单一 tier）
	var model: String = _provider.get_model_name(tier)
	if model == "":
		model = _provider._config.get("model", "") as String

	_log_info("→ request (model: %s, tier: %s)" % [model, tier])
	MananaLogger.log_agent_request(agent_name, user_prompt)

	# temperature / max_tokens 默认值从 Provider config 获取（Q2: Agent 仍可通过 options 覆盖）
	var result: Dictionary = await _provider.chat_async(system_prompt, user_prompt, {
		"model": model,
		"temperature": options.get("temperature", _provider._config.get("temperature", 0.7)),
		"max_tokens": options.get("max_tokens", _provider._config.get("max_tokens", 1024)),
		"json_mode": options.get("json_mode", false),
	})

	if result.get("ok", false):
		_log_info("← response (tokens: %d)" % result.get("tokens", 0))
		MananaLogger.log_agent_response(agent_name, result.get("content", ""), result.get("tokens", 0), true)
	else:
		_log_error("✗ error: %s" % result.get("error", "unknown"))
		MananaLogger.log_agent_response(agent_name, "", 0, false)

	return result


# ============================================================
# JSON 解析
# ============================================================

## 从 LLM 返回的文本中提取 JSON 对象。
## 策略: 先尝试直接解析整段文本；失败则尝试提取 markdown 代码块中的 JSON；
## 仍失败则用正则匹配最外层 {...} 块。
## [param response] LLM 调用返回的 {"ok": true, "content": "..."}
## [returns] {"ok": bool, "data": Dictionary, "error": String}
func _parse_json_response(response: Dictionary) -> Dictionary:
	if not response.get("ok", false):
		return {"ok": false, "data": {}, "error": response.get("error", "LLM call failed")}

	var content: String = response.get("content", "") as String
	if content == "":
		return {"ok": false, "data": {}, "error": "Empty LLM response"}

	# 策略 1: 直接解析
	var data: Dictionary = _try_parse_json(content)
	if not data.is_empty():
		return {"ok": true, "data": data, "error": ""}

	# 策略 2: 提取 markdown 代码块 ```json ... ```
	var code_block: String = _extract_markdown_json(content)
	if code_block != "":
		data = _try_parse_json(code_block)
		if not data.is_empty():
			return {"ok": true, "data": data, "error": ""}

	# 策略 3: 正则匹配最外层花括号对
	var brace_content: String = _extract_brace_block(content)
	if brace_content != "":
		data = _try_parse_json(brace_content)
		if not data.is_empty():
			return {"ok": true, "data": data, "error": ""}

	return {"ok": false, "data": {}, "error": "Failed to parse JSON from response: %s" % content.left(200)}


## 尝试调用 JSON.parse_string 解析文本
func _try_parse_json(text: String) -> Dictionary:
	var json: JSON = JSON.new()
	var err: int = json.parse(text)
	if err != OK:
		return {}
	var json_result: Variant = json.get_data()
	if json_result is Dictionary:
		return json_result as Dictionary
	return {}


## 提取 ```json ... ``` 代码块内容
func _extract_markdown_json(text: String) -> String:
	var start_tag: String = "```json"
	var start_idx: int = text.find(start_tag)
	if start_idx == -1:
		start_tag = "```"
		start_idx = text.find(start_tag)
	if start_idx == -1:
		return ""

	# 跳过开始标签行
	var newline_idx: int = text.find("\n", start_idx + start_tag.length())
	if newline_idx == -1:
		return ""

	var end_idx: int = text.find("```", newline_idx + 1)
	if end_idx == -1:
		return ""

	return text.substr(newline_idx + 1, end_idx - newline_idx - 1).strip_edges()


## 正则匹配最外层花括号对
func _extract_brace_block(text: String) -> String:
	var start: int = text.find("{")
	if start == -1:
		return ""

	# 从起始 { 开始计数，找到匹配的 }
	var depth: int = 0
	for i in range(start, text.length()):
		var ch: String = text[i]
		if ch == "{":
			depth += 1
		elif ch == "}":
			depth -= 1
			if depth == 0:
				return text.substr(start, i - start + 1)

	return ""


# ============================================================
# 日志辅助
# ============================================================

func _log_info(msg: String) -> void:
	print("[MaNA] %s %s" % [agent_name, msg])


func _log_warn(msg: String) -> void:
	push_warning("[MaNA] %s %s" % [agent_name, msg])


func _log_error(msg: String) -> void:
	push_error("[MaNA] %s %s" % [agent_name, msg])
