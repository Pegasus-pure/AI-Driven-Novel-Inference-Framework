class_name OllamaProvider
extends BaseLLMProvider

## Ollama Provider — 使用原生 /api/chat 端点
## 无需 API Key，适合本地部署

# ============================================================
# 公开方法
# ============================================================

## 返回 Provider 名称标识
func get_provider_name() -> String:
	return "ollama"


## 配置 Ollama Provider
## [param config] 包含: endpoint, model_strong, model_medium, model_light, timeout, max_retries
func configure(config: Dictionary) -> void:
	super.configure(config)
	# Ollama 不需要 api_key，但确保默认 endpoint
	if not _config.has("endpoint") or _config["endpoint"] == "":
		_config["endpoint"] = "http://localhost:11434/api/chat"
	if not _config.has("timeout"):
		_config["timeout"] = 120.0
	if not _config.has("max_retries"):
		_config["max_retries"] = 3


## 异步发起聊天请求
## Ollama 格式: {"model": "...", "messages": [...], "stream": false}
## 响应格式: {"message": {"role": "assistant", "content": "..."}}
func chat_async(system_prompt: String, user_message: String, options: Dictionary = {}) -> Dictionary:
	if not _is_http_ready():
		return {"ok": false, "error": "HTTP node not attached", "content": "", "raw": "", "tokens": 0}

	var opts: Dictionary = _normalize_options(options)
	var body_dict: Dictionary = _build_request_body(system_prompt, user_message, opts)
	var body_json: String = JSON.stringify(body_dict)

	var endpoint: String = _config.get("endpoint", "http://localhost:11434/api/chat")
	var max_retries: int = _config.get("max_retries", 3)

	var last_result: Dictionary = {}
	for attempt in range(max_retries + 1):
		var result: Dictionary = await _do_http_request(endpoint, body_json)
		if result.get("ok", false):
			return result
		last_result = result
		if attempt < max_retries:
			push_warning("Ollama retry %d/%d: %s" % [attempt + 1, max_retries, result.get("error", "")])

	return last_result


## 获取模型名称
func get_model_name(_tier: String = "") -> String:
	return _config.get("model", "")


# ============================================================
# 内部方法
# ============================================================

## 构建 Ollama 格式的请求体
func _build_request_body(system_prompt: String, user_message: String, options: Dictionary) -> Dictionary:
	var messages: Array = []
	if system_prompt != "":
		messages.append({"role": "system", "content": system_prompt})
	messages.append({"role": "user", "content": user_message})

	var body: Dictionary = {
		"model": options.get("model", _config.get("model", "")),
		"messages": messages,
		"stream": false,
		"think": false     # 关闭 qwen3 思考模式（Ollama 原生 API）
	}

	# Ollama 也支持 temperature / max_tokens 等 OpenAI 兼容参数
	if options.has("temperature"):
		body["temperature"] = options["temperature"]
	if options.has("max_tokens"):
		body["max_tokens"] = options["max_tokens"]

	# JSON mode: 追加 system 提示
	if options.get("json_mode", false):
		messages.append({"role": "system", "content": "You must respond with valid JSON only."})

	return body


## 解析 Ollama 响应
## 格式: {"model": "...", "message": {"role": "assistant", "content": "..."}, "done": true, "total_duration": ...}
func _parse_response(body_text: String) -> Dictionary:
	var json: JSON = JSON.new()
	var parse_err: int = json.parse(body_text)
	if parse_err != OK:
		return {"ok": false, "error": "JSON parse error: %s" % json.get_error_message(), "content": "", "raw": body_text, "tokens": 0}

	var data: Variant = json.get_data()
	if not (data is Dictionary):
		return {"ok": false, "error": "Response is not a Dictionary", "content": "", "raw": body_text, "tokens": 0}

	var resp: Dictionary = data as Dictionary

	# 检查错误
	if resp.has("error"):
		var err_str: String = str(resp["error"])
		return {"ok": false, "error": err_str, "content": "", "raw": body_text, "tokens": 0}

	# 提取 message.content
	var message: Dictionary = resp.get("message", {}) as Dictionary
	var content: String = message.get("content", "") as String

	# 估算 token 数（Ollama 可能返回 eval_count / prompt_eval_count）
	var tokens: int = 0
	if resp.has("eval_count"):
		tokens = resp["eval_count"] as int
	else:
		tokens = content.length() / 4  # 粗略估算

	return {"ok": true, "content": content, "raw": body_text, "tokens": tokens}


# === v4: Embedding ===

const EMBED_ENDPOINT: String = "/api/embed"
var _embed_model: String = "qwen3-embedding:0.6b"

## 文本向量化 — 调用 Ollama /api/embed
func embed(text: String) -> PackedFloat64Array:
	if not _is_http_ready():
		push_error("OllamaProvider.embed: HTTP node not attached")
		return PackedFloat64Array()

	var model: String = _config.get("embed_model", _embed_model) as String

	var body_dict: Dictionary = {
		"model": model,
		"input": text
	}
	var body_json: String = JSON.stringify(body_dict)

	var base_endpoint: String = str(_config.get("endpoint", "http://localhost:11434/api/chat"))
	var embed_url: String = base_endpoint.replace("/api/chat", EMBED_ENDPOINT)

	var result: Dictionary = await _do_http_request(embed_url, body_json)
	if not result.get("ok", false):
		push_error("OllamaProvider.embed: HTTP failed: " + str(result.get("error", "")))
		return PackedFloat64Array()

	return _parse_embed_response(str(result.get("raw", "")))

## 解析 Ollama /api/embed 响应
## 响应格式: {"model":"...","embeddings":[[0.1,-0.2,...]],"total_duration":...,"prompt_eval_count":...}
## 向量已 L2 归一化
func _parse_embed_response(raw: String) -> PackedFloat64Array:
	var json: JSON = JSON.new()
	var err: int = json.parse(raw)
	if err != OK:
		push_error("OllamaProvider: embed JSON parse failed: " + json.get_error_message())
		return PackedFloat64Array()

	var data: Variant = json.get_data()
	if not (data is Dictionary):
		return PackedFloat64Array()

	var resp: Dictionary = data as Dictionary
	var embeddings: Array = resp.get("embeddings", []) as Array
	if embeddings.size() == 0:
		return PackedFloat64Array()

	var first: Array = embeddings[0] as Array
	var result_vec: PackedFloat64Array = PackedFloat64Array()
	result_vec.resize(first.size())
	for i in first.size():
		result_vec[i] = first[i] as float
	return result_vec
