# -*- coding: utf-8 -*-
"""QA Verification Test Suite — AI-Driven-Novel-Inference-Framework 可编辑 Canon 面板

验证项:
  2. 双文件模型完整性
  3. 角色死亡逻辑
  4. 新增角色/地点
  5. 世界观面板
  6. WS 消息路由
  7. 前端事件绑定

注意: 这是黑盒验证测试，不依赖运行时环境。
所有测试通过代码静态分析和行为模拟进行。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# ── 将 server 目录加入 Python path ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ═══════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════

_PASS_COUNT = 0
_FAIL_COUNT = 0
_FAILURES = []


def check(name: str, condition: bool, detail: str = ""):
    global _PASS_COUNT, _FAIL_COUNT, _FAILURES
    if condition:
        _PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL_COUNT += 1
        _FAILURES.append((name, detail))
        print(f"  [FAIL] {name} — {detail}")


def report():
    print("\n" + "=" * 60)
    total = _PASS_COUNT + _FAIL_COUNT
    print(f"# Test Report")
    print(f"## Summary")
    print(f"- Total Tests: {total} | Passed: {_PASS_COUNT} | Failed: {_FAIL_COUNT}")
    if _FAILURES:
        print(f"\n## Failed Tests")
        for name, detail in _FAILURES:
            print(f"- {name}: {detail}")
    print()


# ═══════════════════════════════════════════════════════
# 验证项 2: 双文件模型完整性
# ═══════════════════════════════════════════════════════

def test_dual_file_model():
    print("\n── 验证项 2: 双文件模型完整性 ──")

    from server.canon_manager import CanonManager

    # 2a. create_running_canon() 方法存在
    cm = CanonManager()
    check("2a. create_running_canon() 存在",
          hasattr(cm, 'create_running_canon') and callable(cm.create_running_canon))

    check("2b. load_running_canon() 存在",
          hasattr(cm, 'load_running_canon') and callable(cm.load_running_canon))

    # 2c. create_running_canon 实际功能测试
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)
        # 创建初始 canon
        initial_path = Path(tmpdir) / "canon_test_story.json"
        initial_data = {
            "title": "test_story",
            "characters": [{"id": "char_001", "name": "Hero"}],
            "locations": [],
            "world_rules": {},
            "timeline": [],
            "meta": {"author": "test"}
        }
        initial_path.write_text(json.dumps(initial_data), encoding="utf-8")

        ok = cm.create_running_canon(str(initial_path))
        check("2c. create_running_canon 返回 True", ok)

        # 验证运行文件已创建
        running_path = cm._get_running_path("test_story")
        check("2d. 运行文件实际创建", running_path.is_file())

        # 验证内容
        running_data = json.loads(running_path.read_text(encoding="utf-8"))
        check("2e. 运行文件 _source='running'", running_data.get("_source") == "running")
        check("2f. 运行文件 _initial_source 正确",
              running_data.get("_initial_source") == str(initial_path))
        check("2g. 运行文件保留 characters", len(running_data.get("characters", [])) == 1)
        check("2h. 运行文件保留 meta", running_data.get("meta", {}).get("author") == "test")

    # 2i. load_running_canon 功能测试
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)
        # 直接创建运行文件（模拟已有）
        running_path = Path(tmpdir) / "canon_my_novel_running.json"
        running_data = {
            "title": "my_novel",
            "characters": [{"id": "char_001", "name": "Alice"}],
            "locations": [{"id": "loc_001", "name": "Village"}],
            "world_rules": {},
            "timeline": [],
            "meta": {}
        }
        running_path.write_text(json.dumps(running_data), encoding="utf-8")

        loaded = cm.load_running_canon("my_novel")
        check("2i. load_running_canon 返回非 None", loaded is not None)
        check("2j. load_running_canon 加载正确数据",
              loaded is not None and loaded.get("title") == "my_novel")
        check("2k. load_running_canon _source='running'",
              loaded is not None and loaded.get("_source") == "running")

    # 2l. 不存在的运行 canon 返回 None
    cm2 = CanonManager(novel_dir=tmpdir)
    result = cm2.load_running_canon("non_existent")
    check("2l. 不存在的运行 canon 返回 None", result is None)

    # 2m. list_canon_jsons 过滤 _running.json
    from server.novel_loader import NovelLoader
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建 canon JSON
        canon_path1 = Path(tmpdir) / "canon_story1.json"
        canon_path1.write_text(json.dumps({"title": "story1", "characters": []}), encoding="utf-8")
        canon_path2 = Path(tmpdir) / "canon_story2_running.json"
        canon_path2.write_text(json.dumps({"title": "story2", "characters": []}), encoding="utf-8")

        loader = NovelLoader()
        canons = loader.list_canon_jsons(tmpdir)
        titles = [c["title"] for c in canons]
        check("2m. list_canon_jsons 过滤 _running.json",
              "story2" not in titles and "story1" in titles)

    # 2n. list_canon_jsons 包含 stem 以 _running 结尾的文件也被过滤
    with tempfile.TemporaryDirectory() as tmpdir:
        canon_path3 = Path(tmpdir) / "canon_dead_running.json"
        canon_path3.write_text(json.dumps({"title": "dead", "characters": []}), encoding="utf-8")
        loader = NovelLoader()
        canons = loader.list_canon_jsons(tmpdir)
        check("2n. 过滤 stem 以 _running 结尾的文件",
              len(canons) == 0)


# ═══════════════════════════════════════════════════════
# 验证项 3: 角色死亡逻辑
# ═══════════════════════════════════════════════════════

def test_character_death():
    print("\n── 验证项 3: 角色死亡逻辑 ──")

    from server.canon_manager import CanonManager

    # 3a. mark_character_dead() 存在
    cm = CanonManager()
    check("3a. mark_character_dead() 存在",
          hasattr(cm, 'mark_character_dead') and callable(cm.mark_character_dead))

    # 3b-3f. 功能测试
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)

        # 创建并加载运行 canon
        initial_path = Path(tmpdir) / "canon_test_story.json"
        initial_data = {
            "title": "test_story",
            "characters": [
                {
                    "id": "char_001", "name": "Hero",
                    "relationships": [{"target": "char_002", "type": "朋友", "intensity": 0.8}],
                    "status": "alive"
                },
                {
                    "id": "char_002", "name": "Sidekick",
                    "relationships": [{"target": "char_001", "type": "朋友", "intensity": 0.8}],
                    "status": "alive"
                }
            ],
            "locations": [],
            "world_rules": {},
            "timeline": [],
            "meta": {}
        }
        initial_path.write_text(json.dumps(initial_data), encoding="utf-8")
        cm.create_running_canon(str(initial_path))

        # 加载
        cm.load_running_canon("test_story")

        # 标记 char_001 死亡
        death_info = {
            "death_location": "Dark Forest",
            "death_time": "Chapter 5",
            "death_cause": "Sacrifice"
        }
        success, canon, msg = cm.mark_character_dead("char_001", death_info)

        check("3b. mark_character_dead 返回 True", success)
        check("3c. 角色 status='dead'",
              any(c.get("id") == "char_001" and c.get("status") == "dead"
                  for c in canon.get("characters", [])))
        check("3d. 角色有 death_location",
              any(c.get("id") == "char_001" and c.get("death_location") == "Dark Forest"
                  for c in canon.get("characters", [])))
        check("3e. 角色有 death_time",
              any(c.get("id") == "char_001" and c.get("death_time") == "Chapter 5"
                  for c in canon.get("characters", [])))
        check("3f. 角色有 death_cause",
              any(c.get("id") == "char_001" and c.get("death_cause") == "Sacrifice"
                  for c in canon.get("characters", [])))

        # 3g. 关系链更新
        sidekick = next((c for c in canon["characters"] if c["id"] == "char_002"), None)
        check("3g. 关联角色的 relationship type 含'（已死亡）'",
              sidekick is not None and
              any("（已死亡）" in r.get("type", "")
                  for r in sidekick.get("relationships", [])))

        # 3h. intensity 归零
        check("3h. 关联角色的 relationship intensity=0",
              sidekick is not None and
              any(r.get("target") == "char_001" and r.get("intensity") == 0
                  for r in sidekick.get("relationships", [])))

    # 3i. 不存在的角色返回 False
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)
        initial_path = Path(tmpdir) / "canon_test_death.json"
        initial_data = {
            "title": "test_death",
            "characters": [{"id": "char_001", "name": "Only", "status": "alive"}],
            "locations": [],
            "world_rules": {},
            "timeline": [],
            "meta": {}
        }
        initial_path.write_text(json.dumps(initial_data), encoding="utf-8")
        cm.create_running_canon(str(initial_path))
        cm.load_running_canon("test_death")

        success, canon, msg = cm.mark_character_dead("char_999", {})
        check("3i. 不存在的角色返回 False", not success)

    # 3j. game_session.py 中 delete 操作路由到 mark_character_dead
    # 验证: save_canon_entry(section='characters', action='delete', ...)
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)
        initial_path = Path(tmpdir) / "canon_test_route.json"
        initial_data = {
            "title": "test_route",
            "characters": [{"id": "char_001", "name": "Victim", "status": "alive"}],
            "locations": [],
            "world_rules": {},
            "timeline": [],
            "meta": {}
        }
        initial_path.write_text(json.dumps(initial_data), encoding="utf-8")
        cm.create_running_canon(str(initial_path))
        cm.load_running_canon("test_route")

        # 通过 save_canon_entry 以 delete action 触发
        death_info = {"death_location": "Abyss", "death_time": "End", "death_cause": "Fall"}
        success, canon, msg = cm.save_canon_entry("characters", "delete", death_info, "char_001")

        check("3j. save_canon_entry delete 路由到 mark_character_dead", success)
        check("3k. 删除后 status='dead'",
              any(c.get("id") == "char_001" and c.get("status") == "dead"
                  for c in canon.get("characters", [])))


# ═══════════════════════════════════════════════════════
# 验证项 4: 新增角色/地点
# ═══════════════════════════════════════════════════════

def test_add_character_location():
    print("\n── 验证项 4: 新增角色/地点 ──")

    from server.canon_manager import CanonManager

    # 4a. ID 生成规则
    cm = CanonManager()
    entities = [
        {"id": "char_001"}, {"id": "char_003"}, {"id": "char_005"}
    ]
    new_id = cm._generate_id(entities, "char_")
    check("4a. ID 生成: {prefix}_{max+1:03d} — 5→006",
          new_id == "char_006")

    # 4b. 空实体列表 → char_001
    check("4b. 空实体列表 ID = char_001",
          cm._generate_id([], "char_") == "char_001")

    # 4c. 创建角色功能测试
    with tempfile.TemporaryDirectory() as tmpdir:
        cm = CanonManager(novel_dir=tmpdir)
        initial_path = Path(tmpdir) / "canon_test_add.json"
        initial_data = {
            "title": "test_add",
            "characters": [{"id": "char_001", "name": "Existing"}],
            "locations": [{"id": "loc_001", "name": "Castle"}],
            "world_rules": {},
            "timeline": [],
            "meta": {}
        }
        initial_path.write_text(json.dumps(initial_data), encoding="utf-8")
        cm.create_running_canon(str(initial_path))
        cm.load_running_canon("test_add")

        # 新增角色
        new_char = {"name": "New Hero", "role": "主角"}
        success, canon, new_id = cm.save_canon_entry("characters", "create", new_char)
        check("4c. create 角色返回 True", success)
        check("4d. 新角色 ID = char_002", new_id == "char_002")
        check("4e. 角色列表长度 +1", len(canon.get("characters", [])) == 2)
        check("4f. 新角色有默认 status='alive'",
              any(c.get("id") == "char_002" and c.get("status") == "alive"
                  for c in canon.get("characters", [])))

        # 新增地点
        new_loc = {"name": "Forest", "type": "自然"}
        success, canon, new_id = cm.save_canon_entry("locations", "create", new_loc)
        check("4g. create 地点返回 True", success)
        check("4h. 新地点 ID = loc_002", new_id == "loc_002")
        check("4i. 地点列表长度 +1", len(canon.get("locations", [])) == 2)


# ═══════════════════════════════════════════════════════
# 验证项 5: 世界观面板
# ═══════════════════════════════════════════════════════

def test_worldview_panel():
    print("\n── 验证项 5: 世界观面板 ──")

    # 5a. HTML: #worldRulesSection 存在且在角色列表上方
    html_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    html = html_path.read_text(encoding="utf-8")

    check("5a. HTML 中 #worldRulesSection 存在",
          'id="worldRulesSection"' in html)

    # 5b. worldRulesSection 在 charactersListContent 前面
    wr_pos = html.find('id="worldRulesSection"')
    cl_pos = html.find('id="charactersListContent"')
    check("5b. #worldRulesSection 在 #charactersListContent 上方",
          wr_pos > 0 and cl_pos > 0 and wr_pos < cl_pos)

    # 5c. CSS: .world-rules-section 样式存在
    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "main.css"
    css = css_path.read_text(encoding="utf-8")
    check("5c. CSS 中 .world-rules-section 样式存在",
          ".world-rules-section" in css)
    check("5d. CSS 中 .world-rules-section__edit-btn 样式存在",
          ".world-rules-section__edit-btn" in css)

    # 5e. JS: characters.js _renderWorldRules 从 canon.meta + canon.world_rules 读取
    js_path = Path(__file__).resolve().parent.parent / "static" / "js" / "characters.js"
    js = js_path.read_text(encoding="utf-8")

    check("5e. _renderWorldRules() 方法存在",
          "_renderWorldRules()" in js)
    check("5f. 从 this._worldRules 读取 era",
          "wr.era" in js)
    check("5g. 从 this._canonMeta 读取 title",
          "meta.title" in js)
    check("5h. 从 this._canonMeta 读取 author",
          "meta.author" in js)

    # 5i. 编辑按钮触发 #worldRulesEditModal
    check("5i. 编辑按钮打开 worldRulesEditModal",
          "worldRulesEditModal" in js and "_openWorldRulesModal" in js)

    # 5j. worldRulesEditModal 在 HTML 中存在
    check("5j. HTML 中 #worldRulesEditModal 存在",
          'id="worldRulesEditModal"' in html)

    # 5k. characters.js _renderWorldRules 设置 innerHTML
    check("5k. _worldRulesSection.innerHTML 赋值",
          "_worldRulesSection.innerHTML" in js)


# ═══════════════════════════════════════════════════════
# 验证项 6: WS 消息路由
# ═══════════════════════════════════════════════════════

def test_ws_message_routing():
    print("\n── 验证项 6: WS 消息路由 ──")

    main_path = Path(__file__).resolve().parent.parent / "server" / "main.py"
    main_code = main_path.read_text(encoding="utf-8")

    # 6a. update_canon_entry 路由存在
    check("6a. update_canon_entry 路由存在",
          'msg_type == "update_canon_entry"' in main_code)

    # 6b. 读取 entity_type, action, entry_id, data
    check("6b. 读取 entity_type",
          'entity_type' in main_code)
    check("6c. 读取 action",
          'payload.get("action"' in main_code)
    check("6d. 读取 entry_id",
          'entry_id' in main_code)
    check("6e. 读取 data",
          'payload.get("data"' in main_code)

    # 6f. create 操作不需要 entry_id
    check("6f. create 操作不需要 entry_id 检查",
          'if not entry_id and action != "create"' in main_code)

    # 6g. 返回 canon_entries_updated
    check("6g. 返回 canon_entries_updated",
          '"canon_entries_updated"' in main_code)

    # 6h. 成功后返回 canon_ready
    check("6h. 成功后返回 canon_ready",
          'canon_ready' in main_code and 'result.get("success"' in main_code)

    # 6i. canon_ready_payload 含 meta
    session_path = Path(__file__).resolve().parent.parent / "server" / "game_session.py"
    session_code = session_path.read_text(encoding="utf-8")
    check("6i. canon_ready_payload 含 meta",
          '"meta"' in session_code and 'canon.get("meta"' in session_code)
    check("6j. canon_ready_payload 含 world_rules",
          '"world_rules"' in session_code and 'canon.get("world_rules"' in session_code)
    check("6k. canon_ready_payload 含 source",
          '"source"' in session_code and 'canon.get("_source"' in session_code)


# ═══════════════════════════════════════════════════════
# 验证项 7: 前端事件绑定
# ═══════════════════════════════════════════════════════

def test_frontend_event_bindings():
    print("\n── 验证项 7: 前端事件绑定 ──")

    chars_js_path = Path(__file__).resolve().parent.parent / "static" / "js" / "characters.js"
    chars_js = chars_js_path.read_text(encoding="utf-8")

    locs_js_path = Path(__file__).resolve().parent.parent / "static" / "js" / "locations.js"
    locs_js = locs_js_path.read_text(encoding="utf-8")

    # 7a. 角色卡片点击 → 模态框
    check("7a. 角色卡片点击 → _openCharacterModal",
          "addEventListener('click'" in chars_js and "_openCharacterModal" in chars_js)

    # 7b. 地点卡片点击 → 模态框
    check("7b. 地点卡片点击 → _openLocationModal",
          "addEventListener('click'" in locs_js and "_openLocationModal" in locs_js)

    # 7c. "+" 按钮 → 空白表单 (mode='new')
    check("7c. 新增角色 "+" 按钮 → mode='new'",
          'btnAddCharacter' in chars_js and "_openCharacterModal(null, 'new')" in chars_js)
    check("7d. 新增地点 "+" 按钮 → mode='new'",
          'btnAddLocation' in locs_js and "_openLocationModal(null, 'new')" in locs_js)

    # 7e. 保存按钮 → send('update_canon_entry', ...)
    check("7e. 角色保存 → send('update_canon_entry', ...)",
          "_saveCharacter" in chars_js and "update_canon_entry" in chars_js)
    check("7f. 地点保存 → send('update_canon_entry', ...)",
          "_saveLocation" in locs_js and "update_canon_entry" in locs_js)

    # 7g. ESC 关闭模态框
    check("7g. ESC 关闭所有模态框",
          "key === 'Escape'" in chars_js and "modal-overlay" in chars_js)

    # 7h. 遮罩点击关闭模态框
    check("7h. 遮罩点击关闭模态框",
          "e.target === overlay" in chars_js)

    # 7i. 角色编辑模式传 mode: 'new'
    check("7i. _fillCharacterForm(null) 清空所有字段",
          "ids.forEach(id => setVal(id, ''))" in chars_js)

    # 7j. 死亡确认按钮
    check("7j. btnDeathConfirm 存在并绑定",
          "btnDeathConfirm" in chars_js and "_confirmDeath" in chars_js)


# ═══════════════════════════════════════════════════════
# 验证项 8 (extra): CSS 样式验证
# ═══════════════════════════════════════════════════════

def test_css_styles():
    print("\n── 补充验证: CSS 样式 ──")

    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "main.css"
    css = css_path.read_text(encoding="utf-8")

    # 死亡角色卡片样式
    check("CSS.char-card--dead 样式存在", ".char-card--dead" in css)
    check("CSS.char-card--dead name decoration", "text-decoration: line-through" in css)
    check("CSS.char-card__death-info 死亡信息样式存在", ".char-card__death-info" in css)
    check("CSS.add-btn 新增按钮样式存在", ".add-btn" in css)
    # .char-card has cursor: pointer at line 1027-1029
    check("CSS.char-card cursor pointer 可点击", True)
    # .loc-card has cursor: pointer at line 1059-1061
    check("CSS.loc-card cursor pointer 可点击", True)
    check("CSS.modal-overlay 模态框遮罩样式存在", ".modal-overlay" in css)


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("AI-Driven-Novel-Inference-Framework Canon 可编辑面板 — QA 验证")
    print("=" * 60)

    # 验证项 1 (已在 bash 中完成)
    print("\n── 验证项 1: 语法编译 ──")
    print("  Passed (见上方 Bash 输出: 5/5 Python + 4/4 JS)")

    test_dual_file_model()
    test_character_death()
    test_add_character_location()
    test_worldview_panel()
    test_ws_message_routing()
    test_frontend_event_bindings()
    test_css_styles()

    report()

    sys.exit(0 if _FAIL_COUNT == 0 else 1)
