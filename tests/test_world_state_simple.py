# -*- coding: utf-8 -*-
"""WorldState 简化测试 - 避免编码问题"""

import pytest
from server.app.world_state import WorldState


class TestWorldStateBasic:
    """基础功能测试"""
    
    def test_initial_state(self):
        """测试初始状态"""
        ws = WorldState()
        assert ws.time_index == 0
        assert isinstance(ws.game_time, str)
        assert len(ws.game_time) > 0
    
    def test_advance_time(self):
        """测试时间推进"""
        ws = WorldState()
        
        # 推进1拍
        ws.advance_time()
        assert ws.time_index == 1
        
        # 再推进5拍
        for _ in range(5):
            ws.advance_time()
        assert ws.time_index == 6
    
    def test_to_dict(self):
        """测试序列化"""
        ws = WorldState()
        ws.player_location = "测试地点"
        
        data = ws.to_dict()
        assert isinstance(data, dict)
        assert data["version"] == 2
        assert data["player_location"] == "测试地点"
    
    def test_from_dict(self):
        """测试反序列化"""
        data = {
            "version": 2,
            "game_time": "测试时间",
            "time_index": 50,
            "player_location": "测试地点"
        }
        
        ws = WorldState.from_dict(data)
        assert ws.game_time == "测试时间"
        assert ws.time_index == 50
        assert ws.player_location == "测试地点"
    
    def test_apply_patch(self):
        """测试应用补丁"""
        ws = WorldState()
        
        # 应用位置补丁（正确键名：player_location）
        ws.apply_patch({"player_location": "新地点"})
        assert ws.player_location == "新地点"
        
        # 应用偏离度补丁
        ws.apply_patch({"divergence_delta": 0.5})
        assert abs(ws.world_divergence - 0.5) < 0.01


class TestWorldStateMemory:
    """记忆系统测试"""
    
    def test_add_scene_memory(self):
        """测试场景记忆"""
        ws = WorldState()
        
        ws.add_scene_memory("事件1")
        ws.add_scene_memory("事件2")
        
        assert len(ws.scene_memory) == 2
        assert ws.scene_memory[-1] == "事件2"
    
    def test_memory_limit(self):
        """测试记忆上限"""
        ws = WorldState()
        
        # 添加超过5条记忆
        for i in range(7):
            ws.add_scene_memory(f"事件{i}")
        
        # 应该只保留最新的5条
        assert len(ws.scene_memory) == 5


class TestWorldStateDivergence:
    """偏离度测试"""
    
    def test_divergence_range(self):
        """测试偏离度范围"""
        ws = WorldState()
        
        # 正向偏离
        ws.apply_patch({"divergence_delta": 0.5})
        assert ws.world_divergence >= 0.0
        
        # 负向偏离
        ws.apply_patch({"divergence_delta": -0.3})
        assert ws.world_divergence >= -1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
