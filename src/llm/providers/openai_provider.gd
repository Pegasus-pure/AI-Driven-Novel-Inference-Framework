class_name OpenAIProvider
extends BaseLLMProvider

## OpenAI Provider — 标准 OpenAI API 格式
## base_url: https://api.openai.com/v1/chat/completions
## Header: Authorization: Bearer {api_key}
## 请求/响应格式与 DeepSeekProvider 完全相同，仅 endpoint 不同。

# ============================================================
# 公开方法
# ============================================================

## 返回 Provider 名称标识
func get_provider_name() -> String:
	return "openai"


## 配置 OpenAI Provider
## [param config] 包含: endpoint, api_key, model_strong, model_medium, model_light, timeout, max_retries
func configure(config: Dictionary) -> void:
	super.configure(config)
	if not _config.has("endpoint") or _config["endpoint"] == "":
		_config["endpoint"] = "https://api.openai.com/v1/chat/completions"
	if not _config.has("timeout"):
		_config["timeout"] = 60.0
	if not _config.has("max_retries"):
		_config["max_retries"] = 3


## 异步发起聊天请求
## OpenAI 格式: {"model": "...", "messages": [...], "temperature": 0.7, "max_tokens": 1024}
func chat_async(system_prompt: String, user_message: String, options: Dictionary = {}) -> Dictionary:
	if not _is_http_ready():
		return {"ok": false, "error": "HTTP node not attached", "content": "", "raw": "", "tokens": 0}

	var opts: Dictionary = _normalize_options(options)
	var body_dict: Dictionary = _build_request_body(system_prompt, user_message, opts)
	var body_json: String = JSON.stringify(body_dict)

	var endpoint: String = _config.get("endpoint", "https://api.openai.com/v1/chat/completions")
	var max_retries: int = _config.get("max_retries", 3)

	var last_result: Dictionary = {}
	for attempt in range(max_retries + 1):
		var result: Dictionary = await _do_http_request(endpoint, body_json)
		if result.get("ok", false):
			return result
		last_result = result
		if attempt < max_retries:
			push_warning("OpenAI retry %d/%d: %s" % [attempt + 1, max_retries, result.get("error", "")])

	return last_result


## 获取模型名称
func get_model_name(_tier: String = "") -> String:
	return _config.get("model", "")


# ============================================================
# 内部方法
# ============================================================

## 构建请求头（含 Bearer Token）
func _build_headers() -> PackedStringArray:
	var headers: PackedStringArray = PackedStringArray(["Content-Type: application/json"])
	var api_key: String = _config.get("api_key", "") as String
	if api_key != "":
		headers.append("Authorization: Bearer " + api_key)
	return headers


## 构建 OpenAI 请求体
func _build_request_body(system_prompt: String, user_message: String, options: Dictionary) -> Dictionary:
	var messages: Array = []
	if system_prompt != "":
		messages.append({"role": "system", "content": system_prompt})
	messages.append({"role": "user", "content": user_message})

	# JSON mode: 追加 system 提示
	if options.get("json_mode", false):
		messages.append({"role": "system", "content": "You must respond with valid JSON only."})

	var body: Dictionary = {
		"model": options.get("model", _config.get("model_strong", "gpt-4o")),
		"messages": messages,
		"temperature": options.get("temperature", 0.7),
		"max_tokens": options.get("max_tokens", 1024),
		"stream": false,
	}

	return body


## 解析 OpenAI 响应
func _parse_response(body_text: String) -> Dictionary:
	var json: JSON = JSON.new()
	var parse_err: int = json.parse(body_text)
	if parse_err != OK:
		return {"ok": false, "error": "JSON parse error: %s" % json.get_error_message(), "content": "", "raw": body_text, "tokens": 0}

	var data: Variant = json.get_data()
	if not (data is Dictionary):
		return {"ok": false, "error": "Response is not a Dictionary", "content": "", "raw": body_text, "tokens": 0}

	var resp: Dictionary = data as Dictionary

	if resp.has("error"):
		var err_obj: Dictionary = resp.get("error", {}) as Dictionary
		var err_msg: String = str(err_obj.get("message", "Unknown error"))
		return {"ok": false, "error": err_msg, "content": "", "raw": body_text, "tokens": 0}

	var choices: Array = resp.get("choices", []) as Array
	if choices.size() == 0:
		return {"ok": false, "error": "No choices in response", "content": "", "raw": body_text, "tokens": 0}

	var choice: Dictionary = choices[0] as Dictionary
	var message: Dictionary = choice.get("message", {}) as Dictionary
	var content: String = message.get("content", "") as String

	var tokens: int = 0
	if resp.has("usage"):
		var usage: Dictionary = resp.get("usage", {}) as Dictionary
		tokens = usage.get("total_tokens", 0) as int
	else:
		tokens = content.length() / 4

	return {"ok": true, "content": content, "raw": body_text, "tokens": tokens}
