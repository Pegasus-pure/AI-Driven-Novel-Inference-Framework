#!/usr/bin/env python3
"""
验证测试：ID 解析 + 叙事审计逻辑

模拟 GameSession._replace_ids_with_names() 和前端 characters.js 中的
ID↔名称转换逻辑，验证：
  1. 长 ID 优先替换策略
  2. 角色和地点替换顺序
  3. 边界情况（空文本、无匹配、无 locations 数据）
"""

# ── 模拟后端 _replace_ids_with_names ──

def replace_ids_with_names(text: str, canon: dict) -> str:
    """模拟 GameSession._replace_ids_with_names()"""
    if not text:
        return text

    result = text

    # 长 ID 优先替换
    chars = sorted(canon.get("characters", []) or [],
                   key=lambda c: len(c.get("id", "")), reverse=True)
    for c in chars:
        cid = c.get("id", "")
        cname = c.get("name", "")
        if cid and cname:
            result = result.replace(cid, cname)

    locs = sorted(canon.get("locations", []) or [],
                  key=lambda l: len(l.get("id", "")), reverse=True)
    for loc in locs:
        lid = loc.get("id", "")
        lname = loc.get("name", "")
        if lid and lname:
            result = result.replace(lid, lname)

    return result


# ── 模拟前端 characters.js 逻辑 ──

def frontend_card_display(starting_location: str, locations: list) -> str:
    """模拟角色卡片显示逻辑"""
    if not starting_location:
        return ""  # 不显示"起始地点"行
    loc_name = starting_location
    if locations:
        found = next((l for l in locations if l["id"] == starting_location), None)
        if found:
            loc_name = found["name"]
    return f"起始地点: {loc_name}"


def frontend_form_fill(starting_location: str, locations: list) -> str:
    """模拟编辑表单填充（ID→名称）"""
    if not starting_location:
        return ""
    if locations:
        found = next((l for l in locations if l["id"] == starting_location), None)
        if found:
            return found["name"]
    return starting_location


def frontend_form_collect(raw_name: str, locations: list) -> str:
    """模拟编辑表单收集（名称→ID）"""
    if not raw_name:
        return ""
    if locations:
        found = next((l for l in locations if l["name"] == raw_name), None)
        if found:
            return found["id"]
    return raw_name


# ═══════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════

def test_scenario_A():
    """场景 A：角色有 starting_location="loc_01"，地点列表有 {id:"loc_01", name:"王城"}"""
    locations = [{"id": "loc_01", "name": "王城"}]

    # 前端卡片显示
    card = frontend_card_display("loc_01", locations)
    assert card == "起始地点: 王城", f"预期='起始地点: 王城', 实际='{card}'"

    # 编辑表单填充
    form_val = frontend_form_fill("loc_01", locations)
    assert form_val == "王城", f"预期='王城', 实际='{form_val}'"

    # 表单收集反查
    collected_id = frontend_form_collect("王城", locations)
    assert collected_id == "loc_01", f"预期='loc_01', 实际='{collected_id}'"

    print("[OK] 场景 A 通过")


def test_scenario_B():
    """场景 B：角色没有 starting_location"""
    locations = [{"id": "loc_01", "name": "王城"}]

    # 卡片显示
    card = frontend_card_display("", locations)
    assert card == "", f"预期=''(空), 实际='{card}'"

    # 编辑表单填充
    form_val = frontend_form_fill("", locations)
    assert form_val == "", f"预期=''(空), 实际='{form_val}'"

    # 表单收集
    collected_id = frontend_form_collect("", locations)
    assert collected_id == "", f"预期=''(空), 实际='{collected_id}'"

    print("[OK] 场景 B 通过")


def test_scenario_C():
    """场景 C：叙事文本包含 'char_001 来到了 loc_01'"""
    canon = {
        "characters": [
            {"id": "char_001", "name": "艾琳·风行者"},
            {"id": "char_002", "name": "凯恩"},
        ],
        "locations": [
            {"id": "loc_01", "name": "王城"},
            {"id": "loc_02", "name": "翡翠森林"},
        ]
    }

    text = "char_001 来到了 loc_01。char_002 在 loc_02 守候。"
    result = replace_ids_with_names(text, canon)
    expected = "艾琳·风行者 来到了 王城。凯恩 在 翡翠森林 守候。"
    assert result == expected, f"\n预期: {expected}\n实际: {result}"
    print("[OK] 场景 C 通过")


def test_long_id_priority():
    """长 ID 优先替换 — char_001 不会被 char_00 误匹配"""
    canon = {
        "characters": [
            {"id": "char_001", "name": "艾琳"},
            {"id": "char_00", "name": "路人甲"},
        ],
        "locations": []
    }

    text = "char_001 遇见了 char_00。"
    result = replace_ids_with_names(text, canon)
    expected = "艾琳 遇见了 路人甲。"
    assert result == expected, f"\n预期: {expected}\n实际: {result}"
    print("[OK] 长 ID 优先测试通过")


def test_empty_text():
    """空文本保护"""
    canon = {"characters": [], "locations": []}
    assert replace_ids_with_names("", canon) == ""
    assert replace_ids_with_names(None, canon) is None
    print("[OK] 空文本保护测试通过")


def test_no_matching_locations():
    """地点不存在时保持原始值"""
    locations = []

    # 卡片显示
    card = frontend_card_display("loc_unknown", locations)
    assert card == "起始地点: loc_unknown", f"预期='起始地点: loc_unknown', 实际='{card}'"

    # 表单填充
    form_val = frontend_form_fill("loc_unknown", locations)
    assert form_val == "loc_unknown", f"预期='loc_unknown', 实际='{form_val}'"

    # 表单收集
    collected_id = frontend_form_collect("未知地点", locations)
    assert collected_id == "未知地点", f"预期='未知地点', 实际='{collected_id}'"

    print("[OK] 无匹配地点测试通过")


def test_no_canon_data():
    """无 canon 数据时原样返回"""
    text = "char_001 来到了一个地方。"
    result = replace_ids_with_names(text, {})
    assert result == text, f"预期原样返回, 实际='{result}'"
    print("[OK] 无 canon 数据测试通过")


def test_variable_id_lengths():
    """不同长度 ID 混合"""
    canon = {
        "characters": [
            {"id": "c_999", "name": "短ID"},
            {"id": "char_very_long_id_123", "name": "长ID角色"},
            {"id": "char_mid", "name": "中ID角色"},
        ],
        "locations": [
            {"id": "loc", "name": "短地点"},
            {"id": "location_very_long_id_456", "name": "长地点名"},
        ]
    }

    text = "char_very_long_id_123 从 location_very_long_id_456 走到了 loc。char_mid 在中途遇到 c_999。"
    result = replace_ids_with_names(text, canon)
    expected = "长ID角色 从 长地点名 走到了 短地点。中ID角色 在中途遇到 短ID。"
    assert result == expected, f"\n预期: {expected}\n实际: {result}"
    print("[OK] 混合长度 ID 测试通过")


# ═══════════════════════════════════════════
# 运行
# ═══════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_scenario_A,
        test_scenario_B,
        test_scenario_C,
        test_long_id_priority,
        test_empty_text,
        test_no_matching_locations,
        test_no_canon_data,
        test_variable_id_lengths,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__} 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__} 异常: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"总计: {len(tests)} | 通过: {passed} | 失败: {failed}")
    if failed == 0:
        print("[OK] 所有测试通过！")
    else:
        print(f"[WARN] {failed} 个测试失败")
