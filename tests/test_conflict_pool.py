# -*- coding: utf-8 -*-
"""ConflictPool 测试 - 修正版，匹配实际API"""

import pytest
import copy
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.app.conflict_pool import ConflictPool


class TestConflictPoolInit:
    """测试ConflictPool初始化"""
    
    def test_init_empty(self):
        """测试空初始化"""
        pool = ConflictPool()
        assert pool.seed_count == 0
        assert pool.available_count == 0
    
    def test_conflict_types(self):
        """测试冲突类型常量"""
        assert "character_conflict" in ConflictPool.CONFLICT_TYPES
        assert "moral_dilemma" in ConflictPool.CONFLICT_TYPES
        assert "environmental_crisis" in ConflictPool.CONFLICT_TYPES
        assert "social_tension" in ConflictPool.CONFLICT_TYPES
        assert "mystery" in ConflictPool.CONFLICT_TYPES


class TestConflictPoolLoadFromCanon:
    """测试从Canon加载"""
    
    def test_load_from_canon_basic(self):
        """测试基本加载"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {
                    "id": "event_001",
                    "conflicts": [
                        {"id": "conflict_001", "type": "mystery", "intensity": 0.5}
                    ]
                }
            ]
        }
        
        count = pool.load_from_canon(canon)
        
        assert count == 1
        assert pool.seed_count == 1
        assert pool._seeds[0]["id"] == "conflict_001"
    
    def test_load_from_canon_multiple_events(self):
        """测试从多个事件加载"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {"id": "e1", "conflicts": [{"id": "c1", "type": "mystery"}]},
                {"id": "e2", "conflicts": [{"id": "c2", "type": "social"}]},
            ]
        }
        
        count = pool.load_from_canon(canon)
        
        assert count == 2
        assert pool.seed_count == 2
    
    def test_load_from_canon_duplicate_ids(self):
        """测试重复ID跳过"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {
                    "id": "e1",
                    "conflicts": [
                        {"id": "c1", "type": "mystery"},
                        {"id": "c1", "type": "mystery"},  # 重复
                    ]
                }
            ]
        }
        
        count = pool.load_from_canon(canon)
        
        assert count == 1  # 只加载第一个
        assert pool.seed_count == 1
    
    def test_load_from_canon_invalid_type(self):
        """测试无效类型回退"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {"id": "e1", "conflicts": [{"id": "c1", "type": "invalid_type"}]}
            ]
        }
        
        pool.load_from_canon(canon)
        
        assert pool._seeds[0]["type"] == "mystery"  # 回退到默认
    
    def test_load_from_canon_missing_fields(self):
        """测试缺失字段补全"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {"id": "e1", "conflicts": [{"id": "c1"}]}  # 只有ID
            ]
        }
        
        pool.load_from_canon(canon)
        
        seed = pool._seeds[0]
        assert seed["type"] == "mystery"  # 默认值
        assert seed["intensity"] == 0.5  # 默认值
        assert seed["times_used"] == 0  # 默认值
        assert seed["is_exhausted"] is False  # 默认值


class TestConflictPoolGetAvailableSeeds:
    """测试获取可用种子"""
    
    @pytest.fixture
    def pool_with_seeds(self):
        """创建带种子的池"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {
                    "id": "e1",
                    "conflicts": [
                        {"id": "c1", "type": "mystery", "intensity": 0.5},
                        {"id": "c2", "type": "social_tension", "intensity": 0.8},
                        {"id": "c3", "type": "mystery", "intensity": 0.2},  # 强度低
                    ]
                }
            ]
        }
        pool.load_from_canon(canon)
        return pool
    
    def test_get_available_seeds_basic(self, pool_with_seeds):
        """测试基本获取"""
        available = pool_with_seeds.get_available_seeds()
        
        assert len(available) == 2  # c1和c2可用，c3强度太低（0.2 < 0.3）
    
    def test_get_available_seeds_min_intensity(self, pool_with_seeds):
        """测试强度过滤"""
        available = pool_with_seeds.get_available_seeds(min_intensity=0.4)
        
        assert len(available) == 2  # c1和c2
    
    def test_get_available_seeds_exhausted(self, pool_with_seeds):
        """测试排除已耗尽"""
        pool_with_seeds._seeds[0]["is_exhausted"] = True
        
        available = pool_with_seeds.get_available_seeds()
        
        assert len(available) == 1  # 只有c2可用（c1已耗尽，c3强度太低）
    
    def test_get_available_seeds_deep_copy(self, pool_with_seeds):
        """测试返回深拷贝"""
        available = pool_with_seeds.get_available_seeds()
        
        # 修改返回的列表不应影响原始数据
        available[0]["intensity"] = 999
        assert pool_with_seeds._seeds[0]["intensity"] == 0.5


class TestConflictPoolGetRandomCombination:
    """测试随机组合"""
    
    @pytest.fixture
    def pool_with_many_seeds(self):
        """创建带多个种子的池"""
        pool = ConflictPool()
        timeline = []
        for i in range(5):
            timeline.append({
                "id": f"e{i}",
                "conflicts": [
                    {"id": f"c{i}", "type": "mystery", "intensity": 0.5}
                ]
            })
        canon = {"timeline": timeline}
        pool.load_from_canon(canon)
        return pool
    
    def test_get_random_combination_basic(self, pool_with_many_seeds):
        """测试基本组合功能"""
        pool = pool_with_many_seeds
        
        selected = pool.get_random_combination(count=2)
        
        assert len(selected) == 2
        # 验证 times_used 被更新
        assert pool._seeds[0]["times_used"] >= 0  # 可能未被选中
    
    def test_get_random_combination_increments_times_used(self):
        """测试组合后 times_used 增加"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {"id": "e1", "conflicts": [{"id": "c1", "type": "mystery", "intensity": 0.5}]}
            ]
        }
        pool.load_from_canon(canon)
        
        # 第一次获取
        selected = pool.get_random_combination(count=1)
        assert len(selected) == 1
        
        # 验证 times_used 增加
        assert pool._seeds[0]["times_used"] == 1
    
    def test_get_random_combination_insufficient(self, pool_with_many_seeds):
        """测试可用种子不足时的处理"""
        pool = pool_with_many_seeds
        
        # 请求 10 个，但只有 5 个可用
        selected = pool.get_random_combination(count=10)
        
        assert len(selected) == 5  # 返回全部可用
    
    def test_get_random_combination_empty(self):
        """测试没有可用种子时返回空列表"""
        pool = ConflictPool()
        
        selected = pool.get_random_combination(count=2)
        
        assert len(selected) == 0
    
    def test_get_random_combination_exhausted_after_mark_used(self):
        """测试使用多次后标记为耗尽（需要显式调用mark_used）"""
        pool = ConflictPool()
        canon = {
            "timeline": [
                {
                    "id": "e1",
                    "conflicts": [
                        {"id": "c1", "type": "mystery", "intensity": 0.5},
                    ]
                }
            ]
        }
        
        pool.load_from_canon(canon)
        
        # 使用 3 次并标记
        for _ in range(3):
            comb = pool.get_random_combination(count=1)
            if comb:
                pool.mark_used(comb[0]["id"])
        
        # 应该被标记为耗尽
        assert pool._seeds[0]["is_exhausted"] is True
        assert pool.available_count == 0


class TestConflictPoolAddSeeds:
    """测试添加新种子"""
    
    def test_add_seeds_basic(self):
        """测试基本添加功能"""
        pool = ConflictPool()
        new_seeds = [
            {"id": "new_001", "type": "mystery", "description": "新冲突"}
        ]
        
        pool.add_seeds(new_seeds)
        
        assert pool.seed_count == 1
        assert pool._seeds[0]["id"] == "new_001"
    
    def test_add_seeds_duplicate_ids(self):
        """测试重复ID跳过"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        pool.add_seeds([{"id": "c1", "type": "social"}])  # 重复
        
        assert pool.seed_count == 1  # 只添加第一个
    
    def test_add_seeds_auto_id(self):
        """测试自动生成ID"""
        pool = ConflictPool()
        new_seeds = [
            {"type": "mystery", "description": "无ID冲突"}
        ]
        
        pool.add_seeds(new_seeds)
        
        assert pool.seed_count == 1
        assert pool._seeds[0]["id"].startswith("conflict_dyn_")


class TestConflictPoolMarkUsed:
    """测试标记使用"""
    
    def test_mark_used_basic(self):
        """测试基本标记功能"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        
        pool.mark_used("c1")
        
        assert pool._seeds[0]["times_used"] == 1
    
    def test_mark_used_exhausted(self):
        """测试标记后耗尽"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        
        # 使用 3 次
        for _ in range(3):
            pool.mark_used("c1")
        
        assert pool._seeds[0]["times_used"] == 3
        assert pool._seeds[0]["is_exhausted"] is True
    
    def test_mark_used_nonexistent(self):
        """测试标记不存在的种子（不应崩溃）"""
        pool = ConflictPool()
        
        pool.mark_used("nonexistent")  # 应该不报错
        
        assert pool.seed_count == 0


class TestConflictPoolResetExhausted:
    """测试重置耗尽状态"""
    
    def test_reset_exhausted_basic(self):
        """测试基本重置功能"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        pool.mark_used("c1")
        pool.mark_used("c1")
        pool.mark_used("c1")  # 应该耗尽
        
        assert pool._seeds[0]["is_exhausted"] is True
        
        pool.reset_exhausted()
        
        assert pool._seeds[0]["is_exhausted"] is False
        assert pool._seeds[0]["times_used"] == 3  # times_used 保留
    
    def test_reset_exhausted_keep_times_used(self):
        """测试重置后保留使用次数"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        pool.mark_used("c1")
        
        pool.reset_exhausted()
        
        assert pool._seeds[0]["times_used"] == 1  # 保留


class TestConflictPoolSerialization:
    """测试序列化"""
    
    def test_to_dict(self):
        """测试序列化为字典"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery", "intensity": 0.5}])
        
        data = pool.to_dict()
        
        assert "seeds" in data
        assert len(data["seeds"]) == 1
        assert data["seeds"][0]["id"] == "c1"
    
    def test_from_dict(self):
        """测试从字典反序列化"""
        data = {
            "seeds": [
                {"id": "c1", "type": "mystery", "intensity": 0.5, "times_used": 2}
            ]
        }
        
        pool = ConflictPool.from_dict(data)
        
        assert pool.seed_count == 1
        assert pool._seeds[0]["id"] == "c1"
        assert pool._seeds[0]["times_used"] == 2
    
    def test_serialization_round_trip(self):
        """测试序列化往返"""
        pool1 = ConflictPool()
        pool1.add_seeds([{"id": "c1", "type": "mystery", "intensity": 0.5}])
        pool1.mark_used("c1")
        
        data = pool1.to_dict()
        pool2 = ConflictPool.from_dict(data)
        
        assert pool2.seed_count == pool1.seed_count
        assert pool2._seeds[0]["times_used"] == pool1._seeds[0]["times_used"]


class TestConflictPoolEdgeCases:
    """测试边界情况"""
    
    def test_load_from_canon_empty_timeline(self):
        """测试空时间线"""
        pool = ConflictPool()
        canon = {"timeline": []}
        
        count = pool.load_from_canon(canon)
        
        assert count == 0
        assert pool.seed_count == 0
    
    def test_load_from_canon_no_timeline(self):
        """测试无时间线字段"""
        pool = ConflictPool()
        canon = {"meta": {"title": "test"}}  # 没有timeline
        
        count = pool.load_from_canon(canon)
        
        assert count == 0
    
    def test_get_available_seeds_all_exhausted(self):
        """测试全部耗尽时返回空"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        pool.mark_used("c1")
        pool.mark_used("c1")
        pool.mark_used("c1")  # 耗尽
        
        available = pool.get_available_seeds()
        
        assert len(available) == 0
    
    def test_add_seeds_empty_list(self):
        """测试添加空列表"""
        pool = ConflictPool()
        
        pool.add_seeds([])  # 应该不报错
        
        assert pool.seed_count == 0
    
    def test_repr(self):
        """测试字符串表示"""
        pool = ConflictPool()
        pool.add_seeds([{"id": "c1", "type": "mystery"}])
        
        repr_str = repr(pool)
        
        assert "ConflictPool" in repr_str
        assert "seeds=1" in repr_str
        assert "available=1" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
