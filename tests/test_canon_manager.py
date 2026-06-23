# -*- coding: utf-8 -*-
"""CanonManager 测试 v2 - 正确配置Mock"""

import pytest
from unittest.mock import Mock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.data.canon_manager import CanonManager


class TestCanonManagerCreate:
    """测试创建和加载"""
    
    def test_create_success(self):
        """测试成功创建"""
        mock_storage = Mock()
        mock_storage.create_running_canon.return_value = True
        mock_storage.load_running_canon.return_value = {
            "meta": {"title": "test"},
            "characters": [],
            "locations": []
        }
        
        cm = CanonManager(storage=mock_storage)
        result = cm.create_running_canon("novel/canon_test.json")
        
        assert result is True
        assert cm._current_novel == "test"
        assert cm.is_running() is True


class TestCanonManagerCRUD:
    """测试CRUD操作"""
    
    @pytest.fixture
    def cm(self):
        """创建带Mock的CanonManager"""
        mock_storage = Mock()
        # 关键：明确设置 get_entry_count 返回整数
        mock_storage.get_entry_count = MagicMock(return_value=0)
        
        cm = CanonManager(storage=mock_storage)
        cm._running_canon = {
            "meta": {"title": "test"},
            "characters": [],
            "locations": []
        }
        cm._current_novel = "test"
        return cm
    
    def test_add_character(self, cm):
        """测试添加角色"""
        data = {"name": "测试角色", "role": "protagonist"}
        
        success, canon, msg = cm.save_canon_entry(
            section="characters",
            action="create",
            entry_data=data
        )
        
        assert success is True
        assert msg.startswith("char_")
        assert len(msg) == 13  # "char_" (5) + 8 hex
        import re
        assert re.match(r'^char_[0-9a-f]{8}$', msg), f"UUID 格式不匹配: {msg}"
        assert len(cm._running_canon["characters"]) == 1
    
    def test_update_character(self, cm):
        """测试更新角色"""
        cm._running_canon["characters"] = [{
            "id": "char_001",
            "name": "原名字"
        }]
        
        success, canon, msg = cm.save_canon_entry(
            section="characters",
            action="update",
            entry_data={"name": "新名字"},
            entry_id="char_001"
        )
        
        assert success is True
        assert cm._running_canon["characters"][0]["name"] == "新名字"
    
    def test_mark_character_dead(self, cm):
        """测试标记角色死亡"""
        cm._running_canon["characters"] = [{
            "id": "char_001",
            "name": "测试",
            "status": "alive"
        }]
        
        success, canon, msg = cm.mark_character_dead("char_001", {
            "death_location": "战场",
            "death_time": "第三日"
        })
        
        assert success is True
        assert cm._running_canon["characters"][0]["status"] == "dead"


class TestCanonManagerID:
    """测试ID生成"""
    
    def test_generate_id_first(self):
        """测试生成第一个ID（UUID 格式）"""
        mock_storage = Mock()
        mock_storage.get_entry_count = MagicMock(return_value=0)
        
        cm = CanonManager(storage=mock_storage)
        cm._running_canon = {"meta": {"title": "test"}, "characters": [], "locations": []}
        cm._current_novel = "test"
        
        data = {"name": "测试"}
        success, canon, msg = cm.save_canon_entry(
            section="characters",
            action="create",
            entry_data=data
        )
        
        # UUID 格式: char_ + 8-digit hex
        assert msg.startswith("char_")
        assert len(msg) == 13  # "char_" (6) + 8 hex chars = 14? No. "char_" = 5. Wait: "char_" = 5 chars? Let me count: c-h-a-r-_ = 5, plus 8 hex = 13 total
        import re
        assert re.match(r'^char_[0-9a-f]{8}$', msg), f"UUID 格式不匹配: {msg}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
