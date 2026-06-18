class_name MananaLogger
extends RefCounted

## MaNA 统一日志 + Agent Trace 系统。
## 全静态方法，不持有实例状态。为 Pipeline 和所有 Agent 提供统一的日志接口。
## 支持按 beat_id 组织 agent trace，方便调试和审计。

# ============================================================
# 静态状态
# ============================================================

static var _beat_id: String = ""

## agent_traces[beat_id][agent_name] = {"request": "", "response": "", "tokens": 0, "ok": false}
static var _traces: Dictionary = {}

# ============================================================
# Beat 生命周期
# ============================================================

## 设置当前追踪的 Beat ID，初始化该 beat 的 trace 容器。
static func set_current_beat(beat_id: String) -> void:
	_beat_id = beat_id
	_traces[beat_id] = {}


## 获取当前 Beat ID。
static func get_current_beat() -> String:
	return _beat_id


## 清理指定 beat 的 trace 数据（节省内存）。
static func clear_beat(beat_id: String) -> void:
	if _traces.has(beat_id):
		_traces.erase(beat_id)


# ============================================================
# Agent 请求/响应日志
# ============================================================

## 记录 Agent 请求。
## [param agent_name] Agent 名称
## [param request] 完整 user prompt 文本
static func log_agent_request(agent_name: String, request: String) -> void:
	print("[MaNA] [%s] %s → request (%d chars)" % [_beat_id, agent_name, request.length()])

	if not _traces.has(_beat_id):
		return

	var beat_traces: Dictionary = _traces[_beat_id] as Dictionary
	beat_traces[agent_name] = {
		"request": request,
		"response": "",
		"tokens": 0,
		"ok": false,
	}


## 记录 Agent 响应。
## [param agent_name] Agent 名称
## [param response] LLM 返回的 content 文本
## [param tokens] 消耗的 token 数量
## [param success] 调用是否成功
static func log_agent_response(agent_name: String, response: String, tokens: int, success: bool) -> void:
	var status_label: String = "←" if success else "✗"
	print("[MaNA] [%s] %s %s response (tokens: %d)" % [_beat_id, agent_name, status_label, tokens])

	if not _traces.has(_beat_id):
		return

	var resp_beat_traces: Dictionary = _traces[_beat_id] as Dictionary
	if not resp_beat_traces.has(agent_name):
		resp_beat_traces[agent_name] = {"request": "", "response": "", "tokens": 0, "ok": false}

	var trace: Dictionary = resp_beat_traces[agent_name] as Dictionary
	trace["response"] = response
	trace["tokens"] = tokens
	trace["ok"] = success


# ============================================================
# 层级日志
# ============================================================

## 记录 Layer 级事件（如 "Layer 1: Director 启动"）。
static func log_layer(layer: String, message: String) -> void:
	print("[MaNA] [%s] Layer %s: %s" % [_beat_id, layer, message])


# ============================================================
# 警告 / 错误日志
# ============================================================

## 记录 Agent 警告。
static func log_warning(agent_name: String, message: String) -> void:
	push_warning("[MaNA] [%s] %s: %s" % [_beat_id, agent_name, message])


## 记录 Agent 错误。
static func log_error(agent_name: String, message: String) -> void:
	push_error("[MaNA] [%s] %s: %s" % [_beat_id, agent_name, message])


# ============================================================
# Trace 持久化 (T05 完善)
# ============================================================

## 将指定 beat 的 agent traces 保存到磁盘。
## 保存路径: debug/agent_traces/beat_{beat_id}/
## — request.json 和 response.json 分别存放请求和响应文本
## [param beat_id] 要保存的 beat ID
static func save_traces(beat_id: String) -> void:
	if not _traces.has(beat_id):
		return

	var user_dir: String = OS.get_user_data_dir()
	var base_dir: String = user_dir.path_join("debug/agent_traces/beat_%s" % beat_id)

	# 确保目录存在
	if not DirAccess.dir_exists_absolute(base_dir):
		DirAccess.make_dir_recursive_absolute(base_dir)

	var save_beat_traces: Dictionary = _traces[beat_id] as Dictionary
	for agent_name in save_beat_traces:
		var save_trace: Dictionary = save_beat_traces[agent_name] as Dictionary

		# 保存 request
		var req_fname: String = "%s/%s_request.json" % [base_dir, agent_name]
		var req_file: FileAccess = FileAccess.open(req_fname, FileAccess.WRITE)
		if req_file:
			req_file.store_string(str(save_trace.get("request", "")))
			req_file.close()

		# 保存 response
		var resp_fname: String = "%s/%s_response.json" % [base_dir, agent_name]
		var resp_file: FileAccess = FileAccess.open(resp_fname, FileAccess.WRITE)
		if resp_file:
			resp_file.store_string(str(save_trace.get("response", "")))
			resp_file.close()

		# 保存 meta (token 数量、是否成功)
		var meta_fname: String = "%s/%s_meta.json" % [base_dir, agent_name]
		var meta_file: FileAccess = FileAccess.open(meta_fname, FileAccess.WRITE)
		if meta_file:
			var meta: String = JSON.stringify({
				"agent": agent_name,
				"beat_id": beat_id,
				"tokens": save_trace.get("tokens", 0),
				"ok": save_trace.get("ok", false),
			})
			meta_file.store_string(meta)
			meta_file.close()

	print("[MaNA] Traces saved for beat '%s' (%d agents)" % [beat_id, save_beat_traces.size()])


# ============================================================
# 查询方法
# ============================================================

## 获取指定 beat 的所有 agent trace。
static func get_traces(beat_id: String) -> Dictionary:
	return _traces.get(beat_id, {}) as Dictionary


## 获取所有已记录的 beat ID 列表。
static func get_all_beat_ids() -> Array:
	return _traces.keys()


## 计算全部 trace 的总 token 消耗。
static func get_total_tokens() -> int:
	var total: int = 0
	for beat_id in _traces:
		var total_beat_traces: Dictionary = _traces[beat_id] as Dictionary
		for agent_name in total_beat_traces:
			var total_trace: Dictionary = total_beat_traces[agent_name] as Dictionary
			total += total_trace.get("tokens", 0) as int
	return total


# ============================================================
# v4: 节拍性能日志
# ============================================================

## 单个 Beat 的详细性能日志记录
class MananaBeatLog:
	var beat_id: String = ""
	var start_time_ms: int = 0
	var end_time_ms: int = 0
	var agent_timings: Dictionary = {}  # {agent_name: {start_ms, end_ms, duration_ms}}
	var refinement_triggered: bool = false
	var refinement_verdict: String = ""  # "" | "WARNING" | "FAIL"
	var best_of_3_rejected_count: int = 0
	var complexity_score: float = 0.0
	var degrade_level: int = 0

	func duration_ms() -> int:
		return end_time_ms - start_time_ms


static var _beat_logs: Array = []
static var _session_start_ms: int = 0


## 初始化 session 级别的统计
static func init_session() -> void:
	_session_start_ms = Time.get_ticks_msec()
	_beat_logs.clear()


## 为当前 beat 创建新的性能日志并返回
## @param beat_id: String — 当前 beat 标识
## @returns MananaBeatLog
static func create_beat_log(beat_id: String) -> MananaBeatLog:
	var log: MananaBeatLog = MananaBeatLog.new()
	log.beat_id = beat_id
	log.start_time_ms = Time.get_ticks_msec()
	_beat_logs.append(log)
	return log


## 记录单个 Agent 的耗时
## @param beat_log: MananaBeatLog — 所属 beat 的性能日志
## @param agent_name: String — Agent 名称
## @param start_ms: int — Agent 调用开始时间戳
## @param end_ms: int — Agent 调用结束时间戳
static func record_agent_timing(beat_log: MananaBeatLog, agent_name: String, start_ms: int, end_ms: int) -> void:
	beat_log.agent_timings[agent_name] = {
		"start_ms": start_ms,
		"end_ms": end_ms,
		"duration_ms": end_ms - start_ms,
	}


## 获取整个 session 的聚合性能统计
## @returns Dictionary {
##     total_beats, total_duration_ms, avg_beat_duration_ms,
##     refinement_triggered, best_of_3_rejected, avg_complexity,
##     avg_agent_timing_ms, session_duration_ms
## }
static func get_session_stats() -> Dictionary:
	var total_beats: int = _beat_logs.size()
	if total_beats == 0:
		return {"total_beats": 0}

	var total_duration: int = 0
	var refinement_count: int = 0
	var best_of_3_rejected: int = 0
	var total_complexity: float = 0.0
	var per_agent_total: Dictionary = {}
	var per_agent_count: Dictionary = {}

	for log_ in _beat_logs:
		var log: MananaBeatLog = log_ as MananaBeatLog
		total_duration += log.duration_ms()
		if log.refinement_triggered:
			refinement_count += 1
		best_of_3_rejected += log.best_of_3_rejected_count
		total_complexity += log.complexity_score

		for agent_name in log.agent_timings:
			var timing: Dictionary = log.agent_timings[agent_name] as Dictionary
			var dur: int = timing["duration_ms"] as int
			if not per_agent_total.has(agent_name):
				per_agent_total[agent_name] = 0
				per_agent_count[agent_name] = 0
			per_agent_total[agent_name] = per_agent_total[agent_name] as int + dur
			per_agent_count[agent_name] = per_agent_count[agent_name] as int + 1

	var avg_per_agent: Dictionary = {}
	for agent_name in per_agent_total:
		var total_for: int = per_agent_total[agent_name] as int
		var count_for: int = per_agent_count[agent_name] as int
		avg_per_agent[agent_name] = total_for / max(1, count_for)

	return {
		"total_beats": total_beats,
		"total_duration_ms": total_duration,
		"avg_beat_duration_ms": total_duration / max(1, total_beats),
		"refinement_triggered": refinement_count,
		"best_of_3_rejected": best_of_3_rejected,
		"avg_complexity": total_complexity / max(1.0, float(total_beats)),
		"avg_agent_timing_ms": avg_per_agent,
		"session_duration_ms": Time.get_ticks_msec() - _session_start_ms,
	}
