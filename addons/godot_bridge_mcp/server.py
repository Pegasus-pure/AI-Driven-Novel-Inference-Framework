#!/usr/bin/env python3
import asyncio
import json
import logging
import os
from typing import Any, Optional, Dict

import websockets
from mcp.server.fastmcp import FastMCP
from websockets.exceptions import ConnectionClosed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BRIDGE_PORT = int(os.environ.get("GODOT_BRIDGE_PORT", "4099"))
GODOT_WS_URI = f"ws://localhost:{BRIDGE_PORT}"
REQUEST_TIMEOUT = 10

mcp = FastMCP("Godot Bridge")

class GodotConnection:
    def __init__(self, uri: str):
        self.uri = uri
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.lock = asyncio.Lock()
        self._pending: Dict[str, asyncio.Future] = {}
        self._counter = 0
        self._receiver_task: Optional[asyncio.Task] = None

    async def connect(self):
        async with self.lock:
            # websockets >= 13: use state; < 13: use open
            if self.websocket:
                try:
                    if self.websocket.state == websockets.protocol.State.OPEN:
                        return
                except AttributeError:
                    if self.websocket.open:
                        return
            try:
                self.websocket = await websockets.connect(self.uri)
                self._receiver_task = asyncio.create_task(self._receive_loop())
                logger.info(f"Connected to Godot at {self.uri}")
            except Exception as e:
                logger.error(f"Failed to connect: {e}")
                raise

    async def disconnect(self):
        async with self.lock:
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            if self._receiver_task:
                self._receiver_task.cancel()
                self._receiver_task = None

    async def _receive_loop(self):
        try:
            async for msg in self.websocket:
                try:
                    data = json.loads(msg)
                    req_id = data.get("id")
                    if req_id and req_id in self._pending:
                        future = self._pending.pop(req_id)
                        if data.get("error"):
                            future.set_exception(Exception(str(data["error"])))
                        else:
                            future.set_result(data.get("result"))
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON: {msg}")
        except ConnectionClosed:
            logger.info("Connection closed")
        finally:
            await self.disconnect()

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        await self.connect()
        async with self.lock:
            self._counter += 1
            req_id = str(self._counter)
            future = asyncio.Future()
            self._pending[req_id] = future

        request = {"id": req_id, "method": method, "params": params or {}}
        try:
            await self.websocket.send(json.dumps(request))
            return await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"Request '{method}' timed out.")
        except Exception as e:
            self._pending.pop(req_id, None)
            raise e

godot_conn = GodotConnection(GODOT_WS_URI)

@mcp.tool()
async def get_scene_tree() -> str:
    """获取当前场景的节点树结构"""
    try:
        result = await godot_conn.send_request("get_scene_tree")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def add_node(node_type: str, node_name: str = "", parent_path: str = "") -> str:
    """在场景中添加新节点"""
    try:
        params = {"type": node_type}
        if node_name:
            params["name"] = node_name
        if parent_path:
            params["parent_path"] = parent_path
        result = await godot_conn.send_request("add_node", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def get_node_properties(node_path: str) -> str:
    """获取节点的所有属性"""
    try:
        result = await godot_conn.send_request("get_node_properties", {"path": node_path})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def set_node_property(node_path: str, property: str, value: Any) -> str:
    """设置节点属性值"""
    try:
        result = await godot_conn.send_request("set_node_property", {
            "path": node_path, "property": property, "value": value
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def execute_script(code: str) -> str:
    """在当前场景执行 GDScript 代码"""
    try:
        result = await godot_conn.send_request("execute_script", {"code": code})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def get_selected_nodes() -> str:
    """获取当前选中的节点列表"""
    try:
        result = await godot_conn.send_request("get_selected_nodes")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def get_editor_info() -> str:
    """获取编辑器信息"""
    try:
        result = await godot_conn.send_request("get_editor_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def create_scene(scene_name: str, root_type: str = "Node2D", directory: str = "res://", open_after_create: bool = False, overwrite: bool = False) -> str:
    """创建新 Godot 场景文件 (.tscn)"""
    try:
        params = {
            "scene_name": scene_name,
            "root_type": root_type,
            "directory": directory,
            "open_after_create": open_after_create,
            "overwrite": overwrite
        }
        result = await godot_conn.send_request("create_scene", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def save_scene(path: str = "") -> str:
    """保存当前场景（空路径=保存到当前位置）"""
    try:
        result = await godot_conn.send_request("save_scene", {"path": path})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def attach_script(node_path: str, script_path: str) -> str:
    """为节点挂载脚本"""
    try:
        params = {"node_path": node_path, "script_path": script_path}
        result = await godot_conn.send_request("attach_script", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def delete_node(node_path: str) -> str:
    """删除场景中的节点（不能删除根节点）"""
    try:
        result = await godot_conn.send_request("delete_node", {"node_path": node_path})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def list_assets(asset_type: str = "all", directory: str = "res://") -> str:
    """列出项目中的所有资源（场景、脚本等）

    Args:
        asset_type: 资源类型 - "scene"场景, "script"脚本, "all"全部
        directory: 搜索目录，默认 "res://"
    """
    try:
        result = await godot_conn.send_request("list_assets", {
            "asset_type": asset_type,
            "directory": directory
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def get_script_info(script_path: str) -> str:
    """获取 GDScript 文件的详细信息（继承类型、方法、信号、导出变量等）

    Args:
        script_path: GDScript 文件路径，例如 "res://scripts/player.gd"
    """
    try:
        result = await godot_conn.send_request("get_script_info", {
            "script_path": script_path
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def create_scene_from_script(script_path: str, directory: str = "") -> str:
    """从已有 GDScript 创建场景文件（自动检测基类并生成 .tscn）

    Args:
        script_path: 脚本文件的 res:// 路径
        directory: 场景保存目录，空=与脚本同目录
    """
    try:
        result = await godot_conn.send_request("create_scene_from_script", {
            "script_path": script_path,
            "directory": directory
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
async def list_node_types() -> str:
    """列出所有可实例化的节点类型"""
    try:
        result = await godot_conn.send_request("list_node_types", {})
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    try:
        mcp.run(transport='stdio')
    except KeyboardInterrupt:
        logger.info("Server stopped")
    finally:
        asyncio.run(godot_conn.disconnect())
