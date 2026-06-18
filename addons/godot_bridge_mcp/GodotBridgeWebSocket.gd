@tool
extends EditorPlugin

const SETTINGS_PATH = "mcp_bridge/port"
const DEFAULT_PORT = 8080

var tcp_server: TCPServer
var peers: Dictionary = {}
var _port: int = DEFAULT_PORT

# UI 元素
var panel: Control
var status_label: Label
var port_input: LineEdit
var start_button: Button
var stop_button: Button
var save_button: Button
var settings_initialized: bool = false

func _enter_tree():
	print("MCP Bridge: _enter_tree() called")
	_load_settings()
	print("MCP Bridge: settings loaded, port=", _port)
	_create_ui()
	print("MCP Bridge: UI created")
	_start_server()
	set_process(true)
	print("MCP Bridge: _enter_tree() complete")

func _exit_tree():
	set_process(false)
	_stop_server()
	_remove_ui()
	print("MCP Bridge: Plugin disabled")

func _load_settings():
	if not ProjectSettings.has_setting(SETTINGS_PATH):
		ProjectSettings.set_setting(SETTINGS_PATH, DEFAULT_PORT)
		var info = {
			"name": SETTINGS_PATH,
			"type": TYPE_INT,
			"hint": PROPERTY_HINT_RANGE,
			"hint_string": "1024,65535"
		}
		ProjectSettings.add_property_info(info)
		ProjectSettings.set_initial_value(SETTINGS_PATH, DEFAULT_PORT)
	_port = ProjectSettings.get_setting(SETTINGS_PATH)
	settings_initialized = true

func _create_ui():
	# 创建底部面板容器
	panel = VBoxContainer.new()
	panel.name = "MCP Bridge"
	
	# 标题
	var title = Label.new()
	title.text = "Godot MCP Bridge"
	title.add_theme_font_size_override("font_size", 16)
	panel.add_child(title)
	
	# 分隔线
	panel.add_child(HSeparator.new())
	
	# 状态行
	var status_row = HBoxContainer.new()
	status_label = Label.new()
	status_label.text = "状态: 未启动"
	status_row.add_child(status_label)
	panel.add_child(status_row)
	
	# 端口设置行
	var port_row = HBoxContainer.new()
	var port_label = Label.new()
	port_label.text = "端口: "
	port_row.add_child(port_label)
	
	port_input = LineEdit.new()
	port_input.text = str(_port)
	port_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	port_row.add_child(port_input)
	panel.add_child(port_row)
	
	# 按钮行
	var button_row = HBoxContainer.new()
	
	start_button = Button.new()
	start_button.text = "启动服务器"
	start_button.pressed.connect(_on_start_pressed)
	button_row.add_child(start_button)
	
	stop_button = Button.new()
	stop_button.text = "停止服务器"
	stop_button.disabled = true
	stop_button.pressed.connect(_on_stop_pressed)
	button_row.add_child(stop_button)
	
	save_button = Button.new()
	save_button.text = "保存端口并重启"
	save_button.pressed.connect(_on_save_pressed)
	button_row.add_child(save_button)
	
	panel.add_child(button_row)
	
	# 说明文本
	var hint = Label.new()
	hint.text = "修改端口后点击保存端口并重启生效。需确保 Godot 的 WebSocket 服务器正在运行，OpenCode 才能连接。"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	panel.add_child(hint)
	
	# 将面板添加到编辑器底部
	add_control_to_bottom_panel(panel, "MCP Bridge")
	
	_update_ui_state()

func _remove_ui():
	if panel:
		remove_control_from_bottom_panel(panel)
		panel.queue_free()

func _update_ui_state():
	var running = tcp_server != null and tcp_server.is_listening()
	status_label.text = "状态: " + ("运行中 (端口 %d)" % _port if running else "已停止")
	start_button.disabled = running
	stop_button.disabled = not running
	port_input.editable = not running

func _start_server():
	print("MCP Bridge: _start_server() called, port=", _port)
	if tcp_server:
		_stop_server()
	
	tcp_server = TCPServer.new()
	var err = tcp_server.listen(_port)
	print("MCP Bridge: tcp_server.listen() returned ", err)
	if err != OK:
		push_error("MCP Bridge: 无法在端口 %d 启动服务器, error=%d" % [_port, err])
		status_label.text = "状态: 启动失败"
	else:
		print("MCP Bridge: WebSocket 服务器已在端口 %d 启动" % _port)
		_update_ui_state()

func _stop_server():
	# 关闭所有客户端连接
	for conn in peers.keys():
		var peer = peers[conn]
		if peer:
			peer.close()
	peers.clear()
	
	if tcp_server:
		tcp_server.stop()
		tcp_server = null
		print("MCP Bridge: WebSocket 服务器已停止")
	_update_ui_state()

func _on_start_pressed():
	_start_server()

func _on_stop_pressed():
	_stop_server()

func _on_save_pressed():
	var new_port = int(port_input.text)
	if new_port < 1024 or new_port > 65535:
		push_error("端口号必须在 1024-65535 之间")
		return
	
	_port = new_port
	ProjectSettings.set_setting(SETTINGS_PATH, _port)
	ProjectSettings.save()
	print("MCP Bridge: 端口配置已保存为 ", _port)
	
	# 重启服务器以应用新端口
	if tcp_server:
		_stop_server()
	_start_server()

# ---------- 以下为 WebSocket 通信处理，与原始代码相同 ----------

func _process(delta):
	if not tcp_server or not tcp_server.is_listening():
		return
	
	while tcp_server.is_connection_available():
		var connection = tcp_server.take_connection()
		var peer = WebSocketPeer.new()
		var accept_err = peer.accept_stream(connection)
		if accept_err != OK:
			print("MCP Bridge: accept_stream error " + str(accept_err))
			continue
		
		peers[connection] = peer
		print("MCP Bridge: 新连接已添加")
	
	var to_remove = []
	for conn in peers.keys():
		var peer = peers[conn]
		peer.poll()
		var state = peer.get_ready_state()
		
		if state == WebSocketPeer.STATE_OPEN:
			while peer.get_available_packet_count() > 0:
				var packet = peer.get_packet()
				if peer.was_string_packet():
					var msg = packet.get_string_from_utf8()
					print("MCP Bridge: RX ", msg)
					_handle_message(msg, peer)
		elif state == WebSocketPeer.STATE_CLOSED:
			var code = peer.get_close_code()
			var reason = peer.get_close_reason()
			print("MCP Bridge: 连接关闭 code=", code, " reason=", reason)
			to_remove.append(conn)
	
	for conn in to_remove:
		peers.erase(conn)

func _handle_message(data: String, peer: WebSocketPeer):
	var json = JSON.new()
	if json.parse(data) != OK:
		_respond(peer, 0, null, "Invalid JSON")
		return
	
	var payload = json.get_data()
	if typeof(payload) != TYPE_DICTIONARY:
		_respond(peer, 0, null, "Expected object")
		return
	
	if not payload.has("id") or not payload.has("method"):
		_respond(peer, 0, null, "Missing id or method")
		return
	
	var req_id = payload["id"]
	var method = payload["method"]
	var params = payload.get("params", {})
	
	var result = null
	var err_msg = ""
	
	match method:
		"get_scene_tree":
			result = _get_scene_tree()
		"get_script_info":
			result = _get_script_info(params)
		"add_node":
			result = _add_node(params)
		"get_node_properties":
			result = _get_node_properties(params)
		"set_node_property":
			result = _set_node_property(params)
		"execute_script":
			result = _execute_script(params)
		"get_selected_nodes":
			result = _get_selected_nodes()
		"get_editor_info":
			result = _get_editor_info()
		"list_assets":
			result = _list_assets(params)
		"list_node_types":
			result = _list_node_types()
		"create_scene":
			result = _create_scene(params)
		"create_scene_from_script":
			result = _create_scene_from_script(params)
		"save_scene":
			result = _save_scene(params)
		"attach_script":
			result = _attach_script(params)
		"delete_node":
			result = _delete_node(params)
		_:
			err_msg = "Unknown method: " + str(method)
	
	_respond(peer, req_id, result, err_msg)

func _respond(peer: WebSocketPeer, req_id, result, err_msg: String):
	var response = {"jsonrpc": "2.0", "id": req_id}
	if err_msg != "":
		response["error"] = {"code": -32600, "message": err_msg}
	else:
		response["result"] = result if result != null else {}
	
	var json_str = JSON.stringify(response)
	peer.send_text(json_str)
	print("MCP Bridge: Sent ", json_str)

# ---------- 业务逻辑函数，与原代码保持一致 ----------

func _get_root():
	return get_editor_interface().get_edited_scene_root()

func _build_tree(node):
	var root = _get_root()
	var path_str = ""
	if root:
		path_str = root.get_path_to(node)
	
	var data = {
		"name": node.name,
		"type": node.get_class(),
		"path": path_str,
		"children": []
	}
	
	for child in node.get_children():
		data["children"].append(_build_tree(child))
	
	return data

func _get_scene_tree():
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	return {"scene_tree": _build_tree(root)}

func _add_node(params):
	var node_type = params.get("type", "")
	if node_type == "":
		return {"error": "Missing type"}
	
	var node_name = params.get("name", node_type)
	var parent_path = params.get("parent_path", "")
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	var parent_node = null
	var sel = get_editor_interface().get_selection()
	var selected = sel.get_selected_nodes()
	
	if parent_path != "":
		parent_node = root.get_node(parent_path)
	elif selected.size() > 0:
		parent_node = selected[0]
	else:
		return {"error": "No parent specified"}
	
	if not parent_node:
		return {"error": "Parent not found"}
	
	var new_node = ClassDB.instantiate(node_type)
	if not new_node:
		return {"error": "Cannot create " + node_type}
	
	new_node.name = node_name
	parent_node.add_child(new_node)
	new_node.owner = root
	
	get_editor_interface().mark_scene_as_unsaved()
	
	return {
		"success": true,
		"node": {
			"name": new_node.name,
			"type": new_node.get_class(),
			"path": root.get_path_to(new_node)
		}
	}

func _get_node_properties(params):
	var node_path = params.get("path", "")
	if node_path == "":
		return {"error": "Missing path"}
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	var target = root.get_node(node_path)
	if not target:
		return {"error": "Node not found"}
	
	var props = {}
	for p in target.get_property_list():
		var pname = p["name"]
		if not pname.begins_with("_"):
			if p["usage"] & PROPERTY_USAGE_STORAGE:
				props[pname] = target.get(pname)
	
	return {"node_path": node_path, "properties": props}

func _set_node_property(params):
	var node_path = params.get("path", "")
	var prop_name = params.get("property", "")
	var value = params.get("value")
	
	if node_path == "" or prop_name == "":
		return {"error": "Missing path or property"}
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	var target = root.get_node(node_path)
	if not target:
		return {"error": "Node not found"}
	
	target.set(prop_name, value)
	get_editor_interface().mark_scene_as_unsaved()
	
	return {"success": true, "node_path": node_path, "property": prop_name}

func _execute_script(params):
	var code = params.get("code", "")
	if code == "":
		return {"error": "Missing code"}
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	var script = GDScript.new()
	script.source_code = "extends Node\nfunc _run():\n\t" + code
	script.reload()
	
	var temp = Node.new()
	temp.set_script(script)
	root.add_child(temp)
	
	var result = null
	if temp.has_method("_run"):
		result = temp.call("_run")
	
	root.remove_child(temp)
	temp.queue_free()
	
	return {"success": true, "result": result if result != null else "done"}

func _get_selected_nodes():
	var sel = get_editor_interface().get_selection()
	var nodes = sel.get_selected_nodes()
	var root = _get_root()
	var result = []
	
	for n in nodes:
		var path_str = ""
		if root:
			path_str = root.get_path_to(n)
		result.append({
			"name": n.name,
			"type": n.get_class(),
			"path": path_str
		})
	
	return {"selected_nodes": result}

func _get_editor_info():
	var root = _get_root()
	var info = Engine.get_version_info()
	return {
		"version": info.get("string", "unknown"),
		"system": OS.get_name(),
		"has_scene": root != null,
		"scene_path": root.scene_file_path if root else ""
	}

func _list_node_types():
	var classes = []
	for cname in ClassDB.get_class_list():
		if cname in ["Object", "Node", "Resource", "RefCounted", "Script", "GDScript", "VisualScript"]:
			continue
		if ClassDB.can_instantiate(cname):
			classes.append(cname)
	classes.sort()
	return {"node_types": classes}

func _create_scene(params):
	var scene_name = params.get("scene_name", "")
	if scene_name == "":
		return {"error": "Missing scene_name"}
	
	var root_type = params.get("root_type", "Node2D")
	var directory = params.get("directory", "res://")
	var open_after_create = params.get("open_after_create", false)
	var overwrite = params.get("overwrite", false)
	
	if not directory.ends_with("/"):
		directory += "/"
	
	var path = directory + scene_name + ".tscn"
	
	if ResourceLoader.exists(path) and not overwrite:
		return {"error": "Scene already exists, use overwrite=true"}
	
	DirAccess.make_dir_recursive_absolute(directory)
	
	if not ClassDB.can_instantiate(root_type):
		return {"error": "Cannot instantiate type: " + root_type}
	
	var root = ClassDB.instantiate(root_type)
	root.name = scene_name
	
	var packed = PackedScene.new()
	var pack_err = packed.pack(root)
	if pack_err != OK:
		root.queue_free()
		return {"error": "Failed to pack scene (error code: " + str(pack_err) + ")"}
	
	var save_err = ResourceSaver.save(packed, path)
	root.queue_free()
	
	if save_err != OK:
		return {"error": "Failed to save scene to " + path + " (error code: " + str(save_err) + ")"}
	
	if open_after_create:
		get_editor_interface().open_scene_from_path(path)
	
	return {"success": true, "scene_path": path}

func _save_scene(params):
	var path = params.get("path", "")
	
	if path == "":
		get_editor_interface().save_scene()
		var root = _get_root()
		if not root:
			return {"error": "No open scene to save"}
		return {"success": true, "scene_path": root.scene_file_path}
	else:
		get_editor_interface().save_scene_as(path)
		var root = _get_root()
		if not root:
			return {"error": "No open scene to save"}
		return {"success": true, "scene_path": path}

func _attach_script(params):
	var node_path = params.get("node_path", "")
	var script_path = params.get("script_path", "")
	
	if node_path == "" or script_path == "":
		return {"error": "Missing node_path or script_path"}
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	var node = root.get_node(node_path)
	if not node:
		return {"error": "Node not found"}
	
	if not ResourceLoader.exists(script_path):
		return {"error": "Script not found: " + script_path}
	
	var script = ResourceLoader.load(script_path)
	if not script:
		return {"error": "Failed to load script: " + script_path}
	
	node.set_script(script)
	get_editor_interface().mark_scene_as_unsaved()
	
	return {"success": true, "node_path": node_path, "script_path": script_path}

func _delete_node(params):
	var node_path = params.get("node_path", "")
	
	if node_path == "":
		return {"error": "Missing node_path"}
	
	var root = _get_root()
	if not root:
		return {"error": "No active scene"}
	
	if node_path == "." or _node_is_root(root, node_path):
		return {"error": "Cannot delete root node"}
	
	var node = root.get_node(node_path)
	if not node:
		return {"error": "Node not found"}
	
	node.queue_free()
	get_editor_interface().mark_scene_as_unsaved()
	
	return {"success": true, "deleted_node": node_path}

func _node_is_root(root, node_path):
	if node_path == ".":
		return true
	var node = root.get_node(node_path)
	return node == root

func _create_scene_from_script(params):
	var script_path = params.get("script_path", "")
	if script_path == "":
		return {"error": "Missing script_path"}
	
	var script = ResourceLoader.load(script_path)
	if script == null or not script is GDScript:
		return {"error": "Not a valid GDScript"}
	
	var base_type = script.get_instance_base_type()
	if base_type == "":
		return {"error": "Cannot determine base type from script"}
	
	var directory = params.get("directory", "")
	if directory == "":
		directory = script_path.get_base_dir()
	
	var scene_name = script_path.get_file().get_basename()
	var path = directory + "/" + scene_name + ".tscn"
	
	if not ClassDB.can_instantiate(base_type):
		return {"error": "Cannot instantiate type: " + base_type}
	
	var root = ClassDB.instantiate(base_type)
	root.name = scene_name
	root.set_script(script)
	
	var packed = PackedScene.new()
	var pack_err = packed.pack(root)
	if pack_err != OK:
		root.queue_free()
		return {"error": "Failed to pack scene (error code: " + str(pack_err) + ")"}
	
	DirAccess.make_dir_recursive_absolute(directory)
	
	var save_err = ResourceSaver.save(packed, path)
	root.queue_free()
	
	if save_err != OK:
		return {"error": "Failed to save scene to " + path + " (error code: " + str(save_err) + ")"}
	
	return {"success": true, "scene_path": path, "root_type": base_type}

func _get_script_info(params):
	var script_path = params.get("script_path", "")
	if script_path == "":
		return {"error": "Missing script_path"}
	
	var script = ResourceLoader.load(script_path)
	if script == null or not script is GDScript:
		return {"error": "Not a valid GDScript"}
	
	var info = {
		"extends": script.get_instance_base_type(),
		"class_name": script.get_global_name() if script.get_global_name() else "",
		"methods": [],
		"signals": [],
		"exports": [],
		"path": script_path
	}
	
	for method in script.get_script_method_list():
		info["methods"].append({"name": method["name"]})
	
	for signal_info in script.get_script_signal_list():
		info["signals"].append({"name": signal_info["name"]})
	
	for prop in script.get_script_property_list():
		if prop["usage"] & PROPERTY_USAGE_EDITOR:
			info["exports"].append({
				"name": prop["name"],
				"type": prop.get("hint_string", ""),
				"default": prop.get("default_value", null)
			})
	
	return info

func _list_assets(params):
	var asset_type = params.get("asset_type", "all")
	var directory = params.get("directory", "res://")
	
	var scenes = []
	var scripts = []
	
	var efs = EditorInterface.get_resource_filesystem()
	var root_dir = efs.get_filesystem()
	
	_list_assets_recursive(root_dir, directory, asset_type, scenes, scripts, efs)
	
	return {
		"scenes": scenes,
		"scripts": scripts,
		"total": scenes.size() + scripts.size()
	}

func _list_assets_recursive(fs_dir, target_dir: String, asset_type: String, scenes: Array, scripts: Array, efs):
	for i in range(fs_dir.get_file_count()):
		var file_path = fs_dir.get_file_path(i)
		var file_type = efs.get_file_type(file_path)
		
		if not file_path.begins_with(target_dir):
			continue
		
		match asset_type:
			"scene":
				if file_type == "PackedScene":
					scenes.append({"name": file_path.get_file(), "path": file_path})
			"script":
				if file_type == "GDScript":
					scripts.append({"name": file_path.get_file(), "path": file_path})
			"all":
				if file_type == "PackedScene":
					scenes.append({"name": file_path.get_file(), "path": file_path})
				elif file_type == "GDScript":
					scripts.append({"name": file_path.get_file(), "path": file_path})
	
	for i in range(fs_dir.get_subdir_count()):
		var subdir = fs_dir.get_subdir(i)
		_list_assets_recursive(subdir, target_dir, asset_type, scenes, scripts, efs)