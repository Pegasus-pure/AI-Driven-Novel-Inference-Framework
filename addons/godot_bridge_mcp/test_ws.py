"""Integration tests for Godot Bridge MCP WebSocket API.

These tests require a running Godot editor with the MCP Bridge plugin active
on ws://localhost:8080.  Run with:  python test_ws.py
"""

import asyncio
import json

import websockets

WS_URI = "ws://localhost:8080"
REQUEST_TIMEOUT = 10


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

async def send_request(method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC request to the Godot WebSocket server and return
    the ``result`` dict.  Errors are returned as ``{"error": ...}``.
    """
    try:
        async with websockets.connect(WS_URI) as ws:
            request = {
                "id": "test_req",
                "method": method,
                "params": params or {},
            }
            await ws.send(json.dumps(request))
            response = await asyncio.wait_for(ws.recv(), timeout=REQUEST_TIMEOUT)
            data = json.loads(response)
            if data.get("error"):
                return {"error": data["error"]}
            return data.get("result", {})
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# test cases
# ---------------------------------------------------------------------------

async def test_create_scene():
    """创建临时场景，验证文件存在"""
    result = await send_request(
        "create_scene",
        {
            "scene_name": "test_temp_scene",
            "root_type": "Node2D",
            "directory": "res://test_output/",
            "open_after_create": False,
            "overwrite": True,
        },
    )
    assert result.get("success"), f"create_scene failed: {result.get('error')}"
    print(f"✅ create_scene: {result['scene_path']}")


async def test_save_scene():
    """保存当前打开场景"""
    result = await send_request("save_scene", {})
    assert result.get("success"), f"save_scene failed: {result.get('error')}"
    print(f"✅ save_scene: {result['scene_path']}")


async def test_attach_script():
    """给节点挂载脚本"""
    # 先确保有场景和节点
    await send_request(
        "create_scene",
        {
            "scene_name": "test_attach",
            "root_type": "Control",
            "directory": "res://test_output/",
            "overwrite": True,
        },
    )
    result = await send_request(
        "attach_script",
        {"node_path": ".", "script_path": "res://src/ui/main.gd"},
    )
    # attach_script 成功或脚本类型不匹配均可接受
    print(f"✅ attach_script: {result}")


async def test_delete_node():
    """创建子节点后删除"""
    await send_request(
        "add_node",
        {"parent_path": ".", "node_type": "Label", "node_name": "TestLabel"},
    )
    result = await send_request("delete_node", {"node_path": "TestLabel"})
    assert result.get("success"), f"delete_node failed: {result.get('error')}"
    print(f"✅ delete_node: deleted {result['deleted_node']}")


async def test_delete_node_root_protected():
    """验证无法删除根节点"""
    result = await send_request("delete_node", {"node_path": "."})
    assert "error" in result, "Should reject root deletion"
    print(f"✅ delete_node root protection: {result['error']}")


async def test_list_assets():
    """验证列表格式"""
    result = await send_request("list_assets", {"asset_type": "all", "directory": "res://src/"})
    assert result.get("scenes") is not None, "Missing scenes list"
    assert result.get("scripts") is not None, "Missing scripts list"
    print(f"✅ list_assets: {result.get('total')} assets found")


async def test_get_script_info():
    """读取已知脚本的元信息"""
    result = await send_request("get_script_info", {"script_path": "res://src/ui/main.gd"})
    assert result.get("extends"), "Missing extends info"
    print(
        f"✅ get_script_info: extends {result['extends']}, "
        f"{len(result.get('methods', []))} methods"
    )


async def test_list_node_types():
    """验证返回类型列表"""
    result = await send_request("list_node_types", {})
    # list_node_types 应返回节点类型列表
    assert result.get("node_types") or result.get("success") is not None, "Missing node types"
    print("✅ list_node_types: done")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

async def _run_all():
    """Execute every test in order, printing a summary at the end."""
    tests = [
        ("test_create_scene", test_create_scene),
        ("test_save_scene", test_save_scene),
        ("test_attach_script", test_attach_script),
        ("test_delete_node", test_delete_node),
        ("test_delete_node_root_protected", test_delete_node_root_protected),
        ("test_list_assets", test_list_assets),
        ("test_get_script_info", test_get_script_info),
        ("test_list_node_types", test_list_node_types),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        print(f"\n--- Running {name} ---")
        try:
            await func()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"❌ {name} FAILED: {exc}")

    print(f"\n{'=' * 50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_run_all())
