class_name VectorMemory
extends RefCounted

## 向量记忆系统 — 语义存储与检索
## 基于 Ollama /api/embed + cosine similarity

const MAX_VECTOR_ENTRIES: int = 500

var _cache: Dictionary = {}
var _store: Array = []

## 对文本做向量化（带 MD5 缓存）
func embed(provider: BaseLLMProvider, text: String) -> PackedFloat64Array:
	var hash_key: String = text.md5_text()
	if _cache.has(hash_key):
		return _cache[hash_key] as PackedFloat64Array

	var vector: PackedFloat64Array = await provider.embed(text)
	if vector.size() == 0:
		return PackedFloat64Array()

	_cache[hash_key] = vector
	return vector

## 存储一条记忆
func store(key: String, text: String, embedding: PackedFloat64Array, metadata: Dictionary = {}) -> void:
	_store.append({
		"key": key,
		"text": text,
		"embedding": embedding,
		"metadata": metadata
	})

	while _store.size() > MAX_VECTOR_ENTRIES:
		_store.pop_front()

## 语义检索 — 返回 top_k 条最相似记忆
func search(query_embedding: PackedFloat64Array, top_k: int = 3) -> Array:
	if query_embedding.size() == 0 or _store.size() == 0:
		return []

	var scored: Array = []
	for entry_ in _store:
		var entry: Dictionary = entry_ as Dictionary
		var entry_embed: PackedFloat64Array = entry["embedding"] as PackedFloat64Array
		var score: float = _cosine_similarity(query_embedding, entry_embed)
		scored.append({"entry": entry, "score": score})

	scored.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return (a["score"] as float) > (b["score"] as float)
	)

	var result: Array = []
	var limit: int = min(top_k, scored.size())
	for i in range(limit):
		var item: Dictionary = scored[i] as Dictionary
		result.append(item["entry"] as Dictionary)
	return result

## 查询记忆数量
func size() -> int:
	return _store.size()

## 清空所有记忆
func clear() -> void:
	_store.clear()
	_cache.clear()

## 余弦相似度 — 向量已 L2 归一化，简化为点积
static func _cosine_similarity(a: PackedFloat64Array, b: PackedFloat64Array) -> float:
	var dot: float = 0.0
	var size: int = min(a.size(), b.size())
	for i in range(size):
		dot += a[i] * b[i]
	return dot
