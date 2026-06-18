extends Node

## ProviderRegistry Autoload — 持有三层 LLM Provider 实例
## 由 MananaPipeline 在初始化时注册，其他模块通过 EventBus 获取。
##
## 使用方式:
##   var provider := ProviderRegistry.get_provider("strong")
##   var provider := ProviderRegistry.get_provider()         # 返回 strong（向后兼容）
##   if provider:
##       var result = await provider.chat_async(...)

# ============================================================
# 内部状态
# ============================================================

## 按 tier 存储的 Provider 实例: {"strong": ..., "medium": ..., "light": ...}
var _providers: Dictionary = {}

# ============================================================
# 生命周期
# ============================================================

func _ready() -> void:
	# Provider 由 MananaPipeline 在初始化时通过 register_provider() 设置
	pass


# ============================================================
# 公开方法
# ============================================================

## 获取指定 tier 的 Provider（默认 strong，向后兼容无参调用）
## [param tier] "strong" | "medium" | "light"
## [returns] BaseLLMProvider 或 null
func get_provider(tier: String = "strong") -> BaseLLMProvider:
	return _providers.get(tier, null)


## 按 tier 注册 Provider 实例
## [param tier] "strong" | "medium" | "light"
## [param provider] 已配置好的 BaseLLMProvider 实例
func register_provider(tier: String, provider: BaseLLMProvider) -> void:
	if provider == null:
		push_warning("ProviderRegistry: Attempted to register null provider for tier '%s'" % tier)
		return
	_providers[tier] = provider
	print("ProviderRegistry: Registered '%s' provider for tier '%s'" % [provider.get_provider_name(), tier])


## 检查指定 tier 是否已注册 Provider
## [param tier] "strong" | "medium" | "light"
## [returns] bool
func has_provider(tier: String = "strong") -> bool:
	return _providers.has(tier)


## 移除指定 tier 的 Provider
## [param tier] "strong" | "medium" | "light"
func unregister_provider(tier: String) -> void:
	_providers.erase(tier)


## 清理所有 Provider — 依次调用 cleanup() 后清空
func clear_all() -> void:
	for provider in _providers.values():
		if provider.has_method("cleanup"):
			provider.cleanup()
	_providers.clear()
	print("ProviderRegistry: All providers cleared")


## 获取所有已注册的 tier 列表
## [returns] Array[String]
func get_all_tiers() -> Array:
	return _providers.keys()
