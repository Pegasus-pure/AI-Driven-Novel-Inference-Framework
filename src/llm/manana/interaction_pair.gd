class_name InteractionPair
extends RefCounted

## 交互对数据模型
## 表示 Director 规划的一组角色交互对（2 个角色互动）。

## 交互对唯一 ID
var pair_id: String = ""

## 参与交互的角色 ID 列表（通常为 2 个）
var char_ids: Array[String] = []

## 交互类型: "dialogue" | "action" | "both"
var pair_type: String = "dialogue"


## 从 Dictionary 构建 InteractionPair
static func from_dict(data: Dictionary) -> InteractionPair:
	var pair: InteractionPair = InteractionPair.new()
	pair.pair_id = str(data.get("pair_id", ""))
	var raw_ids: Array = data.get("char_ids", [])
	for elem in raw_ids:
		if elem != null and elem is String:
			pair.char_ids.append(elem as String)
	pair.pair_type = str(data.get("pair_type", "dialogue"))
	return pair


## 获取指定角色的交互对手 char_id。
## [param char_id] 当前角色 ID
## [returns] 对手角色 ID，若不在本 pair 中或仅有一人则返回空字符串
func get_counterpart(char_id: String) -> String:
	for cid in char_ids:
		if cid != char_id:
			return cid
	return ""


## 检查指定角色是否为此交互对成员。
func is_member(char_id: String) -> bool:
	return char_id in char_ids


## 获取此 pair 中另一个角色的名称（需外部提供 name_map）。
func get_counterpart_name(char_id: String, name_map: Dictionary) -> String:
	var cid: String = get_counterpart(char_id)
	if cid == "":
		return ""
	return str(name_map.get(cid, cid))


## 转换为可序列化的 Dictionary
func to_dict() -> Dictionary:
	return {
		"pair_id": pair_id,
		"char_ids": char_ids.duplicate(),
		"pair_type": pair_type,
	}
