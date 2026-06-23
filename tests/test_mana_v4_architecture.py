# -*- coding: utf-8 -*-
"""MaNA v4 架构完整测试套件（最终修复版）"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from typing import Any, Dict, List, Optional
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.manana.pipeline import MananaPipeline
from server.manana.config import MananaConfig, resolve_tier
from server.manana.base_agent import BaseAgent
from server.manana.schema import MananaSchema, SemanticValidator
from server.manana.pipeline_state import InteractionPair, apply_state_patch
from server.manana.providers import BaseProvider, ProviderFactory
from server.manana.memory import MemoryEntry, MemoryManager

# 导入所有 Agent 类（通过 __init__.py 统一导出，不依赖具体文件名）
from server.manana.agents import (
    ActionDirector, StateExtractor, PlanScorerAgent,
    RoleReflector, CharacterManager, LocationManager, MicroOracleAgent,
    MotivationEngine, DialogueWeaver, ConsistencyAuditor,
    ThreadManager, PlanSynthesizerAgent, ContinuityChecker,
    SceneDirector, SceneComposer, ReflectionOracle,
)


# ═══════════════════════════════════════════════
# 测试配置
# ═══════════════════════════════════════════════

TEST_CONFIG = {
    "providers": {
        "导演层": {"type": "ollama", "endpoint": "http://localhost:11434/api/chat", "model": "qwen2.5:14b"},
        "演员层": {"type": "ollama", "endpoint": "http://localhost:11434/api/chat", "model": "qwen2.5:7b"},
        "动作层": {"type": "ollama", "endpoint": "http://localhost:11434/api/chat", "model": "qwen2.5:3b"},
    },
    "features": {
        "multi_view": True, "best_of_3": True, "refinement": True,
        "dynamic_tier": True, "micro_oracle": True, "emergence_system": True,
        "continuity_check": True, "role_reflection": True, "memory_system": True,
    },
    "game": {"oracle_interval": 5},
}


# ═══════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════

@pytest.fixture
def config_yaml():
    return TEST_CONFIG.copy()


@pytest.fixture
def manana_config(config_yaml):
    return MananaConfig(yaml_dict=config_yaml)


@pytest.fixture
def mock_provider():
    provider = AsyncMock(spec=BaseProvider)
    provider.chat.return_value = {"ok": True, "content": '{"test": "mock"}', "tokens": 100}
    provider.get_model_name.return_value = "mock-model"
    provider.get_provider_name = Mock(return_value="mock")
    return provider


@pytest.fixture
def pipeline(config_yaml):
    return MananaPipeline(yaml_dict=config_yaml)


# ═══════════════════════════════════════════════
# 1. 配置管理测试
# ═══════════════════════════════════════════════

class TestMananaConfigFull:
    """完整的配置管理测试"""

    def test_init_with_yaml(self, config_yaml):
        config = MananaConfig(yaml_dict=config_yaml)
        assert config is not None

    def test_init_empty(self):
        config = MananaConfig()
        assert config is not None

    def test_resolve_tier_chinese(self):
        assert resolve_tier("导演层") == "strong"
        assert resolve_tier("演员层") == "medium"
        assert resolve_tier("动作层") == "light"

    def test_feature_enabled(self, manana_config):
        assert manana_config.is_feature_enabled("multi_view") is True

    def test_feature_disabled(self):
        config = MananaConfig(yaml_dict={"features": {"multi_view": False}})
        assert config.is_feature_enabled("multi_view") is False

    def test_oracle_interval(self, manana_config):
        assert manana_config.get_oracle_interval() == 5

    def test_refinement_limits(self, manana_config):
        limits = manana_config.get_refinement_limits()
        assert "max_warning_refine" in limits
        assert "max_fail_rewrite" in limits

    def test_best_of_3_config(self, manana_config):
        config = manana_config.get_best_of_3_config()
        assert "sample_count" in config

    def test_memory_config(self, manana_config):
        mem_config = manana_config.get_memory_config()
        assert isinstance(mem_config, dict)

    def test_hot_reload_config(self, manana_config):
        new_yaml = TEST_CONFIG.copy()
        new_yaml["features"]["multi_view"] = False
        manana_config.reload(new_yaml)
        assert manana_config.is_feature_enabled("multi_view") is False

    def test_dynamic_tier_config(self, manana_config):
        overrides = manana_config.get_tier_overrides(0.8)
        assert isinstance(overrides, dict)

    def test_vector_memory_config(self, manana_config):
        vm_config = manana_config.get_vector_memory_config()
        assert isinstance(vm_config, dict)


# ═══════════════════════════════════════════════
# 2. Pipeline 初始化测试
# ═══════════════════════════════════════════════

class TestMananaPipelineFull:
    """完整的 Pipeline 初始化测试"""

    def test_init(self, config_yaml):
        pipeline = MananaPipeline(yaml_dict=config_yaml)
        assert pipeline is not None

    @pytest.mark.asyncio
    async def test_is_ready(self, pipeline):
        result = pipeline.is_ready()
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════
# 3. BaseAgent 测试
# ═══════════════════════════════════════════════

class TestBaseAgentFull:
    """完整的 BaseAgent 测试"""

    def test_init(self):
        agent = ActionDirector()
        assert agent.agent_name == "ActionDirector"
        assert agent.model_tier == "light"

    def test_configure(self):
        agent = ActionDirector()
        mock_provider = Mock(spec=BaseProvider)
        agent.configure(mock_provider)
        assert agent._provider is not None

    @pytest.mark.asyncio
    async def test_run(self):
        agent = ActionDirector()
        mock_provider = AsyncMock(spec=BaseProvider)
        mock_provider.chat.return_value = {
            "ok": True,
            "content": '{"character_id": "test", "actions": []}',
            "tokens": 50,
        }
        agent.configure(mock_provider)
        
        input_data = {
            "character": {"char_id": "test", "name": "测试"},
            "interaction_context": {},
            "beat_summary": "测试",
            "player_action": "",
            "scene_tone": "平淡",
        }
        
        result = await agent.run(input_data)
        assert result.get("ok") is True


# ═══════════════════════════════════════════════
# 4. Schema 验证测试
# ═══════════════════════════════════════════════

class TestMananaSchemaFull:
    """完整的 Schema 验证测试"""

    def test_validate_director_output(self):
        data = {
            "beat_id": "beat_001",
            "narrative_mode": "exploration",
            "beat_summary": "测试",
            "featured_characters": [],
            "interaction_pairs": [],
            "unpaired_characters": [],
            "scene_tone": "平淡",
            "priority_thread_ids": [],
            "required_canon": [],
        }
        result = MananaSchema.validate_director_output(data)
        assert result["valid"] is True


# ═══════════════════════════════════════════════
# 5. 记忆系统测试
# ═══════════════════════════════════════════════

class TestMemorySystem:
    """记忆系统测试"""

    def test_memory_entry_creation(self):
        entry = MemoryEntry(
            agent_id="test_agent",
            content="测试记忆内容",
            timestamp=1,
            importance=7.0,
            memory_type="observation",
            tags=["测试", "记忆"],
            source="L2R1",
        )
        
        assert entry.agent_id == "test_agent"
        assert entry.importance == 7.0
        assert len(entry.tags) == 2

    def test_memory_manager_add(self):
        mm = MemoryManager()
        
        entry = MemoryEntry(
            agent_id="test",
            content="测试记忆",
            timestamp=1,
        )
        
        mm.add_memory(entry)
        
        assert "test" in mm.memory_stream
        assert len(mm.memory_stream["test"]) == 1

    def test_memory_manager_should_reflect(self):
        """测试累积重要性触发反思"""
        mm = MemoryManager(config={"reflection_threshold": "20"})
        
        # 添加高重要性记忆
        for i in range(5):
            entry = MemoryEntry(
                agent_id="test",
                content=f"重要记忆 {i}",
                timestamp=i,
                importance=5.0,  # 5 * 5 = 25 > 20
            )
            mm.add_memory(entry)
        
        # 检查是否触发反思
        assert mm.should_reflect("test") is True


# ═══════════════════════════════════════════════
# 6. 所有 Agent 的详细测试
# ═══════════════════════════════════════════════

class TestAllAgentsDetail:
    """所有 Agent 的详细测试"""

    def _create_mock_provider(self):
        """创建符合 BaseProvider 接口的 mock provider
        
        注意：BaseProvider 中 get_model_name() 和 get_provider_name() 是同步方法，
        而 chat() 是异步方法。不能使用 AsyncMock()，否则同步方法也会变成异步。
        """
        mock = Mock(spec=BaseProvider)
        
        # chat 是异步方法，需要设置 return_value
        mock.chat.return_value = {
            "ok": True,
            "content": '{"test": "mock"}',
            "tokens": 50,
        }
        
        # get_model_name 和 get_provider_name 是同步方法
        mock.get_model_name.return_value = "mock-model"
        mock.get_provider_name.return_value = "mock"
        
        return mock

    @pytest.mark.asyncio
    async def test_action_director(self):
        agent = ActionDirector()
        agent.configure(self._create_mock_provider())
        
        input_data = {
            "character": {"char_id": "test", "name": "测试"},
            "interaction_context": {},
            "beat_summary": "测试",
            "player_action": "",
            "scene_tone": "平淡",
        }
        
        result = await agent.run(input_data)
        assert result.get("ok") is True

    @pytest.mark.asyncio
    async def test_motivation_engine(self):
        agent = MotivationEngine()
        agent.configure(self._create_mock_provider())
        
        input_data = {
            "character": {"char_id": "test", "name": "测试"},
            "scene_summary": "测试",
            "player_action": "",
            "scene_tone": "平淡",
        }
        
        result = await agent.run(input_data)
        assert result is not None

    @pytest.mark.asyncio
    async def test_scene_director(self):
        agent = SceneDirector()
        agent.configure(self._create_mock_provider())
        
        input_data = {
            "scene_context": {
                "game_time": "测试",
                "location": {"name": "测试地点"},
                "player": {"action": "测试"},
                "characters": [],
                "active_threads": [],
                "recent_history": [],
            }
        }
        
        result = await agent.run(input_data)
        assert result is not None


# ═══════════════════════════════════════════════
# 主程序入口
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
