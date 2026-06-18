class_name BaseLLMProvider
extends RefCounted

## MaNA 架构 — LLM Provider 抽象基类
## 所有 Provider 必须继承此类并重写 chat_async / get_model_name 等方法。
## RefCounted 不能直接 add_child，HTTPRequest 节点通过 _attach_http_node 接收。
##
## 多 Provider 架构 (v2):
##   每个 tier (strong/medium/light) 拥有独立的 Provider 实例，
##   Provider 的 _config 仅包含该 tier 的配置（model/temperature 等）。

# ============================================================
# 内部状态
# ============================================================

## HTTP 请求节点，由子类通过 _attach_http_node 创建
var _http_request: HTTPRequest = null

## 当前配置字典（由 configure 填充，包含单 tier 配置）
var _config: Dictionary = {}

## 最后一次调用的模型名
var _last_model: String = ""

# ============================================================
# 公开方法 — 子类必须重写
# ============================================================

## 返回 Provider 名称标识（如 "ollama"、"deepseek"、"openai"）
func get_provider_name() -> String:
	return "base"


## 配置 Provider
## [param config] 包含: endpoint, api_key, model, temperature, max_tokens, timeout
func configure(config: Dictionary) -> void:
	_config = config.duplicate()


## 异步发起聊天请求
## [param system_prompt] 系统提示词
## [param user_message] 用户消息
## [param options] 可选参数: {"model": "", "temperature": 0.7, "max_tokens": 1024, "json_mode": false}
## [returns] {"ok": bool, "content": String, "raw": String, "tokens": int, "error": String}
func chat_async(_system_prompt: String, _user_message: String, _options: Dictionary = {}) -> Dictionary:
	return {"ok": false, "error": "NOT_IMPLEMENTED"}


## 获取模型名称
## [param tier] "strong" | "medium" | "light"（多 Provider 架构下参数不再使用，保留以兼容接口）
## [returns] 当前 Provider 实例的模型名
func get_model_name(_tier: String = "") -> String:
	return _config.get("model", "")


## 文本向量化（Embedding）
## 默认实现：不支持 embedding 的 Provider 返回空数组
## [param _text] 待向量化的文本
## [returns] PackedFloat64Array — 768 维向量；不支持时为空
func embed(_text: String) -> PackedFloat64Array:
	push_warning("BaseLLMProvider.embed() not implemented for provider: %s" % get_provider_name())
	return PackedFloat64Array()


## 清理连接，释放 HTTPRequest 节点
func cleanup() -> void:
	if _http_request:
		_http_request.cancel_request()
		if _http_request.is_inside_tree():
			_http_request.queue_free()
		_http_request = null


# ============================================================
# 内部方法
# ============================================================

## 将 HTTPRequest 挂载到指定的父节点上。
## Provider (RefCounted) 不能直接 add_child，需要外部 Node 承载。
## [param parent_node] 承载 HTTPRequest 的父节点（如 Pipeline 实例）
func _attach_http_node(parent_node: Node) -> void:
	if _http_request:
		return  # 已挂载，避免重复
	_http_request = HTTPRequest.new()
	parent_node.add_child(_http_request)


## 检查 HTTPRequest 是否已准备好
func _is_http_ready() -> bool:
	return _http_request != null


## 构建请求体（子类重写）
## [param system_prompt] 系统提示词
## [param user_message] 用户消息
## [param options] 可选参数
## [returns] Dictionary — 请求体
func _build_request_body(_system_prompt: String, _user_message: String, _options: Dictionary) -> Dictionary:
	return {}


## 构建请求头（子类重写）
## [returns] PackedStringArray
func _build_headers() -> PackedStringArray:
	return PackedStringArray(["Content-Type: application/json"])


## 解析响应体（子类重写）
## [param body_text] 原始响应文本
## [returns] {"ok": bool, "content": String, "raw": String, "tokens": int, "error": String}
func _parse_response(body_text: String) -> Dictionary:
	return {"ok": false, "error": "NOT_IMPLEMENTED", "content": "", "raw": body_text, "tokens": 0}


## 执行 HTTP 请求并等待响应（子类可直接调用）
## [param url] 请求 URL
## [param body_json] JSON 字符串请求体
## [returns] {"ok": bool, "content": String, "raw": String, "tokens": int, "error": String}
func _do_http_request(url: String, body_json: String) -> Dictionary:
	if not _is_http_ready():
		return {"ok": false, "error": "HTTP node not attached", "content": "", "raw": "", "tokens": 0}

	var headers: PackedStringArray = _build_headers()
	var timeout: float = _config.get("timeout", 120.0)

	# 设置超时（如果节点已存在）
	if _http_request.get_parent() != null:
		_http_request.timeout = timeout

	var err: int = _http_request.request(url, headers, HTTPClient.METHOD_POST, body_json)
	if err != OK:
		return {"ok": false, "error": "Request failed: %s" % error_string(err), "content": "", "raw": "", "tokens": 0}

	# 等待 HTTP 响应 —— GDScript 的 await 会让出主线程
	var signal_result: Array = await _http_request.request_completed
	var http_result: int = signal_result[0] as int
	var response_code: int = signal_result[1] as int
	var _resp_headers: PackedStringArray = signal_result[2] as PackedStringArray
	var body: PackedByteArray = signal_result[3] as PackedByteArray

	var body_text: String = body.get_string_from_utf8()

	if http_result != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "error": "HTTP error: result=%d, status=%d" % [http_result, response_code], "content": "", "raw": body_text, "tokens": 0}

	if response_code != 200:
		return {"ok": false, "error": "HTTP %d: %s" % [response_code, body_text.left(500)], "content": "", "raw": body_text, "tokens": 0}

	return _parse_response(body_text)


## 提取 options 参数，带默认值
## [param options] 原始 options 字典
## [returns] 规范化后的字典
func _normalize_options(options: Dictionary) -> Dictionary:
	var result: Dictionary = {
		"model": options.get("model", _config.get("model", "")),
		"temperature": options.get("temperature", 0.7),
		"max_tokens": options.get("max_tokens", 1024),
		"json_mode": options.get("json_mode", false),
	}
	return result
