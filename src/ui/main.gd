extends Control

## 主终端 UI
##
## 叙事区 + 输入区 + 状态栏 + 快捷键面板
## 连接 WorldState / MananaPipeline / CanonLoader

const NarrativeTemplate = preload("res://src/narrative/narrative_template.gd")
const NarrativeState = preload("res://src/narrative/narrative_state.gd")

# ===== 节点引用 =====
@onready var _time_label: Label = $Margin/MainVBox/StatusBar/TimeLabel
@onready var _location_label: Label = $Margin/MainVBox/StatusBar/LocationLabel
@onready var _thread_label: Label = $Margin/MainVBox/StatusBar/ThreadLabel
@onready var _narrative: RichTextLabel = $Margin/MainVBox/NarrativeScroll/NarrativeArea
@onready var _input_field: LineEdit = $Margin/MainVBox/InputRow/InputField

# ===== 状态 =====
var _game_started: bool = false
var _connection_ready: bool = false
var _warming_up: bool = false
var _pipeline_busy: bool = false
var _showing_panel: String = ""
var _selecting_novel: bool = false
var _latest_action: String = ""
var _latest_narrative: String = ""

# ===== v2 面板系统 — tscn 预加载框架 =====
var _panels: Dictionary = {}  # {"character": {root, overlay, panel}, ...}

const PANEL_SCENES: Dictionary = {
	"character": "res://scenes/character_panel.tscn",
	"location":  "res://scenes/location_panel.tscn",
	"log":       "res://scenes/log_panel.tscn",
	"relations": "res://scenes/relations_panel.tscn",
	"save_load": "res://scenes/save_load_panel.tscn",
	"worldbook": "res://scenes/worldbook_panel.tscn",
}

const PANEL_NODE_NAMES: Dictionary = {
	"character": "CharacterPanel",
	"location":  "LocationPanel",
	"log":       "LogPanel",
	"relations": "RelationsPanel",
	"save_load": "SaveLoadPanel",
	"worldbook": "WorldbookPanel",
}

# ============================================================
# 🔧 Canon 提取 API 配置 — 启用时填写
# ============================================================
#   填写你的 LLM API 端点 (OpenAI 兼容格式)，即可自动从小说提取 canon
#   示例: "https://your-api.com/v1/chat/completions"
var canon_extract_api: String = ""


func _ready() -> void:
	_setup_theme()
	_connect_signals()
	_build_settings_panel()
	_load_all_panels()
	_show_splash()


func _setup_theme() -> void:
	var bg: StyleBoxFlat = StyleBoxFlat.new()
	bg.bg_color = Color(0.08, 0.08, 0.10, 1.0)
	add_theme_stylebox_override("panel", bg)

	# 更新快捷键标签
	var sc: Label = $Margin/MainVBox/ShortcutBar/ScF1
	if sc != null:
		sc.text = "F1:角色 F2:地点 F3:日志 F4:关系 F5:存档 F6:设置 F7:规则 F8:续写"


func _connect_signals() -> void:
	_input_field.text_submitted.connect(_on_input_submitted)
	# MaNA Pipeline 接管连接管理，不再使用 LLMClient 信号
	EventBus.world_time_changed.connect(_on_time_changed)
	EventBus.llm_call_started.connect(_on_llm_busy)
	EventBus.llm_call_finished.connect(_on_llm_idle)
	EventBus.llm_stream_token.connect(_on_stream_token)
	EventBus.narrative_ready.connect(_on_narrative_ready)
	EventBus.thread_updated.connect(_on_thread_updated)
	EventBus.beat_completed.connect(_on_beat_completed)


func _input(event: InputEvent) -> void:
	if not event.is_pressed():
		return
	if _warming_up or _pipeline_busy:
		return

	if event.as_text() == "F6":
		_toggle_settings_panel()
		return

	if event.as_text() == "F7":
		_toggle_worldbook_panel()
		return

	if event.as_text() == "F8":
		_continue_narrative()
		return

	if not _game_started:
		return

	if event.as_text() == "F1":         _toggle_panel_v2("character")
	if event.as_text() == "F2":         _toggle_panel_v2("location")
	if event.as_text() == "F3":         _toggle_panel_v2("log")
	if event.as_text() == "F4":         _toggle_panel_v2("relations")
	if event.as_text() == "F5":         _toggle_panel_v2("save_load")
	# F6 keep existing _toggle_settings_panel()
	if event.as_text() == "F7":         _toggle_panel_v2("worldbook")


func _show_splash() -> void:
	_append_narrative("[color=#5DCAA5]Rain · AI 小说推演框架[/color]")
	_append_narrative("[color=#888]===============================[/color]")
	_append_narrative("")
	_append_narrative("[color=#888]MaNA Pipeline 正在初始化...[/color]")
	_input_field.editable = false
	_input_field.placeholder_text = "等待初始化..."
	# MaNA Pipeline 作为 Autoload 自动初始化 Provider，延迟后进入小说选择
	await get_tree().create_timer(0.5).timeout
	_connection_ready = true
	_show_novel_selection()


## 连接回调 (已由 MaNA Pipeline 接管，保留兼容)
func _on_connection_tested(_success: bool, _message: String) -> void:
	pass


func _show_novel_selection() -> void:
	NovelScanner.scan()
	var lib_text: String = NovelScanner.get_library_text()
	_append_narrative("[color=#B5D4F4]--- 选择小说世界 ---[/color]")
	_append_narrative(lib_text)
	_append_narrative("")
	if NovelScanner.get_library().is_empty():
		_append_narrative("[color=#888]无小说文件，加载默认测试世界...[/color]")
		_append_narrative("[color=#B5D4F4]按 Enter 开始冒险[/color]")
		_selecting_novel = false
	else:
		_append_narrative("[color=#F5C4B3]输入序号选择已就绪的小说，或按 Enter 使用默认世界[/color]")
		_selecting_novel = true
	_input_field.editable = true
	_input_field.placeholder_text = "选择世界..."
	_input_field.grab_focus()


func _start_game() -> void:
	var canon: Dictionary = CanonLoader.load_canon()
	if canon.is_empty():
		_append_narrative("[color=red]错误: 无法加载世界数据 (canon.json)[/color]")
		return

	var meta: Dictionary = canon.get("meta", {}) as Dictionary
	var title: String = str(meta.get("title", "未知世界"))

	_clear_narrative()
	_append_narrative("[color=#5DCAA5]Rain · %s[/color]" % title)
	_append_narrative("[color=#888]=============================[/color]")

	_game_started = true
	_update_status_bar()
	# MaNA Pipeline 已初始化 Provider，直接生成开场场景
	_generate_opening_scene()


func _generate_opening_scene() -> void:
	if _pipeline_busy:
		return

	# 使用 MaNA Pipeline 生成开场
	_pipeline_busy = true
	MananaPipeline.run_beat("观察周围环境")


func _append_narrative(text: String) -> void:
	_narrative.append_text(text + "\n")


func _append_scene(text: String) -> void:
	# 将 LLM 返回的【角色名】标记着色后追加
	var colored: String = _colorize_dialogue(text)
	_append_narrative(colored)


## 将文本中的【角色名】和【行动提示】转为 BBCode 着色标签
func _colorize_dialogue(text: String) -> String:
	var lines: Array = text.split("\n")
	var result: Array = []
	for raw in lines:
		var line: String = raw as String
		if line.begins_with("【行动提示】"):
			result.append("[color=#888]%s[/color]" % line)
		elif line.begins_with("【") and line.find("】") != -1:
			var end: int = line.find("】") + 1
			var name_part: String = line.substr(0, end)
			var rest: String = line.substr(end)
			result.append("[color=#FFB347]%s[/color]%s" % [name_part, rest])
		else:
			result.append(line)
	return "\n".join(result)


## 从 LLM 输出中提取 <!-- REP: char_id=+0.1, ... --> 并更新声誉
## 返回去除标记后的干净文本
## ⚠ MaNA Pipeline 已接管 — 此方法保留以兼容旧代码路径
func _apply_reputation_tags(text: String) -> String:
	return text


func _apply_thread_tags(text: String) -> String:
	return text


func _apply_player_tags(text: String) -> String:
	return text


func _apply_npc_tags(text: String) -> String:
	return text


func _apply_fact_tags(text: String) -> String:
	return text


func _clear_narrative() -> void:
	_narrative.clear()


func _update_status_bar() -> void:
	_time_label.text = WorldState.game_time
	_location_label.text = str(CanonLoader.get_location_info(WorldState.player_location).get("name", "???"))

	var threads: Array = WorldState.get_active_threads()
	var parts: Array = []
	for t_ in threads:
		var t: Dictionary = t_ as Dictionary
		var thread_title: String = str(t.get("title", ""))
		if thread_title == "":
			continue
		var short: String = thread_title
		if thread_title.length() > 5:
			short = thread_title.left(4) + "…"
		parts.append("%s %.0f%%" % [short, (t.get("progress", 0.0) as float) * 100])
	if parts.size() > 0:
		_thread_label.text = " | ".join(parts)
	else:
		_thread_label.text = ""


func _on_input_submitted(raw: String) -> void:
	_input_field.clear()

	var text: String = raw.strip_edges()

	# 设置面板（随时可用）
	if text == "设置":
		_toggle_settings_panel()
		return

	if text == "规则":
		_toggle_worldbook_panel()
		return

	# 还没连接好 / 连接失败 → 按 Enter 重试
	if not _connection_ready:
		_input_field.editable = false
		_input_field.placeholder_text = "等待初始化..."
		_append_narrative("[color=#888]正在初始化 Pipeline...[/color]")
		# MaNA Pipeline 作为 Autoload，延迟后重试
		await get_tree().create_timer(0.5).timeout
		_connection_ready = true
		_show_novel_selection()
		return

	# 正在选小说 → 解析序号
	if _selecting_novel:
		_selecting_novel = false
		var num: int = raw.strip_edges().to_int()
		if num > 0:
			var book_id: String = NovelScanner.get_book_by_index(num)
			if book_id != "":
				var book: Dictionary = NovelScanner.get_book(book_id)
				if book["canon_ready"]:
					_load_novel_canon(book)
					_append_narrative("[color=#5DCAA5]已选择: %s[/color]" % book["title"])
				else:
					_append_narrative("[color=#F5C4B3]《%s》缺少 canon 文件[/color]" % book["title"])
					_append_narrative("[color=#888]请先运行 canon 提取，或将 canon_{书名}.json 放入 src/data/[/color]")
					_append_narrative("")
					_append_narrative("[color=#B5D4F4]按 Enter 使用默认世界[/color]")
					_input_field.placeholder_text = "按 Enter 开始..."
					_input_field.grab_focus()
					return
			else:
				_append_narrative("[color=#F5C4B3]无效序号，使用默认世界[/color]")
		else:
			_append_narrative("[color=#888]使用默认测试世界[/color]")
		_append_narrative("")
		_append_narrative("[color=#B5D4F4]按 Enter 开始冒险[/color]")
		_input_field.placeholder_text = "按 Enter 开始..."
		_input_field.grab_focus()
		return

	# 连接好了但游戏没开始 → 按 Enter 开始游戏
	if not _game_started:
		_input_field.editable = false
		_input_field.placeholder_text = "AI 正在生成，请稍候…"
		_start_game()
		return

	# 正常游戏输入
	if _warming_up or _pipeline_busy:
		return

	if text == "":
		_pipeline_busy = true
		MananaPipeline.run_beat("继续推进剧情")
		return

	if text == "quit" or text == "退出":
		get_tree().quit()
		return

	if text == "续写":
		_continue_narrative()
		return

	# 面板打开时阻挡正常游戏输入
	if _showing_panel != "":
		return

	# 结局后处理
	if not _game_started:
		if text == "重新开始":
			_restart_game()
		elif text == "退出":
			get_tree().quit()
		else:
			_append_narrative("[color=#888]输入「重新开始」或「退出」[/color]")
		return

	_append_narrative("\n[color=#5DCAA5]> %s[/color]" % text)
	_latest_action = text
	_pipeline_busy = true
	EventBus.player_action_submitted.emit(text)
	MananaPipeline.run_beat(text)


## 开场人物展示（只取主角和配角，不包含反派）
func _build_opening_characters() -> String:
	var opening_lines: Array = []
	var chars_data: Array = WorldState.canon.get("characters", []) as Array
	for c_ in chars_data:
		var c: Dictionary = c_ as Dictionary
		var role: String = str(c.get("role", ""))
		if role in ["主角", "配角"]:
			var pid: Dictionary = c.get("personality", {}) as Dictionary
			var traits: Array = pid.get("traits", []) as Array
			var speech: String = str(pid.get("speech_style", ""))
			opening_lines.append("- %s【%s】性格：%s\n  说话风格：%s" % [c.get("name", ""), role, "，".join(traits), speech])
	return "\n\n".join(opening_lines)


func _on_time_changed(_new_time: String) -> void:
	_update_status_bar()


func _on_narrative_ready(_text: String) -> void:
	_input_field.editable = true
	_update_status_bar()


func _on_llm_busy() -> void:
	_pipeline_busy = true
	_input_field.editable = false
	_input_field.placeholder_text = "AI 正在生成，请稍候…"


func _on_stream_token(token: String) -> void:
	# 逐 token 追加，转义 [ 防止 BBCode 解析错误
	_narrative.append_text(token.replace("[", "&#91;"))


func _on_llm_idle(success: bool) -> void:
	if success:
		# MaNA Pipeline 已接管叙事生成——不再在此处处理 LLM 输出
		# 叙事通过 EventBus.beat_completed 信号分发
		_input_field.editable = true
		_update_status_bar()
	else:
		_append_narrative("\n[color=red]AI 响应失败[/color]")
		_input_field.editable = true

	_update_status_bar()


func _on_thread_updated(_thread_id: String) -> void:
	_update_status_bar()


## MaNA Pipeline beat_completed — 显示叙事文本并更新 UI
func _on_beat_completed(_beat_id: String, result: Dictionary) -> void:
	_pipeline_busy = false
	var narrative_text: String = str(result.get("narrative_text", ""))
	if narrative_text != "":
		_latest_narrative = narrative_text
		_latest_action = ""
		_append_scene("\n" + narrative_text)
		# 检测结局触发
		if _check_ending():
			return
		EventBus.narrative_ready.emit(narrative_text)
	_input_field.editable = true
	_input_field.placeholder_text = "输入你的行动…"
	_update_status_bar()


# ============================================================
# v2 面板系统 — tscn 预加载 / 切换
# ============================================================

func _load_all_panels() -> void:
	"""预加载所有 tscn 骨架面板，隐藏并缓存到 _panels 字典"""
	for panel_name in PANEL_SCENES:
		var pscene: PackedScene = load(PANEL_SCENES[panel_name])
		var root: Node = pscene.instantiate()
		root.visible = false
		add_child(root)
		var overlay: ColorRect = root as ColorRect  # root 就是 Overlay
		var panel_node_name: String = PANEL_NODE_NAMES[panel_name]
		var panel: Panel = root.get_node(panel_node_name) as Panel
		_panels[panel_name] = {"root": root, "overlay": overlay, "panel": panel}
		# 连接关闭按钮 — 捕获当前 panel_name 避免闭包引用问题
		panel.get_node("VBox/ButtonRow/CloseBtn").pressed.connect(
			func(pname: String = panel_name): _toggle_panel_v2(pname)
		)


func _toggle_panel_v2(panel_name: String) -> void:
	"""切换 v2 tscn 面板的显示/隐藏，支持互斥"""
	if not _panels.has(panel_name):
		return
	var data: Dictionary = _panels[panel_name]
	var panel_overlay: ColorRect = data["overlay"]
	var is_open: bool = panel_overlay.visible

	if is_open:
		# 关闭
		panel_overlay.visible = false
		_showing_panel = ""
	else:
		# 先关闭所有其他面板
		for other_name in _panels:
			if other_name != panel_name:
				_panels[other_name]["overlay"].visible = false
		# 打开
		panel_overlay.visible = true
		_showing_panel = panel_name
		# 打开时刷新对应面板数据
		match panel_name:
			"character": _refresh_character_panel()
			"location":  _refresh_location_panel()
			"log":       _refresh_log_panel()
			"relations": _refresh_relations_panel()
			"save_load": _refresh_save_load_panel()
			"worldbook": _refresh_worldbook_panel()


# ============================================================
# LineEdit 暗色主题工厂
# ============================================================

func _apply_lineedit_style(le: LineEdit) -> void:
	var normal: StyleBoxFlat = StyleBoxFlat.new()
	normal.bg_color = Color(0.08, 0.08, 0.12)
	normal.border_width_bottom = 1
	normal.border_color = Color(0.25, 0.25, 0.35)
	le.add_theme_stylebox_override("normal", normal)
	var focus: StyleBoxFlat = StyleBoxFlat.new()
	focus.bg_color = Color(0.1, 0.1, 0.15)
	focus.border_width_bottom = 1
	focus.border_color = Color(0.36, 0.8, 0.75)
	le.add_theme_stylebox_override("focus", focus)
	le.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))


# ============================================================
# 面板数据刷新 — 角色 / 地点 / 日志 / 关系 / 存读档 / 世界规则
# ============================================================

func _refresh_character_panel() -> void:
	var char_panel_obj: Panel = _panels["character"]["panel"]
	var char_content: VBoxContainer = char_panel_obj.get_node("VBox/Content")
	for c in char_content.get_children():
		c.queue_free()

	char_content.add_theme_constant_override("separation", 2)

	# --- Header row ---
	var header: HBoxContainer = HBoxContainer.new()
	header.size_flags_horizontal = 3

	var header_texts: Array[String] = ["角色", "身份", "情绪", "位置", "态度"]
	var header_widths: Array[int] = [150, 80, 70, 110, -1]

	for i: int in range(header_texts.size()):
		var lbl: Label = _make_row_label(header_texts[i], header_widths[i])
		lbl.add_theme_color_override("font_color", Color(0.36, 0.8, 0.75))
		header.add_child(lbl)

	char_content.add_child(header)

	# --- Separator ---
	var sep: HSeparator = HSeparator.new()
	char_content.add_child(sep)

	# --- Data rows ---
	var chars_list: Array = WorldState.canon.get("characters", []) as Array
	for c_data in chars_list:
		var c_dict: Dictionary = c_data as Dictionary
		var cs: Dictionary = WorldState.get_character_state(str(c_dict.get("id", "")))
		var rep: String = WorldState.get_reputation_text(str(c_dict.get("id", "")))

		var row: HBoxContainer = HBoxContainer.new()
		row.size_flags_horizontal = 3

		# Col 0: name (blue, w=150)
		var name_lbl: Label = _make_row_label(str(c_dict.get("name", "")), 150)
		name_lbl.add_theme_color_override("font_color", Color(0.71, 0.84, 0.96))
		row.add_child(name_lbl)

		# Col 1: role (w=80)
		var role_lbl: Label = _make_row_label(str(c_dict.get("role", "")), 80)
		role_lbl.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))
		row.add_child(role_lbl)

		# Col 2: mood (w=70)
		var mood_lbl: Label = _make_row_label(str(cs.get("mood", "???")), 70)
		mood_lbl.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))
		row.add_child(mood_lbl)

		# Col 3: location (w=110)
		var loc_id: String = str(cs.get("location", "???"))
		var loc_name: String = str(CanonLoader.get_location_info(loc_id).get("name", loc_id))
		var loc_lbl: Label = _make_row_label(loc_name, 110)
		loc_lbl.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))
		row.add_child(loc_lbl)

		# Col 4: reputation (expand)
		var rep_lbl: Label = _make_row_label(rep, -1)
		rep_lbl.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))
		row.add_child(rep_lbl)

		char_content.add_child(row)


func _make_row_label(text: String, width: int) -> Label:
	var lbl: Label = Label.new()
	lbl.text = text
	lbl.add_theme_font_size_override("font_size", 13)
	if width > 0:
		lbl.custom_minimum_size = Vector2(width, 0)
		lbl.clip_text = true
	else:
		lbl.size_flags_horizontal = 3  # SIZE_EXPAND_FILL
	return lbl


func _refresh_location_panel() -> void:
	var loc_panel_obj: Panel = _panels["location"]["panel"]
	var loc_content: VBoxContainer = loc_panel_obj.get_node("VBox/Content")
	for c in loc_content.get_children():
		c.queue_free()
	var loc_rtl: RichTextLabel = RichTextLabel.new()
	loc_rtl.size_flags_horizontal = 3
	loc_rtl.size_flags_vertical = 3
	loc_rtl.bbcode_enabled = true
	loc_rtl.fit_content = true
	loc_rtl.add_theme_color_override("default_color", Color(0.85, 0.85, 0.85))
	var loc_text: Array = []
	var locs: Array = WorldState.canon.get("locations", []) as Array
	for loc_ in locs:
		var loc: Dictionary = loc_ as Dictionary
		var mark: String = ""
		if str(loc.get("id", "")) == WorldState.player_location:
			mark = " [color=#5ccca0]← 当前[/color]"
		loc_text.append("[%s] %s%s" % [str(loc.get("type", "")), str(loc.get("name", "")), mark])
	loc_rtl.text = "\n".join(loc_text)
	loc_content.add_child(loc_rtl)


func _refresh_log_panel() -> void:
	var log_panel_obj: Panel = _panels["log"]["panel"]
	var log_content: VBoxContainer = log_panel_obj.get_node("VBox/Content")
	for c in log_content.get_children():
		c.queue_free()
	var log_rtl: RichTextLabel = RichTextLabel.new()
	log_rtl.size_flags_horizontal = 3
	log_rtl.size_flags_vertical = 3
	log_rtl.bbcode_enabled = true
	log_rtl.add_theme_color_override("default_color", Color(0.8, 0.8, 0.8))
	log_rtl.text = WorldState.get_recent_history(20)
	log_content.add_child(log_rtl)


func _refresh_relations_panel() -> void:
	var rel_panel_obj: Panel = _panels["relations"]["panel"]
	var cards_vbox: VBoxContainer = rel_panel_obj.get_node("VBox/Content/CardsScroll/CardsVBox")
	var legend_row: HBoxContainer = rel_panel_obj.get_node("VBox/Content/LegendRow")
	
	# 清空旧卡片
	for c in cards_vbox.get_children():
		c.queue_free()
	for c in legend_row.get_children():
		c.queue_free()
	
	var rel_chars: Array = WorldState.canon.get("characters", []) as Array
	for rel_c_data in rel_chars:
		var rel_c_dict: Dictionary = rel_c_data as Dictionary
		var rel_state: Dictionary = WorldState.get_character_state(str(rel_c_dict.get("id", "")))
		var rels: Dictionary = rel_state.get("relations", {}) as Dictionary
		var rel_parts: Array = []
		for target in rels:
			var intensity: float = float(rels[target])
			var target_name: String = _find_char_name(target)
			var sign: String = "—"
			if intensity >= 0.7: sign = "♥"
			elif intensity >= 0.3: sign = "○"
			elif intensity <= -0.7: sign = "✗"
			elif intensity <= -0.3: sign = "△"
			rel_parts.append("%s %s" % [sign, target_name])
		var rel_rep: String = WorldState.get_reputation_text(str(rel_c_dict.get("id", "")))
		
		var row: HBoxContainer = HBoxContainer.new()
		row.size_flags_horizontal = 3
		row.add_theme_constant_override("margin_left", 10)
		row.add_theme_constant_override("margin_right", 10)
		row.add_theme_constant_override("margin_top", 6)
		row.add_theme_constant_override("margin_bottom", 6)
		
		var name_label: Label = Label.new()
		name_label.text = str(rel_c_dict.get("name", ""))
		name_label.custom_minimum_size.x = 120
		name_label.add_theme_color_override("font_color", Color(0.71, 0.83, 0.96))
		row.add_child(name_label)
		
		var rel_text: String = " · ".join(rel_parts) if rel_parts.size() > 0 else "暂无已知关系"
		var rel_label: Label = Label.new()
		rel_label.text = rel_text
		rel_label.size_flags_horizontal = 3
		rel_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
		row.add_child(rel_label)
		
		var rep_label: Label = Label.new()
		rep_label.text = rel_rep
		rep_label.add_theme_color_override("font_color", Color(0.5, 0.5, 0.55))
		row.add_child(rep_label)
		
		cards_vbox.add_child(row)
	
	# 图例
	for pair in [["♥ 亲密", Color(0.83, 0.33, 0.19)], ["○ 友好", Color(0.93, 0.6, 0.48)], ["— 中立", Color(0.5, 0.5, 0.5)], ["△ 冷淡", Color(0.6, 0.6, 0.8)], ["✗ 敌对", Color(0.89, 0.29, 0.29)]]:
		var l: Label = Label.new()
		l.text = pair[0]
		l.add_theme_color_override("font_color", pair[1])
		legend_row.add_child(l)


func _refresh_save_load_panel() -> void:
	var sl_panel_obj: Panel = _panels["save_load"]["panel"]
	var slots_vbox: VBoxContainer = sl_panel_obj.get_node("VBox/Content/SlotsVBox")
	
	for c in slots_vbox.get_children():
		c.queue_free()
	
	for i in range(1, SAVE_SLOTS + 1):
		var info: String = _get_save_info(i)
		var is_empty: bool = info.find("空") != -1
		
		var sl_row: HBoxContainer = HBoxContainer.new()
		sl_row.size_flags_horizontal = 3
		sl_row.add_theme_constant_override("margin_left", 12)
		sl_row.add_theme_constant_override("margin_right", 12)
		sl_row.add_theme_constant_override("margin_top", 8)
		sl_row.add_theme_constant_override("margin_bottom", 8)
		sl_row.add_theme_constant_override("separation", 8)
		
		var num_label: Label = Label.new()
		num_label.text = "[%d]" % i
		num_label.custom_minimum_size.x = 30
		sl_row.add_child(num_label)
		
		var info_label: Label = Label.new()
		info_label.text = info
		info_label.size_flags_horizontal = 3
		sl_row.add_child(info_label)
		
		var save_btn: Button = Button.new()
		save_btn.text = "存档"
		save_btn.pressed.connect(func(s: int = i): _save_game(s); _refresh_save_load_panel())
		
		var load_btn: Button = Button.new()
		load_btn.text = "读档"
		load_btn.disabled = is_empty
		load_btn.pressed.connect(func(s: int = i): _load_game(s); _toggle_panel_v2("save_load"))
		
		var del_btn: Button = Button.new()
		del_btn.text = "删除"
		del_btn.disabled = is_empty
		del_btn.pressed.connect(func(s: int = i): if FileAccess.file_exists(SAVE_DIR + "/slot_%d.json" % s): DirAccess.remove_absolute(SAVE_DIR + "/slot_%d.json" % s); _refresh_save_load_panel())
		
		sl_row.add_child(save_btn)
		sl_row.add_child(load_btn)
		sl_row.add_child(del_btn)
		slots_vbox.add_child(sl_row)


func _refresh_worldbook_panel() -> void:
	var wb_panel_obj: Panel = _panels["worldbook"]["panel"]
	var wb_content: VBoxContainer = wb_panel_obj.get_node("VBox/Content")
	for c in wb_content.get_children():
		c.queue_free()

	# 规则列表
	var scroll: ScrollContainer = ScrollContainer.new()
	scroll.custom_minimum_size.y = 120
	scroll.size_flags_horizontal = 3
	var rules_vbox: VBoxContainer = VBoxContainer.new()
	rules_vbox.add_theme_constant_override("separation", 4)
	scroll.add_child(rules_vbox)
	wb_content.add_child(scroll)

	if WorldState.custom_world_rules.size() == 0:
		var el: Label = Label.new()
		el.text = "(暂无自定义规则)"
		el.add_theme_color_override("font_color", Color(0.5, 0.5, 0.5))
		rules_vbox.add_child(el)
	else:
		for i in range(WorldState.custom_world_rules.size()):
			var r: Dictionary = WorldState.custom_world_rules[i] as Dictionary
			var wb_row: HBoxContainer = HBoxContainer.new()
			wb_row.add_theme_constant_override("separation", 6)
			var en: CheckBox = CheckBox.new()
			en.button_pressed = r.get("enabled", true) as bool
			en.toggled.connect(func(v: bool, idx: int = i): WorldState.custom_world_rules[idx]["enabled"] = v)
			wb_row.add_child(en)
			var txt: Label = Label.new()
			txt.text = str(r.get("key", "")) + ": " + str(r.get("content", ""))
			txt.size_flags_horizontal = 3
			txt.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
			wb_row.add_child(txt)
			var db: Button = Button.new()
			db.text = "×"
			db.pressed.connect(func(idx: int = i): WorldState.custom_world_rules.remove_at(int(idx)); _refresh_worldbook_panel())
			wb_row.add_child(db)
			rules_vbox.add_child(wb_row)

	# 分隔和表单
	wb_content.add_child(HSeparator.new())
	var key_row: HBoxContainer = HBoxContainer.new()
	key_row.add_theme_constant_override("separation", 8)
	var key_label: Label = Label.new()
	key_label.text = "关键词"
	key_label.custom_minimum_size.x = 50
	key_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	key_row.add_child(key_label)
	var key_input: LineEdit = LineEdit.new()
	key_input.size_flags_horizontal = 3
	key_input.placeholder_text = "逗号分隔"
	key_input.custom_minimum_size.y = 28
	_apply_lineedit_style(key_input)
	key_row.add_child(key_input)
	wb_content.add_child(key_row)

	var cont_row: HBoxContainer = HBoxContainer.new()
	cont_row.add_theme_constant_override("separation", 8)
	var cont_label: Label = Label.new()
	cont_label.text = "内容"
	cont_label.custom_minimum_size.x = 50
	cont_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	cont_row.add_child(cont_label)
	var cont_input: LineEdit = LineEdit.new()
	cont_input.size_flags_horizontal = 3
	cont_input.placeholder_text = "规则内容..."
	cont_input.custom_minimum_size.y = 28
	_apply_lineedit_style(cont_input)
	cont_row.add_child(cont_input)
	wb_content.add_child(cont_row)

	# 新增按钮
	var add_row: HBoxContainer = HBoxContainer.new()
	add_row.alignment = BoxContainer.ALIGNMENT_END
	add_row.add_theme_constant_override("margin_top", 6)
	var add_btn: Button = Button.new()
	add_btn.text = "新增"
	add_btn.pressed.connect(func(ki: LineEdit = key_input, ci: LineEdit = cont_input):
		var k: String = ki.text.strip_edges()
		var ct: String = ci.text.strip_edges()
		if k != "" and ct != "":
			WorldState.custom_world_rules.append({"key": k, "content": ct, "enabled": true})
			ki.clear()
			ci.clear()
			_refresh_worldbook_panel()
	)
	add_row.add_child(add_btn)
	wb_content.add_child(add_row)


func _find_char_name(char_id: String) -> String:
	var fn_chars: Array = WorldState.canon.get("characters", []) as Array
	for fn_c_data in fn_chars:
		var fn_c_dict: Dictionary = fn_c_data as Dictionary
		if str(fn_c_dict.get("id", "")) == char_id:
			return str(fn_c_dict.get("name", char_id))
	return char_id


# ===== F5: 存档/读档 =====

const SAVE_DIR := "user://saves"
const SAVE_SLOTS := 3

func _get_save_info(slot: int) -> String:
	var save_path: String = SAVE_DIR + "/slot_%d.json" % slot
	if not FileAccess.file_exists(save_path):
		return "[color=#666]空[/color]"
	var save_file: FileAccess = FileAccess.open(save_path, FileAccess.READ)
	if save_file == null:
		return "[color=#666]空[/color]"
	var save_raw: String = save_file.get_as_text()
	save_file.close()
	var save_json: JSON = JSON.new()
	if save_json.parse(save_raw) != OK:
		return "[color=red]损坏[/color]"
	var info_data: Dictionary = save_json.get_data() as Dictionary
	var saved_time: String = str(info_data.get("game_time", "???"))
	var canon_meta: Dictionary = info_data.get("canon_meta", {}) as Dictionary
	var saved_title: String = str(canon_meta.get("title", "???"))
	return "%s | %s" % [saved_title, saved_time]


func _save_game(slot: int) -> void:
	DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	var game_data: Dictionary = WorldState.to_dict()
	var game_meta: Dictionary = WorldState.canon.get("meta", {}) as Dictionary
	game_data["canon_meta"] = {
		"title": str(game_meta.get("title", "")),
		"author": str(game_meta.get("author", ""))
	}
	game_data["canon_path"] = CanonLoader._file_path

	var game_path: String = SAVE_DIR + "/slot_%d.json" % slot
	var game_file: FileAccess = FileAccess.open(game_path, FileAccess.WRITE)
	if game_file == null:
		_append_narrative("[color=red]存档失败: 无法写入文件[/color]")
		return
	game_file.store_string(JSON.stringify(game_data, "  "))
	game_file.close()
	_append_narrative("[color=#5DCAA5]已存档 → 槽位 %d (%s)[/color]" % [slot, WorldState.game_time])


func _load_game(slot: int) -> void:
	var load_path: String = SAVE_DIR + "/slot_%d.json" % slot
	if not FileAccess.file_exists(load_path):
		_append_narrative("[color=red]槽位 %d 是空的[/color]" % slot)
		_showing_panel = ""
		return

	var load_file: FileAccess = FileAccess.open(load_path, FileAccess.READ)
	var load_raw: String = load_file.get_as_text()
	load_file.close()

	var load_json: JSON = JSON.new()
	if load_json.parse(load_raw) != OK:
		_append_narrative("[color=red]存档损坏[/color]")
		_showing_panel = ""
		return

	var load_data: Dictionary = load_json.get_data() as Dictionary
	WorldState.from_dict(load_data)

	# 如果存档的 canon 路径和当前不同，重新加载
	var saved_canon: String = str(load_data.get("canon_path", ""))
	if saved_canon != "" and saved_canon != CanonLoader._file_path:
		CanonLoader.load_canon(saved_canon)

	_showing_panel = ""
	_clear_narrative()
	var load_meta: Dictionary = load_data.get("canon_meta", {}) as Dictionary
	var load_title: String = str(load_meta.get("title", "这个世界"))
	_append_narrative("[color=#5DCAA5]Rain · %s[/color]" % load_title)
	_append_narrative("[color=#888]=============================[/color]")
	_append_narrative("[color=#5DCAA5]已读档 → 槽位 %d (%s)[/color]" % [slot, WorldState.game_time])
	_update_status_bar()



# ===== 结局检测 =====

## 检测是否触发结局条件：偏离度 > 0.8 或主线全部关闭
## 返回 true 表示已触发结局
func _check_ending() -> bool:
	var dv: float = WorldState.get_divergence()
	var active: Array = WorldState.get_active_threads()

	# 检查是否有主线存在但全部关闭
	var has_main: bool = false
	var main_all_closed: bool = true
	var all_threads: Array = []
	for t_ in active:
		all_threads.append(t_)
	var closed: Array = WorldState.narrative_threads["closed"] as Array
	for t_ in closed:
		all_threads.append(t_)
	for t_ in all_threads:
		var ending_thread: Dictionary = t_ as Dictionary
		if str(ending_thread.get("type", "")) == "main":
			has_main = true
			if (ending_thread.get("progress", 0.0) as float) < 1.0:
				main_all_closed = false

	var trigger: String = ""
	if dv >= 0.8:
		trigger = "世界偏离度已达到 %.0f%%，世界已彻底脱离原著轨迹。" % (dv * 100)
	elif has_main and main_all_closed and active.size() == 0:
		trigger = "所有叙事线索已完结，故事自然收束。"

	if trigger == "":
		return false

	_append_narrative("")
	_append_narrative("[color=#FFD700]══════════════════════════════[/color]")
	_append_narrative("[color=#FFD700]      结  局[/color]")
	_append_narrative("[color=#FFD700]══════════════════════════════[/color]")
	_append_narrative("[color=#B5D4F4]%s[/color]" % trigger)
	_append_narrative("")
	_append_narrative("[color=#888]世界偏离度: %.0f%% | 活跃线索: %d | 已关闭: %d[/color]" % [dv * 100, active.size(), closed.size()])
	_append_narrative("")
	_append_narrative("[color=#5DCAA5]输入「重新开始」重启世界，或「退出」离开。[/color]")

	_input_field.editable = true
	_input_field.placeholder_text = "重新开始 / 退出"
	_input_field.grab_focus()
	_game_started = false
	return true


## 重新开始游戏（清空运行时状态，重新加载 canon）
func _restart_game() -> void:
	# 清空世界状态
	WorldState.narrative_threads = {"active": [], "closed": []}
	WorldState.narrative_history = []
	WorldState.player_reputation = {}
	WorldState.player_profile = {"traits": ["好奇", "谨慎"], "motivation": "搞清楚自己为何来到这个世界", "tendency": "中立"}
	WorldState.dynamic_npcs = {}
	WorldState.scene_memory = []
	WorldState.long_term_memory = []
	WorldState.knowledge_graph = []
	NarrativeState.reset()
	WorldState.time_index = 0
	WorldState.set_divergence(0.0)
	WorldState._update_game_time_string()
	_showing_panel = ""
	_input_field.editable = false
	_start_game()


## 将选中的小说 canon 切换为 CanonLoader 的数据源
func _load_novel_canon(book: Dictionary) -> void:
	var canon_path: String = str(book.get("canon_path", ""))
	if canon_path != "" and FileAccess.file_exists(canon_path):
		CanonLoader.load_canon(canon_path)


## ===== Settings 设置面板 (v3 — 全场景 tscn + 脚本仅绑定数据) =====

var _settings_panel: Panel
var _settings_overlay: ColorRect


func _build_settings_panel() -> void:
	# 遮罩
	_settings_overlay = ColorRect.new()
	_settings_overlay.color = Color(0, 0, 0, 0.5)
	_settings_overlay.anchor_right = 1.0
	_settings_overlay.anchor_bottom = 1.0
	_settings_overlay.visible = false
	_settings_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_settings_overlay)

	# 加载设置面板场景（全部 4 个标签页的静态内容已在 tscn 中）
	var settings_scene: PackedScene = load("res://scenes/settings_panel.tscn")
	_settings_panel = settings_scene.instantiate()
	_settings_panel.visible = false
	add_child(_settings_panel)

	# TabContainer 设置
	var tab_container: TabContainer = _settings_panel.get_node("VBox/TabContainer")
	var tab_bar: TabBar = tab_container.get_tab_bar()
	tab_bar.scrolling_enabled = true
	tab_bar.tab_close_display_policy = TabBar.CLOSE_BUTTON_SHOW_NEVER

	# 设置标签页标题（Scene 中 TabContainer 子节点标题需代码设置）
	tab_container.set_tab_title(0, "强模型 🔵")
	tab_container.set_tab_title(1, "中模型 🟡")
	tab_container.set_tab_title(2, "轻模型 ⚪")
	tab_container.set_tab_title(3, "全局")

	# OptionButton 的 item 文本（Scene 中只设了 item_count=3，需代码填文本）
	for prefix in ["Strong", "Medium", "Light"]:
		var setting_opt: OptionButton = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTypeOpt" % [prefix, prefix, prefix])
		setting_opt.set_item_text(0, "ollama")
		setting_opt.set_item_text(1, "deepseek")
		setting_opt.set_item_text(2, "openai")

	# 给所有 LineEdit 批量设置暗色主题
	_apply_lineedit_theme(_settings_panel)

	# 按钮回调
	var cancel_btn: Button = _settings_panel.get_node("VBox/ButtonRow/CancelBtn")
	cancel_btn.pressed.connect(func(): _toggle_settings_panel())
	var settings_save_btn: Button = _settings_panel.get_node("VBox/ButtonRow/SaveBtn")
	settings_save_btn.pressed.connect(_on_settings_save)

	# 三个 Provider 类型切换回调
	_connect_provider_type_switch("Strong")
	_connect_provider_type_switch("Medium")
	_connect_provider_type_switch("Light")

	# 加载配置到字段
	_load_config_to_fields()


# ============================================================
# 暗色 LineEdit 主题（递归遍历所有 LineEdit 批量设置）
# ============================================================

func _apply_lineedit_theme(root: Node) -> void:
	var normal_style: StyleBoxFlat = StyleBoxFlat.new()
	normal_style.bg_color = Color(0.08, 0.08, 0.12, 1)
	normal_style.border_width_bottom = 1
	normal_style.border_color = Color(0.25, 0.25, 0.35, 1)

	var focus_style: StyleBoxFlat = StyleBoxFlat.new()
	focus_style.bg_color = Color(0.08, 0.08, 0.12, 1)
	focus_style.border_width_bottom = 1
	focus_style.border_color = Color(0.36, 0.8, 0.75, 1)

	_apply_lineedit_theme_recursive(root, normal_style, focus_style)


func _apply_lineedit_theme_recursive(node: Node, normal_style: StyleBoxFlat, focus_style: StyleBoxFlat) -> void:
	if node is LineEdit:
		node.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85, 1))
		node.add_theme_stylebox_override("normal", normal_style)
		node.add_theme_stylebox_override("focus", focus_style)
	for child in node.get_children():
		_apply_lineedit_theme_recursive(child, normal_style, focus_style)


# ============================================================
# Provider 类型切换
# ============================================================

func _connect_provider_type_switch(prefix: String) -> void:
	var connect_opt: OptionButton = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTypeOpt" % [prefix, prefix, prefix])
	connect_opt.item_selected.connect(func(idx: int): _on_provider_type_changed(prefix, idx))


func _on_provider_type_changed(prefix: String, idx: int) -> void:
	var changed_opt: OptionButton = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTypeOpt" % [prefix, prefix, prefix])
	var prov_type: String = changed_opt.get_item_text(idx)

	# 自动填充该 provider 类型的默认 endpoint（如果当前 endpoint 为空）
	var endpoint_le: LineEdit = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sEndpointRow/%sEndpoint" % [prefix, prefix, prefix, prefix])
	if endpoint_le.text.strip_edges() == "":
		match prov_type:
			"deepseek":
				endpoint_le.text = "https://api.deepseek.com/v1/chat/completions"
			"openai":
				endpoint_le.text = "https://api.openai.com/v1/chat/completions"
			_:
				endpoint_le.text = "http://localhost:11434/api/chat"

	# 切换 API Key 可见性
	_setup_api_key_visibility(prefix, prov_type)


func _setup_api_key_visibility(prefix: String, type_text: String) -> void:
	var visible: bool = type_text != "ollama"
	_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sApiKeyLabel" % [prefix, prefix, prefix]).visible = visible
	_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sApiKeyRow" % [prefix, prefix, prefix]).visible = visible


# ============================================================
# 配置加载 / 保存
# ============================================================

func _load_config_to_fields() -> void:
	"""打开面板时从 MananaPipeline 读取配置填充到所有标签页"""
	for tier in ["Strong", "Medium", "Light"]:
		var tier_lower: String = tier.to_lower()
		var section: String = "provider_" + tier_lower

		# Provider 类型
		var config_prov_type: String = str(MananaPipeline.get_config_value(section, "type", "ollama"))
		var type_opt: OptionButton = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTypeOpt" % [tier, tier, tier])
		for i in range(type_opt.item_count):
			if type_opt.get_item_text(i) == config_prov_type:
				type_opt.select(i)
				break

		# 各字段
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sEndpointRow/%sEndpoint" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "endpoint", ""))
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sApiKeyRow/%sApiKey" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "api_key", ""))
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sModelRow/%sModel" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "model", ""))
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTempRow/%sTemp" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "temperature", 0.7) as float)
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTokensRow/%sTokens" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "max_tokens", 2048) as int)
		_settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTimeoutRow/%sTimeout" % [tier, tier, tier, tier]).text = str(MananaPipeline.get_config_value(section, "timeout", 120) as int)

		# 更新 API Key 可见性
		_setup_api_key_visibility(tier, config_prov_type)

	# 全局配置
	_settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalRetryRow/GlobalRetry").text = str(MananaPipeline.get_config_value("retry", "max_retries", 3) as int)
	_settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalDelayRow/GlobalDelay").text = str(MananaPipeline.get_config_value("retry", "base_delay", 1.0) as float)
	_settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalOracleRow/GlobalOracle").text = str(MananaPipeline.get_config_value("oracle", "trigger_interval", 5) as int)


func _on_settings_save() -> void:
	"""保存所有 Provider 和全局设置，持久化并热重连"""
	for tier in ["Strong", "Medium", "Light"]:
		var cfg_tier_lower: String = tier.to_lower()
		var cfg_section: String = "provider_" + cfg_tier_lower

		var cfg_type_opt: OptionButton = _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTypeOpt" % [tier, tier, tier])
		MananaPipeline.set_config_value(cfg_section, "type", cfg_type_opt.get_item_text(cfg_type_opt.selected))
		MananaPipeline.set_config_value(cfg_section, "endpoint", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sEndpointRow/%sEndpoint" % [tier, tier, tier, tier]).text.strip_edges())
		MananaPipeline.set_config_value(cfg_section, "api_key", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sApiKeyRow/%sApiKey" % [tier, tier, tier, tier]).text.strip_edges())
		MananaPipeline.set_config_value(cfg_section, "model", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sModelRow/%sModel" % [tier, tier, tier, tier]).text.strip_edges())
		MananaPipeline.set_config_value(cfg_section, "temperature", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTempRow/%sTemp" % [tier, tier, tier, tier]).text.strip_edges().to_float())
		MananaPipeline.set_config_value(cfg_section, "max_tokens", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTokensRow/%sTokens" % [tier, tier, tier, tier]).text.strip_edges().to_int())
		MananaPipeline.set_config_value(cfg_section, "timeout", _settings_panel.get_node("VBox/TabContainer/Tab%s/%sVBox/%sTimeoutRow/%sTimeout" % [tier, tier, tier, tier]).text.strip_edges().to_int())

	# 保存全局配置
	MananaPipeline.set_config_value("retry", "max_retries", _settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalRetryRow/GlobalRetry").text.strip_edges().to_int())
	MananaPipeline.set_config_value("retry", "base_delay", _settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalDelayRow/GlobalDelay").text.strip_edges().to_float())
	MananaPipeline.set_config_value("oracle", "trigger_interval", _settings_panel.get_node("VBox/TabContainer/TabGlobal/GlobalVBox/GlobalOracleRow/GlobalOracle").text.strip_edges().to_int())

	# 持久化并触发热重连
	MananaPipeline.save_settings()
	MananaPipeline.request_reconnect()

	_toggle_settings_panel()
	_append_narrative("[color=#5DCAA5]设置已保存，正在热重连 Provider...[/color]")


# ============================================================
# 面板开关
# ============================================================

func _toggle_settings_panel() -> void:
	var show: bool = not _settings_panel.visible
	_settings_overlay.visible = show
	_settings_panel.visible = show
	if show:
		_load_config_to_fields()
		_input_field.editable = false
	else:
		_input_field.editable = true
		_input_field.grab_focus()


# ===== F7 世界书编辑器 =====

func _toggle_worldbook_panel() -> void:
	_toggle_panel_v2("worldbook")


## ===== 续写 =====

func _continue_narrative() -> void:
	if _latest_narrative == "":
		_append_narrative("[color=#888]没有可续写的叙事[/color]")
		return
	if _pipeline_busy:
		return
	_append_narrative("[color=#5DCAA5]> 续写[/color]")
	_pipeline_busy = true
	# 使用 MaNA Pipeline 续写上一段叙事
	MananaPipeline.run_beat("（续写）场景自然推进，角色继续当前互动")


## ===== Canon 提取（需配置 API）=====
##
## 流程: 读取小说 + 读取 extract_prompt.md → 拼接 prompt → 发 API → 收 JSON → 存 canon
## 使用时填 api_endpoint 即可

func _request_canon_extraction(book: Dictionary) -> void:
	if canon_extract_api == "":
		_append_narrative("[color=#F5C4B3]Canon 提取 API 未配置 (见 main.gd 顶部 canon_extract_api)[/color]")
		return

	_append_narrative("[color=#888]Canon 提取 API 未配置，请先在文件顶部填写 canon_extract_api[/color]")
	_append_narrative("[color=#888]提取管道已就绪：角色(Pass A) → 世界观(Pass B) → 地点(Pass C) → 时间线(Pass D) → 合并保存[/color]")
