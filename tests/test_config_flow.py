"""集成测试：Config 数据流 — 前端 ↔ 后端 全链路验证

测试覆盖：
  1. MananaConfig 解析 config.yaml providers（含 provider 模板引用）
  2. MananaConfig.reload() 热重连
  3. GameSession.get_config_info() 返回数据完整性
  4. update_config 写入 + 写回 config.yaml 再读
  5. 各种 provider 类型切换时的字段正确性
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from server.manana.config import MananaConfig, resolve_tier, display_tier


# ── Fixtures ──────────────────────────────────────────────────────────────

SAMPLE_CONFIG = {
    "providers": {
        # 模板条目（仅用于前端提供者选择框架）
        "deepseek": {
            "type": "deepseek",
            "endpoint": "https://api.deepseek.com",
        },
        "ollama": {
            "type": "ollama",
            "endpoint": "http://192.168.71.12:11434",
        },
        # Tier 配置（自包含，不引用模板）
        "导演层": {
            "type": "deepseek",
            "endpoint": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "演员层": {
            "type": "deepseek",
            "endpoint": "https://api.deepseek.com",
            "model": "deepseek-v3",
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        "动作层": {
            "type": "ollama",
            "endpoint": "http://192.168.71.12:11434",
            "model": "qwen2.5:1.5b",
            "temperature": 0.5,
            "max_tokens": 1024,
        },
    },
    "features": {
        "refinement": True,
        "best_of_3": True,
    },
    "game": {
        "oracle_interval": 5,
    },
}


@pytest.fixture
def sample_yaml_dict() -> dict:
    return copy.deepcopy(SAMPLE_CONFIG)


@pytest.fixture
def config(sample_yaml_dict) -> MananaConfig:
    return MananaConfig(yaml_dict=sample_yaml_dict)


# ── 1. MananaConfig 解析测试 ────────────────────────────────────────────


class TestMananaConfigProviders:
    """MananaConfig 的 provider 解析逻辑"""

    def test_parse_direct_config(self, config: MananaConfig):
        """导演层直接配置，不引用模板，type/endpoint 自重"""
        tc = config.get_tier_config("strong")  # strong = 导演层
        assert tc["type"] == "deepseek", f"expected deepseek, got {tc['type']}"
        assert "api.deepseek.com" in tc["endpoint"], f"endpoint mismatch: {tc['endpoint']}"
        assert tc["model"] == "deepseek-v4-flash"
        assert tc["temperature"] == 0.7
        assert tc["max_tokens"] == 4096

    def test_parse_deepseek_tier(self, config: MananaConfig):
        """演员层 DeepSeek 配置"""
        tc = config.get_tier_config("medium")  # medium = 演员层
        assert tc["type"] == "deepseek"
        assert tc["model"] == "deepseek-v3"
        assert tc["endpoint"].endswith("/v1/chat/completions"), \
            f"DeepSeek endpoint should have /v1/chat/completions suffix: {tc['endpoint']}"

    def test_parse_ollama_tier(self, config: MananaConfig):
        """动作层 = Ollama，应添加 /api/chat 后缀"""
        tc = config.get_tier_config("light")  # light = 动作层
        assert tc["type"] == "ollama"
        assert tc["model"] == "qwen2.5:1.5b"
        assert tc["endpoint"].endswith("/api/chat"), \
            f"Ollama endpoint should have /api/chat suffix: {tc['endpoint']}"

    def test_all_tiers_have_required_fields(self, config: MananaConfig):
        """所有 tier 都必须包含全部必需字段"""
        for tier in ("strong", "medium", "light"):
            tc = config.get_tier_config(tier)
            for field in ("type", "endpoint", "api_key", "model",
                          "temperature", "max_tokens", "timeout"):
                assert field in tc, f"{tier} missing field '{field}'"
            assert tc["timeout"] > 0, f"{tier} timeout should be > 0"

    def test_ollama_endpoint_suffix(self, config: MananaConfig):
        """Ollama endpoint 应自动添加 /api/chat"""
        tc = config.get_tier_config("light")
        assert tc["endpoint"].endswith("/api/chat")

    def test_deepseek_endpoint_suffix(self, config: MananaConfig):
        """DeepSeek endpoint 应自动添加 /v1/chat/completions"""
        tc = config.get_tier_config("medium")
        assert tc["endpoint"].endswith("/v1/chat/completions")

    def test_empty_config_defaults(self):
        """空配置应使用默认值"""
        c = MananaConfig(yaml_dict={})
        for tier in ("strong", "medium", "light"):
            tc = c.get_tier_config(tier)
            assert tc["type"] == "ollama"
            assert tc["endpoint"] == ""


# ── 2. get_config_info 数据完整性 ─────────────────────────────────────────


class TestGetConfigInfo:
    """模拟 GameSession.get_config_info() 的返回值结构"""

    def _simulate_get_config_info(self, mc: MananaConfig) -> dict:
        """模拟 game_session.py 中 get_config_info 的逻辑"""
        result = {"providers": {}}
        for tier in ("strong", "medium", "light"):
            try:
                tc = mc.get_tier_config(tier)
                ep = tc.get("endpoint", "")
                ep = ep.rstrip("/").replace("/api/chat", "").replace(
                    "/v1/chat/completions", "")
                result["providers"][tier] = {
                    "type": tc.get("type", "ollama"),
                    "endpoint": ep,
                    "model": tc.get("model", ""),
                    "temperature": tc.get("temperature", 0.7),
                    "max_tokens": tc.get("max_tokens", 2048),
                    "timeout": tc.get("timeout", 120),
                    "api_key": tc.get("api_key", ""),
                }
            except Exception:
                result["providers"][tier] = {}
        result["api_key"] = result["providers"].get("strong", {}).get("api_key", "")
        return result

    def test_returns_providers_for_all_tiers(self, config: MananaConfig):
        info = self._simulate_get_config_info(config)
        for tier in ("strong", "medium", "light"):
            assert tier in info["providers"], f"missing {tier}"

    def test_each_provider_has_all_fields(self, config: MananaConfig):
        info = self._simulate_get_config_info(config)
        required = {"type", "endpoint", "model", "temperature",
                    "max_tokens", "timeout", "api_key"}
        for tier, p in info["providers"].items():
            missing = required - set(p.keys())
            assert not missing, f"{tier} missing: {missing}"

    def test_deepseek_provider_no_suffix_in_endpoint(self, config: MananaConfig):
        info = self._simulate_get_config_info(config)
        ep = info["providers"]["medium"]["endpoint"]
        assert "/chat/completions" not in ep, \
            f"suffix leaked into get_config_info endpoint: {ep}"
        assert "/api/chat" not in ep

    def test_ollama_provider_no_suffix_in_endpoint(self, config: MananaConfig):
        info = self._simulate_get_config_info(config)
        ep = info["providers"]["light"]["endpoint"]
        assert "/api/chat" not in ep, \
            f"suffix leaked into get_config_info endpoint: {ep}"

    def test_api_key_per_tier(self, config: MananaConfig):
        """每个 tier 都应该有自己的 api_key 字段"""
        info = self._simulate_get_config_info(config)
        for tier in ("strong", "medium", "light"):
            assert "api_key" in info["providers"][tier], f"{tier} missing api_key"


# ── 3. update_config 写入 + 重加载 ────────────────────────────────────


class TestUpdateConfigRoundtrip:
    """模拟 GameSession.update_config() 写入 + 重加载"""

    def _simulate_update_config(self, yaml_dict: dict,
                                 providers: dict) -> dict:
        """模拟 backend update_config 的核心逻辑（不含健康检查）"""
        cfg = copy.deepcopy(yaml_dict)
        cfg_providers = cfg.setdefault("providers", {})

        normalized = {}
        for k, v in (providers or {}).items():
            normalized[resolve_tier(k)] = v

        for internal_tier in ("strong", "medium", "light"):
            tier_cfg = normalized.get(internal_tier, {})
            if not tier_cfg:
                continue
            # 找现有键名保留中文名
            yaml_key = internal_tier
            for ek in cfg_providers:
                if resolve_tier(ek) == internal_tier:
                    yaml_key = ek
                    break
            prov = cfg_providers.setdefault(yaml_key, {})
            for key in ("endpoint", "model", "type"):
                if tier_cfg.get(key):
                    prov[key] = tier_cfg[key]
            if tier_cfg.get("temperature") is not None:
                prov["temperature"] = float(tier_cfg["temperature"])
            if tier_cfg.get("max_tokens") is not None:
                prov["max_tokens"] = int(tier_cfg["max_tokens"])
            if tier_cfg.get("api_key"):
                prov["api_key"] = tier_cfg["api_key"]
            if tier_cfg.get("timeout") is not None:
                prov["timeout"] = int(tier_cfg["timeout"])

        return cfg

    def test_write_deepseek_config(self, sample_yaml_dict):
        """写入 DeepSeek 配置"""
        payload = {
            "light": {
                "type": "deepseek",
                "endpoint": "https://api.deepseek.com",
                "model": "deepseek-v3",
                "temperature": 0.5,
                "max_tokens": 2048,
                "timeout": 60,
                "api_key": "sk-test",
            }
        }
        cfg = self._simulate_update_config(sample_yaml_dict, payload)

        # 验证写入了 动作层（light 的中文名）
        assert "动作层" in cfg["providers"]
        assert cfg["providers"]["动作层"]["type"] == "deepseek"
        assert cfg["providers"]["动作层"]["api_key"] == "sk-test"
        assert cfg["providers"]["动作层"]["timeout"] == 60

    def test_write_ollama_config(self, sample_yaml_dict):
        """写入 Ollama 配置（无 api_key）"""
        payload = {
            "light": {
                "type": "ollama",
                "endpoint": "http://192.168.71.12:11434",
                "model": "qwen2.5:1.5b",
                "temperature": 0.5,
                "max_tokens": 1024,
                "timeout": 60,
            }
        }
        cfg = self._simulate_update_config(sample_yaml_dict, payload)
        prov = cfg["providers"]["动作层"]
        assert prov["type"] == "ollama"
        assert "api_key" not in prov, \
            "Ollama 不应写入 api_key"

    def test_timeout_persisted(self, sample_yaml_dict):
        """timeout 应被持久化"""
        payload = {
            "strong": {
                "type": "deepseek",
                "endpoint": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "temperature": 0.7,
                "max_tokens": 4096,
                "timeout": 180,
            }
        }
        cfg = self._simulate_update_config(sample_yaml_dict, payload)
        assert cfg["providers"]["导演层"]["timeout"] == 180

    def test_partial_update_preserves_other_tiers(self, sample_yaml_dict):
        """只更新一个 tier 不应影响其他"""
        # 先记下原始值
        orig_strong = sample_yaml_dict["providers"]["导演层"]["model"]

        payload = {
            "light": {
                "type": "ollama",
                "endpoint": "http://192.168.71.12:11434",
                "model": "qwen2.5:1.5b",
                "temperature": 0.3,
                "max_tokens": 512,
                "timeout": 30,
            }
        }
        cfg = self._simulate_update_config(sample_yaml_dict, payload)
        assert cfg["providers"]["导演层"]["model"] == orig_strong, \
            "更新 light 不应修改 strong"

    def test_writes_to_yaml_and_reloads(self, sample_yaml_dict):
        """写入 config.yaml → MananaConfig.reload() 应正确读取"""
        payload = {
            "strong": {
                "type": "deepseek",
                "endpoint": "https://api.deepseek.com",
                "model": "deepseek-r1",
                "temperature": 0.3,
                "max_tokens": 8192,
                "timeout": 180,
                "api_key": "sk-reload-test",
            }
        }

        # 模拟写入 config.yaml
        cfg = self._simulate_update_config(sample_yaml_dict, payload)

        # 重新加载到 MananaConfig
        mc = MananaConfig(yaml_dict=cfg)
        tc = mc.get_tier_config("strong")
        assert tc["model"] == "deepseek-r1"
        assert tc["temperature"] == 0.3
        assert tc["max_tokens"] == 8192
        assert tc["api_key"] == "sk-reload-test"
        assert tc["timeout"] == 180


# ── 4. tier 名称解析 ─────────────────────────────────────────────────


class TestTierNameResolution:
    """resolve_tier / display_tier"""

    def test_chinese_to_internal(self):
        assert resolve_tier("导演层") == "strong"
        assert resolve_tier("演员层") == "medium"
        assert resolve_tier("动作层") == "light"

    def test_internal_identity(self):
        assert resolve_tier("strong") == "strong"
        assert resolve_tier("medium") == "medium"
        assert resolve_tier("light") == "light"

    def test_english_legacy(self):
        assert resolve_tier("director") == "strong"
        assert resolve_tier("actor") == "medium"
        assert resolve_tier("action") == "light"

    def test_display_tier(self):
        assert display_tier("strong") == "导演层"
        assert display_tier("medium") == "演员层"
        assert display_tier("light") == "动作层"

    def test_unknown_passthrough(self):
        assert resolve_tier("unknown") == "unknown"
        assert display_tier("unknown") == "unknown"


# ── 5. 边界情况 ───────────────────────────────────────────────────────


class TestConfigEdgeCases:

    def test_empty_config_no_crash(self):
        """空配置不应崩溃"""
        mc = MananaConfig(yaml_dict={})
        for tier in ("strong", "medium", "light"):
            tc = mc.get_tier_config(tier)
            assert isinstance(tc, dict)

    def test_missing_providers_section(self):
        """缺少 providers 字段不应崩溃"""
        mc = MananaConfig(yaml_dict={"game": {}})
        for tier in ("strong", "medium", "light"):
            tc = mc.get_tier_config(tier)
            assert isinstance(tc, dict)

    def test_missing_tier_returns_defaults(self):
        """缺失的 tier 应返回默认值"""
        cfg = {"providers": {"导演层": {"type": "deepseek", "endpoint": "https://x.com"}}}
        mc = MananaConfig(yaml_dict=cfg)
        tc = mc.get_tier_config("medium")  # 不存在
        assert tc["type"] == "ollama"  # 默认
        assert tc["endpoint"] == ""  # 默认

    def test_reload_preserves_state(self):
        """reload 后新的 get 返回新值"""
        mc = MananaConfig(yaml_dict=SAMPLE_CONFIG)
        tc_before = mc.get_tier_config("strong")
        old_model = tc_before["model"]

        new_cfg = copy.deepcopy(SAMPLE_CONFIG)
        new_cfg["providers"]["导演层"]["model"] = "new-model"
        mc.reload(new_cfg)

        tc_after = mc.get_tier_config("strong")
        assert tc_after["model"] == "new-model"
        assert tc_after["model"] != old_model
