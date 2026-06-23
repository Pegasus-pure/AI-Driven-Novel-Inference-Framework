# -*- coding: utf-8 -*-
"""WebSocket 连接管理器

追踪活跃连接与会话映射，并提供 session 过期清理。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from fastapi import WebSocket

from server.config.logging_config import get_logger

_log = get_logger("Rain.WSManager")

# 会话过期时间：30 分钟无活动自动清理
_SESSION_TTL = 1800


class WebSocketManager:
    """WebSocket 连接管理器

    维护 session_id ↔ WebSocket 和 session_id ↔ GameSession 的映射。
    自动清理 30 分钟无活动的过期 session。
    """

    def __init__(self) -> None:
        # session_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # session_id → GameSession
        self.sessions: dict[str, Any] = {}
        # WebSocket id(hash) → session_id
        self._ws_to_sid: dict[int, str] = {}
        # session_id → 最后一次活动时间戳
        self._last_seen: dict[str, float] = {}
        # 保护共享状态的异步锁
        self._lock = asyncio.Lock()

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

        async with self._lock:
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
        async with self._lock:
            ws_key = self._ws_key(ws)
            sid = self._ws_to_sid.pop(ws_key, "")

            if sid and sid in self._connections:
                # 保留 sessions 以便重连，仅移除连接映射
                if self._connections.get(sid) is ws:
                    del self._connections[sid]

        try:
            await ws.close()
        except Exception:
            _log.debug("WebSocket 关闭异常（连接可能已断开）")
            pass

    async def register_session(self, session_id: str, session: Any) -> None:
        """注册 GameSession

        Args:
            session_id: 会话 ID
            session: GameSession 实例
        """
        async with self._lock:
            self.sessions[session_id] = session
            self._last_seen[session_id] = time.time()

    async def mark_active(self, session_id: str) -> None:
        """刷新会话的最后活动时间（心跳时调用）。"""
        async with self._lock:
            self._last_seen[session_id] = time.time()

    async def cleanup_stale_sessions(self) -> int:
        """清理超过 _SESSION_TTL 无活动且无活跃连接的 session。

        Returns:
            清理的 session 数量。
        """
        async with self._lock:
            now = time.time()
            stale = [
                sid for sid in self.sessions
                if sid not in self._connections
                and now - self._last_seen.get(sid, 0) > _SESSION_TTL
            ]
            for sid in stale:
                session = self.sessions.pop(sid, None)
                self._last_seen.pop(sid, None)
                if session and hasattr(session, 'cleanup'):
                    asyncio.ensure_future(session.cleanup())
                _log.info("清理过期 session: %s", sid)
            return len(stale)

    async def register_connection(self, session_id: str, ws: WebSocket) -> None:
        """注册 WebSocket 与会话 ID 的映射

        首次连接时，connect() 中的 session_id 为空字符串，
        无法建立 _connections 映射。本方法在获取真实 session_id 后调用。

        Args:
            session_id: 真实会话 ID
            ws: WebSocket 连接实例
        """
        async with self._lock:
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
        async with self._lock:
            connections = list(self._connections.items())
        
        failed_sids = []
        for sid, ws in connections:
            success = await self.send_json(ws, data)
            if not success:
                failed_sids.append(sid)

        # 清理失败的连接
        async with self._lock:
            for sid in failed_sids:
                if sid in self._connections:
                    del self._connections[sid]
                    _log.warning("清理失败连接: session=%s", sid)


    # ────────────────────────────────────────────────
    # 主动推送消息（Phase 2 新增）
    # ────────────────────────────────────────────────

    async def push_game_state_update(self, session_id: str) -> bool:
        """推送游戏状态更新（供 Game Info Bar 使用）
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否推送成功
        """
        try:
            session = self.sessions.get(session_id)
            if session is None:
                _log.warning("推送游戏状态失败: 会话 %s 不存在", session_id)
                return False
            
            ws = self.get_ws(session_id)
            if ws is None:
                _log.warning("推送游戏状态失败: 会话 %s 无活跃连接", session_id)
                return False
            
            # 从 game_session 中提取状态数据
            game_state = {
                "location": getattr(session, 'current_location', "起点小镇"),
                "tension": getattr(session, 'tension_level', 0.5),
                "clues": getattr(session, 'collected_clues', 3),
                "present_npcs": getattr(session, 'present_npcs', ["李四", "王五"])
            }
            
            # 推送消息
            message = {
                "type": "game_state_update",
                "data": game_state
            }
            
            success = await self.send_json(ws, message)
            if success:
                _log.info("推送游戏状态更新: session=%s", session_id)
            return success
        except Exception as exc:
            _log.error("推送游戏状态失败: %s", exc)
            return False

    async def push_soul_profile_update(self, session_id: str) -> bool:
        """推送灵魂附生档案更新
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否推送成功
        """
        try:
            session = self.sessions.get(session_id)
            if session is None:
                _log.warning("推送灵魂档案失败: 会话 %s 不存在", session_id)
                return False
            
            ws = self.get_ws(session_id)
            if ws is None:
                _log.warning("推送灵魂档案失败: 会话 %s 无活跃连接", session_id)
                return False
            
            # TODO: 实际实现需要从 SoulPossessionManager 中获取
            soul_data = {
                "ocean": {
                    "openness": 0.7,
                    "conscientiousness": 0.6,
                    "extraversion": 0.4,
                    "agreeableness": 0.8,
                    "neuroticism": 0.3
                },
                "moral_alignment": "neutral_good"
            }
            
            # 推送消息
            message = {
                "type": "soul_profile_update",
                "data": soul_data
            }
            
            success = await self.send_json(ws, message)
            if success:
                _log.info("推送灵魂档案更新: session=%s", session_id)
            return success
        except Exception as exc:
            _log.error("推送灵魂档案失败: %s", exc)
            return False

    async def push_npc_dissonance_update(self, session_id: str) -> bool:
        """推送 NPC 认知冲突更新
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否推送成功
        """
        try:
            session = self.sessions.get(session_id)
            if session is None:
                _log.warning("推送 NPC 认知冲突失败: 会话 %s 不存在", session_id)
                return False
            
            ws = self.get_ws(session_id)
            if ws is None:
                _log.warning("推送 NPC 认知冲突失败: 会话 %s 无活跃连接", session_id)
                return False
            
            # TODO: 实际实现需要从 CharacterCognitionManager 中获取
            dissonance_data = {
                "npc_dissonances": [
                    {
                        "npc_id": "npc_001",
                        "npc_name": "李四",
                        "conflict_type": "identity_confusion",
                        "conflict_level": 0.7,
                        "description": "李四对主角的身份感到困惑"
                    }
                ]
            }
            
            # 推送消息
            message = {
                "type": "npc_dissonance_update",
                "data": dissonance_data
            }
            
            success = await self.send_json(ws, message)
            if success:
                _log.info("推送 NPC 认知冲突更新: session=%s", session_id)
            return success
        except Exception as exc:
            _log.error("推送 NPC 认知冲突失败: %s", exc)
            return False

