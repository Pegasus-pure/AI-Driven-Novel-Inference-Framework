# -*- coding: utf-8 -*-
"""GameSession 单元测试

测试游戏会话编排器的核心功能
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.app.game_session import GameSession
from server.app.world_state import WorldState


class TestGameSessionInit:
    """测试 GameSession 初始化"""

    def test_init_basic(self):
        """测试基本初始化"""
        session = GameSession("test_session")
        
        assert session.session_id == "test_session"
        assert isinstance(session.world_state, WorldState)
        assert session.pipeline is None
        assert session.beat_count == 0
        assert session.is_active is False
        assert session.current_novel == ""
        assert isinstance(session.event_log, list)
        assert isinstance(session.save_manager, object)
        assert isinstance(session.canon_manager, object)

    def test_init_with_custom_params(self):
        """测试自定义参数初始化"""
        session = GameSession(
            "test_002",
            extractor_name="regex",
            fallback_extractor_name="llm",
            storage_name="file"  # 使用有效的存储后端
        )
        
        assert session.session_id == "test_002"
        assert session._extractor_name == "regex"
        assert session._fallback_extractor_name == "llm"


class TestGameSessionExtractor:
    """测试提取器管理"""

    def test_set_extractor(self):
        """测试设置提取器"""
        session = GameSession("test")
        
        # 初始状态
        assert session._extractor is None
        
        # 设置提取器
        session.set_extractor("regex")
        
        assert session._extractor_name == "regex"
        assert session._extractor is not None

    def test_set_fallback_extractor(self):
        """测试设置回退提取器"""
        session = GameSession("test")
        
        session.set_fallback_extractor("llm")
        
        assert session._fallback_extractor_name == "llm"
        assert session._fallback_extractor is not None


class TestGameSessionState:
    """测试状态管理"""

    def test_get_state_snapshot(self):
        """测试获取状态快照"""
        session = GameSession("test")
        
        # 修改一些状态
        session.world_state.player_location = "test_location"
        session.world_state.world_divergence = 0.5
        session.beat_count = 5
        
        snapshot = session.get_state_snapshot()
        
        # 检查实际返回的键
        assert "player_location" in snapshot
        assert snapshot["player_location"] == "test_location"
        assert "divergence" in snapshot
        assert pytest.approx(snapshot["divergence"], abs=0.01) == 0.5
        assert "beat_count" in snapshot
        assert snapshot["beat_count"] == 5
        assert "game_time" in snapshot
        # 注意：快照中没有 time_index 键

    def test_restore_state(self):
        """测试恢复状态"""
        import tempfile
        from server.data.save_manager import SaveManager
        
        session = GameSession("test")
        
        # 使用临时目录进行完整的存档-加载-恢复循环
        with tempfile.TemporaryDirectory() as tmpdir:
            session.save_manager = SaveManager(saves_dir=tmpdir)
            
            # 修改状态
            session.world_state.player_location = "restore_location"
            session.world_state.world_divergence = 0.8
            session.beat_count = 15
            session.event_log.append({"type": "restore_test"})
            
            # 存档
            session.save_manager.save(0, session, "restore_test")
            
            # 创建新会话
            session2 = GameSession("test2")
            session2.save_manager = SaveManager(saves_dir=tmpdir)
            
            # 加载并恢复
            data = session2.save_manager.load(0)
            session2.restore_state(data)
            
            # 验证恢复
            assert session2.world_state.player_location == "restore_location"
            assert pytest.approx(session2.world_state.world_divergence, abs=0.01) == 0.8
            assert session2.beat_count == 15
            assert len(session2.event_log) == 1


class TestGameSessionCanon:
    """测试 Canon 管理"""

    def test_scan_available_canons(self):
        """测试扫描可用 Canon"""
        session = GameSession("test")
        
        # 扫描（使用实际的存储后端）
        result = session._scan_available_canons()
        
        assert isinstance(result, dict)
        # 检查实际返回的键
        assert "canons" in result
        assert "txt_files" in result
        assert "has_existing_canon" in result
        assert isinstance(result["canons"], list)
        assert isinstance(result["txt_files"], list)

    def test_can_switch_novel_no_game(self):
        """测试无游戏进行时允许切换"""
        session = GameSession("test")
        
        can_switch, reason = session.can_switch_novel()
        
        assert can_switch is True
        assert reason == ""

    def test_canon_ready_payload(self):
        """测试 Canon 就绪负载"""
        session = GameSession("test")
        
        # 设置 Canon 数据（使用英文避免编码问题）
        session.world_state.canon = {
            "meta": {"title": "Test Novel"},
            "characters": [{"id": "c1", "name": "Char1"}],
            "locations": [{"id": "l1", "name": "Loc1"}],
        }
        
        payload = session.canon_ready_payload()
        
        # 检查实际返回的键
        assert "meta" in payload
        assert payload["meta"]["title"] == "Test Novel"
        assert "characters" in payload
        assert len(payload["characters"]) == 1
        assert "locations" in payload
        assert len(payload["locations"]) == 1


class TestGameSessionSave:
    """测试存档功能"""

    def test_save_and_load_cycle(self):
        """测试存档-加载循环"""
        import tempfile
        from server.data.save_manager import SaveManager
        
        session = GameSession("test")
        
        # 使用临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            session.save_manager = SaveManager(saves_dir=tmpdir)
            
            # 修改状态
            session.world_state.player_location = "save_location"
            session.beat_count = 10
            session.event_log.append({"type": "save_test"})
            
            # 存档
            result = session.save_manager.save(0, session, "test_save")
            
            assert result["slot"] == 0
            assert result["name"] == "test_save"
            assert "timestamp" in result
            
            # 加载
            data = session.save_manager.load(0)
            
            assert data is not None
            # 检查实际返回的键
            assert "player_location" in data
            assert data["player_location"] == "save_location"
            assert "beat_count" in data
            assert data["beat_count"] == 10
            assert "event_log" in data
            assert len(data["event_log"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
