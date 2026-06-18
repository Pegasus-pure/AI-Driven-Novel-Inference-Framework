extends Node

## 小说扫描器 (Autoload 单例)
##
## 扫描 novel/ 目录 → 按书名分卷分组 → 检测是否有对应 canon
##
##   novel/福尔摩斯1.epub + novel/福尔摩斯2.epub → 同一本书
##   检测 src/data/canon_福尔摩斯.json 是否存在 → 标记为 ready
##
## canon 命名规则: src/data/canon_{书名}.json

const CANON_DIR: String = "res://src/data"

# { "book_id": {title, author, volumes, total_chars, canon_ready, canon_path} }
var _library: Dictionary = {}


func scan() -> Dictionary:
	_library.clear()
	var dir: String = "res://novel"
	if not DirAccess.dir_exists_absolute(dir):
		return _library

	var da: DirAccess = DirAccess.open(dir)
	if da == null:
		return _library

	# 收集所有 epub/txt 文件
	var files: Array = []
	da.list_dir_begin()
	var fname: String = da.get_next()
	while fname != "":
		if not da.current_is_dir():
			var ext: String = fname.get_extension().to_lower()
			if ext in ["epub", "txt"]:
				files.append(fname)
		fname = da.get_next()
	da.list_dir_end()

	# 分组：去掉尾部数字编号 → 同一本书
	var groups: Dictionary = {}
	for raw in files:
		var f: String = raw as String
		var base: String = _base_name(f)
		if not groups.has(base):
			groups[base] = []
		groups[base].append(f)

	var book_id: int = 0
	for base in groups:
		var vols: Array = groups[base] as Array
		vols.sort_custom(_vol_sorter)

		# 检查 canon 文件
		var clean_title: String = _extract_clean_title(base)
		var canon_path: String = CANON_DIR + "/canon_" + clean_title + ".json"
		var canon_ready: bool = FileAccess.file_exists(canon_path)

		var author: String = _extract_author(vols[0] as String)
		var completed: bool = _is_completed(vols[0] as String)

		var book: Dictionary = {
			"id": "book_%d" % book_id,
			"title": clean_title,
			"author": author,
			"completed": completed,
			"volumes": [],
			"total_chars": 0,
			"canon_ready": canon_ready,
			"canon_path": canon_path
		}
		for v_ in vols:
			var v: String = v_ as String
			book["volumes"].append({
				"path": "res://novel/" + v,
				"label": v.get_basename()
			})
		_library[book["id"]] = book
		book_id += 1

	return _library


func _base_name(filename: String) -> String:
	var name: String = filename.get_basename()
	# 去掉 UTF-8 BOM（部分 txt 文件开头有 \uFEFF）
	name = name.lstrip("\uFEFF")
	# 去掉 【完结】/【完結】 前缀
	name = _strip_completed_tag(name)
	# 去掉尾部卷号
	var result: String = name
	while result.ends_with("1") or result.ends_with("2") or result.ends_with("3") \
		or result.ends_with("一") or result.ends_with("二") or result.ends_with("三") \
		or result.ends_with("上") or result.ends_with("中") or result.ends_with("下"):
		result = result.left(result.length() - 1)
	return result.strip_edges()


## 从文件名中提取干净的标题
## 输入: 已去掉卷号的 basename
## 处理: 《书名》作者 → "书名"  /  普通书名 → 原名
func _extract_clean_title(raw: String) -> String:
	var clean_name: String = raw.lstrip("\uFEFF")
	clean_name = _strip_completed_tag(clean_name)
	# 如果以《开头，提取《》中的内容
	if clean_name.begins_with("《"):
		var end: int = clean_name.find("》")
		if end != -1:
			return clean_name.substr(1, end - 1)
	return clean_name.strip_edges()


## 从文件名中提取作者名
## 格式: 《书名》作者名.txt  → "作者名"
func _extract_author(filename: String) -> String:
	var author_name: String = filename.get_basename()
	author_name = author_name.lstrip("\uFEFF")
	author_name = _strip_completed_tag(author_name)
	# 如果文件名包含《》，提取》之后的内容作为作者名
	var bracket_end: int = author_name.find("》")
	if bracket_end != -1 and bracket_end + 1 < author_name.length():
		var extracted_author: String = author_name.substr(bracket_end + 1).strip_edges()
		if extracted_author != "":
			return extracted_author
	return "未知"


## 检测是否为完结小说
func _is_completed(filename: String) -> bool:
	var completed_name: String = filename.get_basename()
	completed_name = completed_name.lstrip("\uFEFF")
	return completed_name.begins_with("【完结】") or completed_name.begins_with("【完結】")


## 去掉 【完结】/【完結】 前缀
func _strip_completed_tag(name: String) -> String:
	var stripped_name: String = name.lstrip("\uFEFF")
	if stripped_name.begins_with("【完结】"):
		stripped_name = stripped_name.substr(4)
	elif stripped_name.begins_with("【完結】"):
		stripped_name = stripped_name.substr(4)
	return stripped_name


func _vol_sorter(a: String, b: String) -> bool:
	if a.get_extension() != b.get_extension():
		return a.get_extension() < b.get_extension()
	return a.nocasecmp_to(b) < 0


func get_book(book_id: String) -> Dictionary:
	return _library.get(book_id, {})


func get_library() -> Dictionary:
	return _library


func get_book_by_index(index: int) -> String:
	var i: int = 1
	for book_id in _library:
		if i == index:
			return book_id
		i += 1
	return ""


## 终端友好的列表文本 — 分两组
func get_library_text() -> String:
	if _library.is_empty():
		return "  (无小说 — 请将 epub/txt 放入 novel/ 目录)"

	var ready_lines: Array = []
	var need_canon_lines: Array = []
	var idx: int = 1

	for book_id in _library:
		var b: Dictionary = _library[book_id] as Dictionary
		var book_vols: Array = b["volumes"] as Array
		var vol_info: String = ""
		if book_vols.size() > 1:
			vol_info = " [%d卷]" % book_vols.size()
		var extra: String = ""
		if b.get("author", "未知") as String != "未知":
			extra += " · " + b["author"]
		if b.get("completed", false) as bool:
			extra += " · 已完结"
		var line: String = "  [%d] %s%s%s" % [idx, b["title"], vol_info, extra]
		if b["canon_ready"]:
			ready_lines.append(line)
		else:
			need_canon_lines.append(line)
		idx += 1

	var lines: Array = []
	if ready_lines.size() > 0:
		lines.append("[color=#5DCAA5]已就绪:[/color]")
		lines.append_array(ready_lines)
	if need_canon_lines.size() > 0:
		if lines.size() > 0:
			lines.append("")
		lines.append("[color=#F5C4B3]缺少 canon:[/color]")
		lines.append_array(need_canon_lines)
		lines.append("  [color=#888](需要运行 canon 提取或放入 canon_{书名}.json)[/color]")

	return "\n".join(lines)


func get_ready_count() -> int:
	var n: int = 0
	for book_id in _library:
		var book_info: Dictionary = _library[book_id] as Dictionary
		if book_info["canon_ready"]:
			n += 1
	return n
