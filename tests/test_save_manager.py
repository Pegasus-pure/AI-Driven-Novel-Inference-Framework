# -*- coding: utf-8 -*-
"""SaveManager 测试 - 修正版，使用Mock模拟session"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock


class TestSaveManagerBasic:
    """测试SaveManager基础功能（不需要session）"""
    
    @pytest.fixture
    def save_mgr(self):
        """创建临时存档目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from server.data.save_manager import SaveManager
            sm = SaveManager(saves_dir=tmpdir)
            yield sm
    
    def test_init(self, save_mgr):
        """测试初始化"""
        assert save_mgr._saves_dir.exists()
        assert save_mgr.DEFAULT_SLOTS == 3
    
    def test_list_slots_empty(self, save_mgr):
        """测试空存档列表"""
        slots = save_mgr.list_slots()
        
        assert len(slots) == 3
        assert all(s["name"] == "(空)" for s in slots)
    
    def test_delete_slot_empty(self, save_mgr):
        """测试删除空槽位"""
        result = save_mgr.delete_slot(0)
        assert result is False  # 空槽位删除失败


class TestSaveManagerWithSave:
    """测试SaveManager存档功能（需要Mock session）"""
    
    @pytest.fixture
    def save_mgr_with_slot(self):
        """创建临时存档目录并添加一个测试存档"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from server.data.save_manager import SaveManager
            sm = SaveManager(saves_dir=tmpdir)
            
            # 手动创建一个测试存档
            test_save = {
                "slot": 0,
                "name": "测试存档",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "beat_id": "beat_005",
                "beat_count": 5,
                "novel_title": "测试小说",
                "game_time": "第一月·第一日·清晨",
                "divergence": 0.3,
                "player_location": "起始之地",
                "event_log": [],
                "world_state_snapshot": {}
            }
            
            slot_path = sm._slot_path(0)
            with open(slot_path, "w", encoding="utf-8") as f:
                json.dump(test_save, f, ensure_ascii=False, indent=2)
            
            yield sm
    
    def test_list_slots_with_save(self, save_mgr_with_slot):
        """测试有存档时的列表"""
        sm = save_mgr_with_slot
        slots = sm.list_slots()
        
        assert slots[0]["name"] == "测试存档"
        assert slots[0]["beat_count"] == 5
        assert slots[1]["name"] == "(空)"
    
    def test_load_save(self, save_mgr_with_slot):
        """测试加载存档"""
        sm = save_mgr_with_slot
        data = sm.load(0)
        
        assert data is not None
        assert data["name"] == "测试存档"
        assert data["beat_count"] == 5
    
    def test_load_empty_slot(self, save_mgr_with_slot):
        """测试加载空槽位"""
        sm = save_mgr_with_slot
        data = sm.load(1)
        
        assert data is None
    
    def test_delete_slot_with_save(self, save_mgr_with_slot):
        """测试删除有存档的槽位"""
        sm = save_mgr_with_slot
        
        # 确认存档存在
        assert sm.load(0) is not None
        
        # 删除
        result = sm.delete_slot(0)
        assert result is True
        
        # 确认已删除
        assert sm.load(0) is None
        assert sm.list_slots()[0]["name"] == "(空)"


class TestSaveManagerSave:
    """测试保存功能（使用Mock session）"""
    
    @pytest.fixture
    def mock_session(self):
        """创建Mock session对象"""
        session = Mock()
        
        # Mock world_state
        session.world_state = Mock()
        session.world_state.to_dict.return_value = {
            "version": 2,
            "game_time": "测试时间",
            "time_index": 10,
            "player_location": "测试地点",
            "world_divergence": 0.5
        }
        session.world_state.game_time = "测试时间"
        session.world_state.world_divergence = 0.5
        session.world_state.player_location = "测试地点"
        
        # Mock 其他属性
        session.beat_count = 10
        session.event_log = ["事件1", "事件2"]
        session.current_novel = "测试小说"
        
        # Mock canon_manager
        session.canon_manager = Mock()
        session.canon_manager.is_running.return_value = False
        
        return session
    
    @pytest.fixture
    def save_mgr(self):
        """创建临时存档目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from server.data.save_manager import SaveManager
            sm = SaveManager(saves_dir=tmpdir)
            yield sm
    
    def test_save_success(self, save_mgr, mock_session):
        """测试成功保存"""
        result = save_mgr.save(slot=0, session=mock_session, name="我的存档")
        
        assert result["slot"] == 0
        assert result["name"] == "我的存档"
        assert "timestamp" in result
        
        # 验证文件已写入
        assert save_mgr._slot_path(0).exists()
    
    def test_save_auto_name(self, save_mgr, mock_session):
        """测试自动生成存档名"""
        result = save_mgr.save(slot=1, session=mock_session, name="")
        
        assert result["name"] == "自动存档"
    
    def test_save_and_load(self, save_mgr, mock_session):
        """测试保存后加载"""
        # 保存
        save_mgr.save(slot=0, session=mock_session, name="测试")
        
        # 加载
        data = save_mgr.load(0)
        
        assert data["name"] == "测试"
        assert data["beat_count"] == 10
        assert data["novel_title"] == "测试小说"
    
    def test_save_invalid_slot(self, save_mgr, mock_session):
        """测试无效槽位"""
        with pytest.raises(ValueError):
            save_mgr.save(slot=5, session=mock_session)


class TestSaveManagerEdgeCases:
    """测试边界情况"""
    
    @pytest.fixture
    def save_mgr(self):
        """创建临时存档目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from server.data.save_manager import SaveManager
            sm = SaveManager(saves_dir=tmpdir)
            yield sm
    
    def test_corrupted_save(self, save_mgr):
        """测试损坏的存档文件"""
        # 写入无效的JSON
        slot_path = save_mgr._slot_path(0)
        with open(slot_path, "w", encoding="utf-8") as f:
            f.write("{invalid json}")
        
        # 加载应该返回None
        data = save_mgr.load(0)
        assert data is None
        
        # 列表应该显示损坏
        slots = save_mgr.list_slots()
        assert "损坏" in slots[0]["name"]  # 包含"损坏"即可
    
    def test_overwrite_save(self, save_mgr):
        """测试覆盖存档"""
        # 创建Mock session
        session1 = Mock()
        session1.world_state.to_dict.return_value = {"test": 1}
        session1.world_state.game_time = "时间1"
        session1.world_state.world_divergence = 0.1
        session1.world_state.player_location = "地点1"
        session1.beat_count = 1
        session1.event_log = []
        session1.current_novel = "测试"
        session1.canon_manager.is_running.return_value = False
        
        session2 = Mock()
        session2.world_state.to_dict.return_value = {"test": 2}
        session2.world_state.game_time = "时间2"
        session2.world_state.world_divergence = 0.2
        session2.world_state.player_location = "地点2"
        session2.beat_count = 2
        session2.event_log = []
        session2.current_novel = "测试"
        session2.canon_manager.is_running.return_value = False
        
        # 保存两次到同一个槽位
        save_mgr.save(slot=0, session=session1, name="存档1")
        save_mgr.save(slot=0, session=session2, name="存档2")
        
        # 应该加载第二次的
        data = save_mgr.load(0)
        assert data["name"] == "存档2"
        assert data["beat_count"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
