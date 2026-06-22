# -*- coding: utf-8 -*-
"""WebSocket 连接管理器

追踪活跃连接与会话映射。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import WebSocket

from .logging_config import get_logger

_log = get_logger("Rain.WSManager")


class WebSocketManager:
    """WebSocket 连接管理器

    维护 session_id ↔ WebSocket 和 session_id ↔ GameSession 的映射。
    """

    def __init__(self) -> None:
        # session_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # session_id → GameSession
        self.sessions: dict[str, Any] = {}
        # WebSocket id(hash) → session_id
        self._ws_to_sid: dict[int, str] = {}

    def _ws_key(self, ws: WebSocket) -> int:
        """获取 WebSocket 的唯一标识"""
        return id(ws)

    # ────────────────────────────────────────────────
    # 连接生命周期
    # ────────────────────────────────────────────────

    async def connect(self, ws: WebSocket, session_id: str = "") -> None:
        """接受 WebSocket 连接

        Args:
            ws: WebSocket 连接实例
            session_id: 重连时携带的旧会话 ID
        """
        await ws.accept()

        sid = session_id if session_id else ""
        ws_key = self._ws_key(ws)
        self._ws_to_sid[ws_key] = sid
        if sid:
            self._connections[sid] = ws

    async def disconnect(self, ws: WebSocket) -> None:
        """断开 WebSocket 连接（不清除 GameSession，允许重连）

        Args:
            ws: 要断开的 WebSocket
        """
        ws_key = self._ws_key(ws)
        sid = self._ws_to_sid.pop(ws_key, "")

        if sid and sid in self._connections:
            # 保留 sessions 以便重连，仅移除连接映射
            if self._connections.get(sid) is ws:
                del self._connections[sid]

        try:
            await ws.close()
        except Exception:
            pass

    def register_session(self, session_id: str, session: Any) -> None:
        """注册 GameSession

        Args:
            session_id: 会话 ID
            session: GameSession 实例
        """
        self.sessions[session_id] = session

    def register_connection(self, session_id: str, ws: WebSocket) -> None:
        """注册 WebSocket 与会话 ID 的映射

        首次连接时，connect() 中的 session_id 为空字符串，
        无法建立 _connections 映射。本方法在获取真实 session_id 后调用。

        Args:
            session_id: 真实会话 ID
            ws: WebSocket 连接实例
        """
        self._connections[session_id] = ws
        # 同步更新 _ws_to_sid 中的 key
        ws_key = self._ws_key(ws)
        self._ws_to_sid[ws_key] = session_id

    # ────────────────────────────────────────────────
    # 查询
    # ────────────────────────────────────────────────

    def get_session_id(self, ws: WebSocket) -> Optional[str]:
        """获取 WebSocket 关联的会话 ID"""
        return self._ws_to_sid.get(self._ws_key(ws))

    def get_session(self, ws: WebSocket) -> Optional[Any]:
        """获取 WebSocket 关联的 GameSession"""
        sid = self.get_session_id(ws)
        if sid:
            return self.sessions.get(sid)
        return None

    def get_ws(self, session_id: str) -> Optional[WebSocket]:
        """获取会话 ID 关联的 WebSocket"""
        return self._connections.get(session_id)

    # ────────────────────────────────────────────────
    # 消息发送
    # ────────────────────────────────────────────────

    async def send_json(self, ws: WebSocket, data: dict) -> bool:
        """向指定 WebSocket 发送 JSON 消息

        Args:
            ws: 目标 WebSocket
            data: 要发送的字典数据

        Returns:
            bool: 是否发送成功
        """
        try:
            # 检查连接状态
            if hasattr(ws, 'client_state'):
                from starlette.websockets import WebSocketState
                if ws.client_state != WebSocketState.CONNECTED:
                    _log.warning("WebSocket 未连接，跳过消息: %s", data.get("type", "unknown"))
                    return False

            await ws.send_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception as exc:
            _log.error("发送消息失败: %s", exc)
            return False

    async def broadcast(self, data: dict) -> None:
        """向所有已连接客户端广播消息

        Args:
            data: 要广播的字典数据
        """
        failed_sids = []
        for sid, ws in list(self._connections.items()):
            success = await self.send_json(ws, data)
            if not success:
                failed_sids.append(sid)

        # 清理失败的连接
        for sid in failed_sids:
            if sid in self._connections:
                del self._connections[sid]
                _log.warning("清理失败连接: session=%s", sid)
