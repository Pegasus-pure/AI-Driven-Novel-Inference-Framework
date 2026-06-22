class_name MananaConfig
extends RefCounted

## MaNA 配置加载器 v2
## 读取 res://manana_config.cfg（INI 格式），提供三 tier Provider / 重试 / Oracle 配置。
## 首次运行或检测到 v1 配置时自动迁移到 v2 格式。

const CONFIG_PATH: String = "res://manana_config.cfg"
const BACKUP_DIR: String = "res://config_backup"
const BACKUP_PATH: String = "res://config_backup/old_manana_config.cfg"

# ============================================================
# 内部缓存
# ============================================================

var _config_file: ConfigFile = null
var _loaded: bool = false

# ============================================================
# 生命周期
# ============================================================

## 加载配置文件。如果文件不存在则自动创建 v2 默认配置。
func load_config() -> void:
	_config_file = ConfigFile.new()

	if _config_file.load(CONFIG_PATH) != OK:
		push_warning("MananaConfig: config not found, creating v2 default at %s" % CONFIG_PATH)
		_create_default_v2_config()
		_loaded = true
		return

	_loaded = true


## 持久化当前配置到文件
func save() -> void:
	if not _loaded or _config_file == null:
		push_warning("MananaConfig: save() called before load, skipping")
		return
	var err: int = _config_file.save(CONFIG_PATH)
	if err != OK:
		push_error("MananaConfig: Failed to save config: %s" % error_string(err))


# ============================================================
# Tier 配置读写
# ============================================================

## 获取指定 tier 的完整 Provider 配置
## @param   tier: "strong" | "medium" | "light"
## @returns Dictionary {
##     "type":        String,   # "ollama"|"deepseek"|"openai"
##     "endpoint":    String,   # 完整 URL（含协议+端口+路径）
##     "api_key":     String,   # API 密钥（可为空）
##     "model":       String,   # 模型名
##     "temperature": float,    # 0.0-2.0
##     "max_tokens":  int,      # 最大 token 数
##     "timeout":     int,      # 超时秒数
## }
func get_tier_config(tier: String) -> Dictionary:
	_ensure_loaded()
	var section: String = "provider_" + tier
	return {
		"type": _config_file.get_value(section, "type", "ollama") as String,
		"endpoint": _config_file.get_value(section, "endpoint", "") as String,
		"api_key": _config_file.get_value(section, "api_key", "") as String,
		"model": _config_file.get_value(section, "model", "") as String,
		"temperature": _config_file.get_value(section, "temperature", 0.7) as float,
		"max_tokens": _config_file.get_value(section, "max_tokens", 2048) as int,
		"timeout": _config_file.get_value(section, "timeout", 120) as int,
	}


## 设置指定 tier 的 Provider 配置并持久化
## @param tier:   "strong" | "medium" | "light"
## @param config: Dictionary with keys {type, endpoint, api_key, model, temperature, max_tokens, timeout}
func set_tier_config(tier: String, config: Dictionary) -> void:
	_ensure_loaded()
	var set_section: String = "provider_" + tier
	_config_file.set_value(set_section, "type", config.get("type", "ollama"))
	_config_file.set_value(set_section, "endpoint", config.get("endpoint", ""))
	_config_file.set_value(set_section, "api_key", config.get("api_key", ""))
	_config_file.set_value(set_section, "model", config.get("model", ""))
	_config_file.set_value(set_section, "temperature", config.get("temperature", 0.7))
	_config_file.set_value(set_section, "max_tokens", config.get("max_tokens", 2048))
	_config_file.set_value(set_section, "timeout", config.get("timeout", 120))
	save()


# ============================================================
# Retry / Oracle 配置读写
# ============================================================

## 获取重试配置
## @returns {max_retries: int, base_delay: float}
func get_retry_config() -> Dictionary:
	_ensure_loaded()
	return {
		"max_retries": _config_file.get_value("retry", "max_retries", 3) as int,
		"base_delay": _config_file.get_value("retry", "base_delay", 1.0) as float,
	}


## 设置重试配置并持久化
func set_retry_config(max_retries: int, base_delay: float) -> void:
	_ensure_loaded()
	_config_file.set_value("retry", "max_retries", max_retries)
	_config_file.set_value("retry", "base_delay", base_delay)
	save()


## 获取 Oracle 检查间隔（节拍数）
## @returns int — 默认 5
func get_oracle_interval() -> int:
	_ensure_loaded()
	return _config_file.get_value("oracle", "trigger_interval", 5) as int


## 设置 Oracle 检查间隔并持久化
func set_oracle_interval(interval: int) -> void:
	_ensure_loaded()
	_config_file.set_value("oracle", "trigger_interval", interval)
	save()


# ============================================================
# 迁移逻辑 (v1 → v2)
# ============================================================

## 确保配置已加载，并检查是否需要迁移
func _ensure_loaded() -> void:
	if not _loaded:
		load_config()
		return

	# 检查 config_version：缺失或 < 2 则触发迁移
	var version: int = 1
	if _config_file.has_section("global"):
		version = _config_file.get_value("global", "config_version", 1) as int

	if version < 2:
		_migrate_v1_to_v2()


## 执行 v1 → v2 迁移：备份旧配置 → 生成 v2 默认配置 → 广播迁移事件
func _migrate_v1_to_v2() -> void:
	var old_version: int = 1
	if _config_file.has_section("global"):
		old_version = _config_file.get_value("global", "config_version", 1) as int

	print("MananaConfig: Detected v%d config, migrating to v2..." % old_version)

	_backup_old_config()
	_create_default_v2_config()
	_loaded = true

	# 通过 EventBus 广播迁移事件
	if EventBus and EventBus.has_signal("config_migrated"):
		EventBus.config_migrated.emit(old_version, 2)

	print("MananaConfig: Migration to v2 complete. Old config backed up to %s" % BACKUP_PATH)


## 备份旧配置文件到 config_backup/ 目录
func _backup_old_config() -> void:
	var dir: DirAccess = DirAccess.open("res://")
	if dir == null:
		push_error("MananaConfig: Cannot access res:// for backup")
		return

	# 确保 config_backup 目录存在
	var backup_err: Error = dir.make_dir("config_backup")
	if backup_err != OK and backup_err != ERR_ALREADY_EXISTS:
		push_warning("MananaConfig: Could not create backup directory: %s" % error_string(backup_err))

	# 复制旧配置文件
	backup_err = dir.copy("manana_config.cfg", "config_backup/old_manana_config.cfg")
	if backup_err != OK:
		push_warning("MananaConfig: Backup copy failed: %s" % error_string(backup_err))
	else:
		print("MananaConfig: Old config backed up to %s" % BACKUP_PATH)


## 创建 v2 默认配置（清空后写入三 provider + retry + oracle 默认值）
func _create_default_v2_config() -> void:
	_config_file = ConfigFile.new()

	# [global]
	_config_file.set_value("global", "config_version", 2)

	# [provider_strong] — 最强模型，低 temperature，高 token 上限
	_config_file.set_value("provider_strong", "type", "ollama")
	_config_file.set_value("provider_strong", "endpoint", "http://localhost:11434/api/chat")
	_config_file.set_value("provider_strong", "api_key", "")
	_config_file.set_value("provider_strong", "model", "qwen3.5:9b")
	_config_file.set_value("provider_strong", "temperature", 0.5)
	_config_file.set_value("provider_strong", "max_tokens", 4096)
	_config_file.set_value("provider_strong", "timeout", 120)

	# [provider_medium] — 中等模型，默认 temperature，中等 token 上限
	_config_file.set_value("provider_medium", "type", "ollama")
	_config_file.set_value("provider_medium", "endpoint", "http://localhost:11434/api/chat")
	_config_file.set_value("provider_medium", "api_key", "")
	_config_file.set_value("provider_medium", "model", "qwen3.5:9b")
	_config_file.set_value("provider_medium", "temperature", 0.7)
	_config_file.set_value("provider_medium", "max_tokens", 2048)
	_config_file.set_value("provider_medium", "timeout", 120)

	# [provider_light] — 轻量模型，高 temperature（创意性），低 token 上限
	_config_file.set_value("provider_light", "type", "ollama")
	_config_file.set_value("provider_light", "endpoint", "http://localhost:11434/api/chat")
	_config_file.set_value("provider_light", "api_key", "")
	_config_file.set_value("provider_light", "model", "qwen3.5:9b")
	_config_file.set_value("provider_light", "temperature", 0.8)
	_config_file.set_value("provider_light", "max_tokens", 512)
	_config_file.set_value("provider_light", "timeout", 60)

	# [retry]
	_config_file.set_value("retry", "max_retries", 3)
	_config_file.set_value("retry", "base_delay", 1.0)

	# [oracle]
	_config_file.set_value("oracle", "trigger_interval", 5)

	# 直接写入磁盘（不走 save() 以避免 _ensure_loaded 递归）
	var err: int = _config_file.save(CONFIG_PATH)
	if err != OK:
		push_error("MananaConfig: Failed to create default config: %s" % error_string(err))
	_loaded = true
	print("MananaConfig: Default v2 config created at %s" % CONFIG_PATH)


# ============================================================
# v4 开关方法
# ============================================================

## 检查 MaNA v4 是否启用
func is_v4_enabled() -> bool:
	return get_bool("v4", "enabled", false)


## 检查指定 feature 是否启用（需 v4 整体开启 && feature 自身开启）
## @param feature: String — section name like "refinement", "best_of_3", etc.
func is_feature_enabled(feature: String) -> bool:
	if not is_v4_enabled():
		return false
	return get_bool(feature, "enabled", false)


## 获取 Refinement 限制配置
## @returns {max_warning_refine: int, max_fail_rewrite: int}
func get_refinement_limits() -> Dictionary:
	return {
		"max_warning_refine": get_int("refinement", "max_warning_refine", 1),
		"max_fail_rewrite": get_int("refinement", "max_fail_rewrite", 2),
	}


## 获取 Best-of-3 配置
## @returns {sample_count: int, scorer_min_total: int}
func get_best_of_3_config() -> Dictionary:
	return {
		"sample_count": get_int("best_of_3", "sample_count", 3),
		"scorer_min_total": get_int("best_of_3", "scorer_min_total", 8),
	}


## 获取 Dynamic Tier 复杂度阈值
## @returns {simple: float, complex: float}
func get_complexity_thresholds() -> Dictionary:
	return {
		"simple": get_float("dynamic_tier", "complexity_threshold_simple", 0.3),
		"complex": get_float("dynamic_tier", "complexity_threshold_complex", 0.5),
	}


## 根据复杂度分数获取 Tier 覆写建议
## @param complexity: float — 0.0~1.0 复杂度分数
## @returns Dictionary — 为空表示不覆写；否则包含 director/composer/auditor/motivation 的 tier 覆写
func get_tier_overrides(complexity: float) -> Dictionary:
	var simple_thresh: float = get_float("dynamic_tier", "complexity_threshold_simple", 0.3)
	var complex_thresh: float = get_float("dynamic_tier", "complexity_threshold_complex", 0.5)
	if complexity < simple_thresh:
		return {"director": "medium", "composer": "medium", "auditor": "light", "motivation": "light"}
	elif complexity > complex_thresh:
		return {"director": "strong", "composer": "strong", "auditor": "strong", "motivation": "strong"}
	return {}


## 获取 Semantic Selection 配置
## @returns {max_canon_tokens: int}
func get_semantic_selection_config() -> Dictionary:
	return {
		"max_canon_tokens": get_int("semantic_selection", "max_canon_tokens", 1200),
	}


## 获取 Memory（向量记忆）配置
## @returns {enable_vector_memory: bool, embed_model: String, vector_top_k: int, max_vector_entries: int}
func get_memory_config() -> Dictionary:
	return {
		"enable_vector_memory": get_bool("memory", "enable_vector_memory", false),
		"embed_model": get_string("memory", "embed_model", "nomic-embed-text"),
		"vector_top_k": get_int("memory", "vector_top_k", 3),
		"max_vector_entries": get_int("memory", "max_vector_entries", 500),
	}


## 获取性能降级配置
## @returns {auto_degrade_enabled: bool, sample_count_degrade_1: int, sample_count_degrade_2: int, multi_view_degrade_1: bool}
func get_degrade_config() -> Dictionary:
	return {
		"auto_degrade_enabled": get_bool("performance", "auto_degrade_enabled", true),
		"sample_count_degrade_1": get_int("performance", "sample_count_degrade_1", 2),
		"sample_count_degrade_2": get_int("performance", "sample_count_degrade_2", 1),
		"multi_view_degrade_1": get_bool("performance", "multi_view_degrade_1", false),
	}


# ============================================================
# 安全类型读取（ConfigFile 缺失 section/key 时不崩溃）
# ============================================================

## 安全读取 bool 值，缺失时返回 default
func get_bool(section: String, key: String, default: bool = false) -> bool:
	if not _config_file.has_section(section):
		return default
	var value: String = str(_config_file.get_value(section, key, str(default)))
	return value == "true" or value == "1"


## 安全读取 float 值，缺失时返回 default
func get_float(section: String, key: String, default: float = 0.0) -> float:
	if not _config_file.has_section(section):
		return default
	return _config_file.get_value(section, key, default) as float


## 安全读取 int 值，缺失时返回 default
func get_int(section: String, key: String, default: int = 0) -> int:
	if not _config_file.has_section(section):
		return default
	return _config_file.get_value(section, key, default) as int


## 安全读取 String 值，缺失时返回 default
func get_string(section: String, key: String, default: String = "") -> String:
	if not _config_file.has_section(section):
		return default
	return str(_config_file.get_value(section, key, default))
