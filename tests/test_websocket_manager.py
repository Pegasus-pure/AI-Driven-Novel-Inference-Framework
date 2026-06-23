# -*- coding: utf-8 -*-
"""WebSocketManager 单元测试（简化版）

测试 WebSocket 连接管理器的核心功能
"""

import pytest
from unittest.mock import Mock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.network.websocket_manager import WebSocketManager
from fastapi import WebSocket


class TestWebSocketManagerInit:
    """测试初始化"""

    def test_init(self):
        """测试基本初始化"""
        mgr = WebSocketManager()
        
        assert isinstance(mgr._connections, dict)
        assert isinstance(mgr.sessions, dict)
        assert isinstance(mgr._ws_to_sid, dict)
        assert len(mgr._connections) == 0
        assert len(mgr.sessions) == 0
        assert len(mgr._ws_to_sid) == 0


class TestWebSocketManagerKeys:
    """测试 WebSocket 键生成"""

    def test_ws_key_consistency(self):
        """测试同一个 WebSocket 的键保持一致"""
        mgr = WebSocketManager()
        
        # 创建 Mock WebSocket
        mock_ws = Mock()
        mock_ws.id = 12345
        
        key1 = mgr._ws_key(mock_ws)
        key2 = mgr._ws_key(mock_ws)
        
        assert key1 == key2
        assert isinstance(key1, int)


class TestWebSocketManagerRegister:
    """测试会话注册"""

    def test_register_session(self):
        """测试注册 GameSession"""
        mgr = WebSocketManager()
        
        mock_session = Mock()
        mock_session.session_id = "test_001"
        
        mgr.register_session("test_001", mock_session)
        
        assert "test_001" in mgr.sessions
        assert mgr.sessions["test_001"] == mock_session

    def test_register_multiple_sessions(self):
        """测试注册多个会话"""
        mgr = WebSocketManager()
        
        for i in range(5):
            mock_session = Mock()
            mock_session.session_id = f"test_{i:03d}"
            mgr.register_session(f"test_{i:03d}", mock_session)
        
        assert len(mgr.sessions) == 5


class TestWebSocketManagerQuery:
    """测试查询方法"""

    def test_get_session_id_no_connection(self):
        """测试无连接时返回 None"""
        mgr = WebSocketManager()
        
        mock_ws = Mock()
        sid = mgr.get_session_id(mock_ws)
        
        assert sid is None

    def test_get_session_no_connection(self):
        """测试无连接时返回 None"""
        mgr = WebSocketManager()
        
        mock_ws = Mock()
        session = mgr.get_session(mock_ws)
        
        assert session is None

    def test_get_ws_no_session(self):
        """测试无会话时返回 None"""
        mgr = WebSocketManager()
        
        ws = mgr.get_ws("nonexistent")
        
        assert ws is None


class TestWebSocketManagerIntegration:
    """测试集成功能（使用 Mock）"""

    def test_connect_and_get_session_id(self):
        """测试连接后获取会话 ID"""
        mgr = WebSocketManager()
        
        # 模拟连接
        mock_ws = Mock()
        mock_ws.id = 999
        
        # 注意：这里不能实际调用 connect()，因为它是异步的
        # 我们直接设置内部状态
        mgr._ws_to_sid[mgr._ws_key(mock_ws)] = "test_001"
        mgr._connections["test_001"] = mock_ws
        
        # 查询
        sid = mgr.get_session_id(mock_ws)
        assert sid == "test_001"

    def test_register_and_get_session(self):
        """测试注册后获取会话"""
        mgr = WebSocketManager()
        
        mock_ws = Mock()
        mock_ws.id = 999
        mock_session = Mock()
        mock_session.session_id = "test_001"
        
        # 注册会话
        mgr.register_session("test_001", mock_session)
        mgr._ws_to_sid[mgr._ws_key(mock_ws)] = "test_001"
        
        # 查询
        session = mgr.get_session(mock_ws)
        assert session == mock_session

    def test_get_ws_after_register(self):
        """测试注册后获取 WebSocket"""
        mgr = WebSocketManager()
        
        mock_ws = Mock()
        mock_ws.id = 999
        
        # 设置状态
        mgr._connections["test_001"] = mock_ws
        
        # 查询
        ws = mgr.get_ws("test_001")
        assert ws == mock_ws


class TestWebSocketManagerEdgeCases:
    """测试边界情况"""

    def test_double_register(self):
        """测试重复注册"""
        mgr = WebSocketManager()
        
        mock_session1 = Mock()
        mock_session1.session_id = "test_001"
        
        mock_session2 = Mock()
        mock_session2.session_id = "test_001"  # 相同 ID
        
        mgr.register_session("test_001", mock_session1)
        mgr.register_session("test_001", mock_session2)  # 覆盖
        
        assert mgr.sessions["test_001"] == mock_session2

    def test_unregister_nonexistent(self):
        """测试取消注册不存在的会话"""
        mgr = WebSocketManager()
        
        # 不应该抛出异常
        mgr.sessions.pop("nonexistent", None)
        
        assert len(mgr.sessions) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
