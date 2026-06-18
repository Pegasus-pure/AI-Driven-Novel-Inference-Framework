class_name ProviderFactory
extends RefCounted

## Provider 工厂 — 根据配置类型创建对应的 Provider 实例
## 静态工厂方法，无需实例化

## 根据 provider 类型创建对应的 Provider 实例
## [param provider_type] "ollama" | "deepseek" | "openai"
## [param config] 配置字典，将传递给 provider.configure()
## [returns] BaseLLMProvider 实例，未知类型返回 null
static func create(provider_type: String, config: Dictionary) -> BaseLLMProvider:
	var provider: BaseLLMProvider = null

	match provider_type.to_lower():
		"ollama":
			provider = OllamaProvider.new()
		"deepseek":
			provider = DeepSeekProvider.new()
		"openai":
			provider = OpenAIProvider.new()
		_:
			push_error("ProviderFactory: Unknown provider type '%s'" % provider_type)
			return null

	provider.configure(config)
	return provider


## 获取所有支持的 provider 类型列表
## [returns] Array[String]
static func get_supported_types() -> Array:
	return ["ollama", "deepseek", "openai"]


## 检查 provider_type 是否受支持
## [param provider_type] 类型名
## [returns] bool
static func is_supported(provider_type: String) -> bool:
	return provider_type.to_lower() in ["ollama", "deepseek", "openai"]
