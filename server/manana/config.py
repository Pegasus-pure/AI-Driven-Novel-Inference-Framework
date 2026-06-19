"""MaNA v4 Configuration loader.

Configuration is loaded from a YAML dict (passed via config.yaml → MananaPipeline).
No INI file reading is performed.

Provides access to:
  - Three-tier provider configs (导演层 / 演员层 / 动作层)
  - Retry / Oracle interval settings
  - v4 feature flags (refinement, best_of_3, multi_view, etc.)
  - Dynamic tier / complexity thresholds
"""

import configparser
from typing import Any
import warnings


# Tier name mapping: 中文名 → 内部标识
# config.yaml 中使用中文层名，内部代码使用 strong/medium/light
TIER_MAP: dict[str, str] = {
    "导演层": "strong",
    "演员层": "medium",
    "动作层": "light",
    # 向后兼容旧名（内部标识）
    "strong": "strong",
    "medium": "medium",
    "light": "light",
    # 向后兼容 config.yaml 中的英文层名（v3 及更早版本）
    "director": "strong",
    "actor": "medium",
    "action": "light",
}

# 内部标识 → 中文名（反向查找）
_INVERSE_TIER_MAP: dict[str, str] = {v: k for k, v in TIER_MAP.items() if k in ("导演层", "演员层", "动作层")}
_INTERNAL_TIERS = ("strong", "medium", "light")


def resolve_tier(name: str) -> str:
    """将层名（中文或旧名）解析为内部标识。"""
    return TIER_MAP.get(name, name)


def display_tier(internal: str) -> str:
    """将内部标识转换为用户友好的中文层名。"""
    return _INVERSE_TIER_MAP.get(internal, internal)


class MananaConfig:
    """MaNA pipeline configuration loaded from a YAML dict.

    Configuration is populated via _populate_from_yaml() from a dict
    provided by the caller (originally from config.yaml).

    ⚠️ 当前内部使用 ConfigParser 作为中间表示层。
       Phase 2 中期将移除 ConfigParser，改为直接访问 self._cfg_dict。
       届时 _populate_from_yaml, set_tier_config, get_model_config 等均需改为 dict 操作。
    """

    def __init__(self, yaml_dict: dict = None) -> None:
        """Initialize config loader.

        Args:
            yaml_dict: Dict from config.yaml (preferred). If None, an empty
                       config is used and all getters return their defaults.
        """
        self._config: configparser.ConfigParser = configparser.ConfigParser()
        self._loaded: bool = False

        if yaml_dict is not None:
            self._populate_from_yaml(yaml_dict)
        else:
            self._populate_from_yaml({})
        self._loaded = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _populate_from_yaml(self, cfg: dict) -> None:
        """直接从 config.yaml 的字典构建 ConfigParser，无需 INI 文件"""
        cfg = cfg or {}
        providers = cfg.get("providers", {}) or {}
        features = cfg.get("features", {}) or {}
        game = cfg.get("game", {}) or {}

        # 全局
        self._config.add_section("global")
        self._config.set("global", "config_version", "2")

        # 三级 Provider
        # config.yaml 使用中文层名（导演层/演员层/动作层），映射为 provider_strong 等 section
        tier_keys = {resolve_tier(k): v for k, v in providers.items()}
        for internal_tier in _INTERNAL_TIERS:
            section = f"provider_{internal_tier}"
            self._config.add_section(section)
            t = tier_keys.get(internal_tier, {}) or {}
            prov_type = t.get("type", "ollama")
            endpoint = t.get("endpoint", "http://localhost:11434")
            if prov_type == "ollama":
                endpoint = endpoint.rstrip("/") + "/api/chat"
            else:
                endpoint = endpoint.rstrip("/") + "/v1/chat/completions"
            self._config.set(section, "type", prov_type)
            self._config.set(section, "endpoint", endpoint)
            self._config.set(section, "api_key", str(t.get("api_key", "")))
            self._config.set(section, "model", str(t.get("model", "")))
            self._config.set(section, "temperature", str(t.get("temperature", 0.7)))
            self._config.set(section, "max_tokens", str(t.get("max_tokens", 2048)))
            self._config.set(section, "timeout", str(t.get("timeout", 120)))

        # 功能开关
        self._config.add_section("v4")
        self._config.set("v4", "enabled", "true")
        for feat in ("multi_view", "dynamic_tier", "micro_oracle", "semantic_selection",
                      "emergence_system", "continuity_check", "role_reflection",
                      "memory_system"):
            self._config.add_section(feat)
            self._config.set(feat, "enabled", "true" if features.get(feat, False) else "false")

        # refinement（含子键）
        self._config.add_section("refinement")
        self._config.set("refinement", "enabled", "true" if features.get("refinement", True) else "false")
        self._config.set("refinement", "max_warning_refine", "1")
        self._config.set("refinement", "max_fail_rewrite", "2")

        # best_of_3（含子键）
        self._config.add_section("best_of_3")
        self._config.set("best_of_3", "enabled", "true" if features.get("best_of_3", True) else "false")
        self._config.set("best_of_3", "sample_count", "3")
        self._config.set("best_of_3", "scorer_min_total", "8")

        # retry / oracle
        self._config.add_section("retry")
        self._config.set("retry", "max_retries", "3")
        self._config.set("retry", "base_delay", "1.0")
        self._config.add_section("oracle")
        self._config.set("oracle", "trigger_interval", str(game.get("oracle_interval", 5)))

        # emergence / continuity / reflection
        emerge = cfg.get("emergence", {}) or {}
        self._config.add_section("emergence")
        self._config.set("emergence", "hit_threshold", str(emerge.get("hit_threshold", 3)))
        self._config.set("emergence", "similarity_threshold", str(emerge.get("similarity_threshold", 0.75)))
        self._config.set("emergence", "feature_extraction", str(emerge.get("feature_extraction", "llm")))
        self._config.set("emergence", "max_pending_entities", str(emerge.get("max_pending_entities", 50)))

        cont = cfg.get("continuity", {}) or {}
        self._config.add_section("continuity")
        self._config.set("continuity", "max_rewrite", str(cont.get("max_rewrite", 2)))
        self._config.set("continuity", "tier", resolve_tier(str(cont.get("tier", "medium"))))

        refl = cfg.get("reflection", {}) or {}
        self._config.add_section("reflection")
        self._config.set("reflection", "tier", resolve_tier(str(refl.get("tier", "light"))))
        for key in ("check_clothing", "check_location", "check_mood", "check_relationship"):
            self._config.set("reflection", key, "true" if refl.get(key, True) else "false")

        # truncation 配置节
        trunc = cfg.get("truncation", {}) or {}
        self._config.add_section("truncation")
        self._config.set("truncation", "thread_context", str(trunc.get("thread_context", 3000)))
        self._config.set("truncation", "llm_extract", str(trunc.get("llm_extract", 15000)))
        self._config.set("truncation", "scene_context", str(trunc.get("scene_context", 4000)))
        self._config.set("truncation", "narrative_history", str(trunc.get("narrative_history", 2000)))

        # memory system
        mem = cfg.get("memory", {}) or {}
        self._config.add_section("memory")
        self._config.set("memory", "recency_weight", str(mem.get("recency_weight", 0.4)))
        self._config.set("memory", "relevance_weight", str(mem.get("relevance_weight", 0.3)))
        self._config.set("memory", "importance_weight", str(mem.get("importance_weight", 0.3)))
        self._config.set("memory", "decay_lambda", str(mem.get("decay_lambda", 0.05)))
        self._config.set("memory", "reflection_threshold", str(mem.get("reflection_threshold", 30)))
        self._config.set("memory", "top_k_director", str(mem.get("top_k_director", 5)))
        self._config.set("memory", "top_k_character", str(mem.get("top_k_character", 3)))
        self._config.set("memory", "max_entries_per_agent", str(mem.get("max_entries_per_agent", 200)))
        self._config.set("memory", "retrieve_recency_window", str(mem.get("retrieve_recency_window", 100)))
        self._config.set("memory", "retention_window", str(mem.get("retention_window", 50)))
        self._config.set("memory", "low_importance_threshold", str(mem.get("low_importance_threshold", 4.0)))
        self._config.set("memory", "compact_interval", str(mem.get("compact_interval", 10)))

    def reload(self, yaml_dict: dict) -> None:
        """从新的 YAML dict 重新加载配置（热重连用）"""
        self._config = configparser.ConfigParser()
        self._populate_from_yaml(yaml_dict)
        self._loaded = True

    def _ensure_loaded(self) -> None:
        """No-op: configuration is always loaded at init time.

        Retained for external call compatibility.
        """
        pass

    # ------------------------------------------------------------------
    # Tier config
    # ------------------------------------------------------------------

    def get_tier_config(self, tier: str) -> dict:
        """获取指定层的完整 Provider 配置。

        Args:
            tier: 层名 — 支持中文（"导演层"/"演员层"/"动作层"）或内部名（"strong"/"medium"/"light"）

        Returns:
            {"type": str, "endpoint": str, "api_key": str, "model": str,
             "temperature": float, "max_tokens": int, "timeout": int}
        """
        self._ensure_loaded()
        section = f"provider_{resolve_tier(tier)}"
        return {
            "type": self._get_str(section, "type", "ollama"),
            "endpoint": self._get_str(section, "endpoint", ""),
            "api_key": self._get_str(section, "api_key", ""),
            "model": self._get_str(section, "model", ""),
            "temperature": self._get_float(section, "temperature", 0.7),
            "max_tokens": self._get_int(section, "max_tokens", 2048),
            "timeout": self._get_int(section, "timeout", 120),
        }

    def set_tier_config(self, tier: str, config: dict) -> None:
        """设置指定层的 Provider 配置。

        ⚠️ 此方法仅更新内部 ConfigParser 表示。
           配置持久化统一走 game_session.update_config → yaml.dump 写回 config.yaml。
           Phase 2 移除 ConfigParser 后将改为直接操作 self._cfg_dict。
        """
        self._ensure_loaded()
        section = f"provider_{resolve_tier(tier)}"
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, "type", str(config.get("type", "ollama")))
        self._config.set(section, "endpoint", str(config.get("endpoint", "")))
        self._config.set(section, "api_key", str(config.get("api_key", "")))
        self._config.set(section, "model", str(config.get("model", "")))
        self._config.set(section, "temperature", str(config.get("temperature", 0.7)))
        self._config.set(section, "max_tokens", str(config.get("max_tokens", 2048)))
        self._config.set(section, "timeout", str(config.get("timeout", 120)))

    # ------------------------------------------------------------------
    # Retry / Oracle
    # ------------------------------------------------------------------

    def get_retry_config(self) -> dict:
        """Get retry configuration."""
        self._ensure_loaded()
        return {
            "max_retries": self._get_int("retry", "max_retries", 3),
            "base_delay": self._get_float("retry", "base_delay", 1.0),
        }

    def get_oracle_interval(self) -> int:
        """Get Oracle trigger interval (number of beats)."""
        self._ensure_loaded()
        return self._get_int("oracle", "trigger_interval", 5)

    # ------------------------------------------------------------------
    # Truncation limits
    # ------------------------------------------------------------------

    def get_truncation_config(self) -> dict:
        """获取各模块文本截断限制。"""
        self._ensure_loaded()
        return {
            "thread_context": self._get_int("truncation", "thread_context", 3000),
            "llm_extract": self._get_int("truncation", "llm_extract", 15000),
            "scene_context": self._get_int("truncation", "scene_context", 4000),
            "narrative_history": self._get_int("truncation", "narrative_history", 2000),
        }

    # ------------------------------------------------------------------
    # v4 Feature flags
    # ------------------------------------------------------------------

    def is_v4_enabled(self) -> bool:
        """Check if MaNA v4 enhancements are globally enabled."""
        return self._get_bool("v4", "enabled", False)

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific v4 feature is enabled.

        Args:
            feature: Section name such as "refinement", "best_of_3", "multi_view", etc.

        Returns:
            True only if v4 is globally on AND the feature section's enabled flag is True.
            For emergence_system/continuity_check/role_reflection: check directly without v4 gate.
        """
        # 新功能不依赖 v4 全局开关
        if feature in ("emergence_system", "continuity_check", "role_reflection", "memory_system"):
            return self._get_bool(feature, "enabled", False)
        if not self.is_v4_enabled():
            return False
        return self._get_bool(feature, "enabled", False)

    # ------------------------------------------------------------------
    # v4: Refinement limits
    # ------------------------------------------------------------------

    def get_refinement_limits(self) -> dict:
        """Get refinement loop parameters."""
        return {
            "max_warning_refine": self._get_int("refinement", "max_warning_refine", 1),
            "max_fail_rewrite": self._get_int("refinement", "max_fail_rewrite", 2),
        }

    # ------------------------------------------------------------------
    # v4: Best-of-3
    # ------------------------------------------------------------------

    def get_best_of_3_config(self) -> dict:
        """Get Best-of-3 Director parameters."""
        return {
            "sample_count": self._get_int("best_of_3", "sample_count", 3),
            "scorer_min_total": self._get_int("best_of_3", "scorer_min_total", 8),
        }

    # ------------------------------------------------------------------
    # v4: Dynamic Tier
    # ------------------------------------------------------------------

    def get_complexity_thresholds(self) -> dict:
        """Get complexity thresholds for dynamic tier adjustment."""
        return {
            "simple": self._get_float("dynamic_tier", "complexity_threshold_simple", 0.3),
            "complex": self._get_float("dynamic_tier", "complexity_threshold_complex", 0.5),
        }

    def get_tier_overrides(self, complexity: float) -> dict:
        """根据场景复杂度评分获取层级覆盖。

        Returns:
            空 dict 表示无覆盖；否则返回 Agent 名 → 内部层名（strong/medium/light）的映射。
        """
        simple_thresh = self._get_float("dynamic_tier", "complexity_threshold_simple", 0.3)
        complex_thresh = self._get_float("dynamic_tier", "complexity_threshold_complex", 0.5)
        if complexity < simple_thresh:
            return {"director": "medium", "composer": "medium", "auditor": "light", "motivation": "light"}
        elif complexity > complex_thresh:
            return {"director": "strong", "composer": "strong", "auditor": "strong", "motivation": "strong"}
        return {}

    # ------------------------------------------------------------------
    # v4: Semantic selection
    # ------------------------------------------------------------------

    def get_semantic_selection_config(self) -> dict:
        """Get semantic Canon selection parameters."""
        return {
            "max_canon_tokens": self._get_int("semantic_selection", "max_canon_tokens", 1200),
        }

    # ------------------------------------------------------------------
    # v4: Vector memory
    # ------------------------------------------------------------------

    def get_vector_memory_config(self) -> dict:
        """Get vector memory parameters."""
        return {
            "enable_vector_memory": self._get_bool("memory", "enable_vector_memory", False),
            "embed_model": self._get_str("memory", "embed_model", "nomic-embed-text"),
            "vector_top_k": self._get_int("memory", "vector_top_k", 3),
            "max_vector_entries": self._get_int("memory", "max_vector_entries", 500),
        }

    # ------------------------------------------------------------------
    # Emergence
    # ------------------------------------------------------------------

    def get_emergence_config(self) -> dict:
        """Get emergence system parameters."""
        return {
            "hit_threshold": self._get_int("emergence", "hit_threshold", 3),
            "similarity_threshold": self._get_float("emergence", "similarity_threshold", 0.75),
            "feature_extraction": self._get_str("emergence", "feature_extraction", "llm"),
            "max_pending_entities": self._get_int("emergence", "max_pending_entities", 50),
        }

    def get_continuity_max_rewrite(self) -> int:
        """Get ContinuityChecker max rewrite count."""
        return self._get_int("continuity", "max_rewrite", 2)

    # ------------------------------------------------------------------
    # Memory
    # ------------------------------------------------------------------

    def get_memory_config(self) -> dict:
        """Get memory system parameters. (Override base method with full config)"""
        return {
            "recency_weight": self._get_float("memory", "recency_weight", 0.4),
            "relevance_weight": self._get_float("memory", "relevance_weight", 0.3),
            "importance_weight": self._get_float("memory", "importance_weight", 0.3),
            "decay_lambda": self._get_float("memory", "decay_lambda", 0.05),
            "reflection_threshold": self._get_float("memory", "reflection_threshold", 30),
            "top_k_director": self._get_int("memory", "top_k_director", 5),
            "top_k_character": self._get_int("memory", "top_k_character", 3),
            "max_entries_per_agent": self._get_int("memory", "max_entries_per_agent", 200),
            "retrieve_recency_window": self._get_int("memory", "retrieve_recency_window", 100),
            "retention_window": self._get_int("memory", "retention_window", 50),
            "low_importance_threshold": self._get_float("memory", "low_importance_threshold", 4.0),
            "compact_interval": self._get_int("memory", "compact_interval", 10),
        }

    # ------------------------------------------------------------------
    # Generic typed accessors (for pipeline direct use)
    # ------------------------------------------------------------------

    def get_str(self, section: str, key: str, default: str = "") -> str:
        """Generic string config accessor."""
        return self._get_str(section, key, default)

    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """Generic int config accessor."""
        return self._get_int(section, key, default)

    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        """Generic float config accessor."""
        return self._get_float(section, key, default)

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """Generic bool config accessor."""
        return self._get_bool(section, key, default)

    # ------------------------------------------------------------------
    # v4: Performance degradation
    # ------------------------------------------------------------------

    def get_degrade_config(self) -> dict:
        """Get performance degradation parameters."""
        return {
            "auto_degrade_enabled": self._get_bool("performance", "auto_degrade_enabled", True),
            "sample_count_degrade_1": self._get_int("performance", "sample_count_degrade_1", 2),
            "sample_count_degrade_2": self._get_int("performance", "sample_count_degrade_2", 1),
            "multi_view_degrade_1": self._get_bool("performance", "multi_view_degrade_1", False),
        }

    # ------------------------------------------------------------------
    # Safe typed accessors
    # ------------------------------------------------------------------

    def _get_bool(self, section: str, key: str, default: bool = False) -> bool:
        if not self._config.has_section(section):
            return default
        val = self._config.get(section, key, fallback=str(default)).lower()
        return val in ("true", "1", "yes")

    def _get_float(self, section: str, key: str, default: float = 0.0) -> float:
        if not self._config.has_section(section):
            return default
        try:
            return self._config.getfloat(section, key, fallback=default)
        except ValueError:
            return default

    def _get_int(self, section: str, key: str, default: int = 0) -> int:
        if not self._config.has_section(section):
            return default
        try:
            return self._config.getint(section, key, fallback=default)
        except ValueError:
            return default

    def _get_str(self, section: str, key: str, default: str = "") -> str:
        if not self._config.has_section(section):
            return default
        return self._config.get(section, key, fallback=default)
