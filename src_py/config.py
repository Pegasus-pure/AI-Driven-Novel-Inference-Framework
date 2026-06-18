"""MaNA v4 Configuration loader.

Reads manana_config.cfg (INI format) and provides access to:
  - Three-tier provider configs (strong / medium / light)
  - Retry / Oracle interval settings
  - v4 feature flags (refinement, best_of_3, multi_view, etc.)
  - Dynamic tier / complexity thresholds
"""

import configparser
import os
from typing import Any, Optional


class MananaConfig:
    """MaNA pipeline configuration loaded from an INI file.

    Backward-compatible with Godot's manana_config.cfg.
    Auto-creates a default v2 config if the file is missing.
    """

    CONFIG_PATH: str = "manana_config.cfg"

    def __init__(self, config_path: str = "") -> None:
        """Initialize config loader.

        Args:
            config_path: Path to the INI config file. Defaults to CONFIG_PATH.
        """
        if config_path:
            self.CONFIG_PATH = config_path
        self._config: configparser.ConfigParser = configparser.ConfigParser()
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load_config(self) -> None:
        """Load configuration from file. Creates default v2 config if missing."""
        if os.path.isfile(self.CONFIG_PATH):
            self._config.read(self.CONFIG_PATH, encoding="utf-8")
            self._loaded = True
        else:
            self._create_default_v2_config()

    def save(self) -> None:
        """Persist current configuration to disk."""
        if not self._loaded:
            return
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            self._config.write(f)

    def _ensure_loaded(self) -> None:
        """Lazy-load config if not already loaded."""
        if not self._loaded:
            self.load_config()

    # ------------------------------------------------------------------
    # Tier config
    # ------------------------------------------------------------------

    def get_tier_config(self, tier: str) -> dict:
        """Get the full provider config for a given tier.

        Args:
            tier: "strong" | "medium" | "light"

        Returns:
            {"type": str, "endpoint": str, "api_key": str, "model": str,
             "temperature": float, "max_tokens": int, "timeout": int}
        """
        self._ensure_loaded()
        section = f"provider_{tier}"
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
        """Set provider config for a tier and persist."""
        self._ensure_loaded()
        section = f"provider_{tier}"
        if not self._config.has_section(section):
            self._config.add_section(section)
        self._config.set(section, "type", str(config.get("type", "ollama")))
        self._config.set(section, "endpoint", str(config.get("endpoint", "")))
        self._config.set(section, "api_key", str(config.get("api_key", "")))
        self._config.set(section, "model", str(config.get("model", "")))
        self._config.set(section, "temperature", str(config.get("temperature", 0.7)))
        self._config.set(section, "max_tokens", str(config.get("max_tokens", 2048)))
        self._config.set(section, "timeout", str(config.get("timeout", 120)))
        self.save()

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
        """
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
        """Get tier overrides based on scene complexity score.

        Args:
            complexity: 0.0–1.0 complexity score.

        Returns:
            Empty dict if no override; otherwise mapping of agent names to tier strings.
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

    def get_memory_config(self) -> dict:
        """Get vector memory parameters."""
        return {
            "enable_vector_memory": self._get_bool("memory", "enable_vector_memory", False),
            "embed_model": self._get_str("memory", "embed_model", "nomic-embed-text"),
            "vector_top_k": self._get_int("memory", "vector_top_k", 3),
            "max_vector_entries": self._get_int("memory", "max_vector_entries", 500),
        }

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

    # ------------------------------------------------------------------
    # Default v2 config generation
    # ------------------------------------------------------------------

    def _create_default_v2_config(self) -> None:
        """Create a default v2 configuration file."""
        c = configparser.ConfigParser()

        c.add_section("global")
        c.set("global", "config_version", "2")

        # ── provider_strong ──
        c.add_section("provider_strong")
        c.set("provider_strong", "type", "ollama")
        c.set("provider_strong", "endpoint", "http://192.168.71.11:11434/api/chat")
        c.set("provider_strong", "api_key", "")
        c.set("provider_strong", "model", "qwen3.5:9b")
        c.set("provider_strong", "temperature", "0.5")
        c.set("provider_strong", "max_tokens", "4096")
        c.set("provider_strong", "timeout", "120")

        # ── provider_medium ──
        c.add_section("provider_medium")
        c.set("provider_medium", "type", "ollama")
        c.set("provider_medium", "endpoint", "http://192.168.71.11:11434/api/chat")
        c.set("provider_medium", "api_key", "")
        c.set("provider_medium", "model", "qwen3.5:9b")
        c.set("provider_medium", "temperature", "0.7")
        c.set("provider_medium", "max_tokens", "2048")
        c.set("provider_medium", "timeout", "120")

        # ── provider_light ──
        c.add_section("provider_light")
        c.set("provider_light", "type", "ollama")
        c.set("provider_light", "endpoint", "http://192.168.71.11:11434/api/chat")
        c.set("provider_light", "api_key", "")
        c.set("provider_light", "model", "qwen3.5:9b")
        c.set("provider_light", "temperature", "0.8")
        c.set("provider_light", "max_tokens", "512")
        c.set("provider_light", "timeout", "60")

        # ── retry ──
        c.add_section("retry")
        c.set("retry", "max_retries", "3")
        c.set("retry", "base_delay", "1.0")

        # ── oracle ──
        c.add_section("oracle")
        c.set("oracle", "trigger_interval", "5")

        # ── v4 feature toggles ──
        c.add_section("v4")
        c.set("v4", "enabled", "true")

        c.add_section("refinement")
        c.set("refinement", "enabled", "true")
        c.set("refinement", "max_warning_refine", "1")
        c.set("refinement", "max_fail_rewrite", "2")

        c.add_section("best_of_3")
        c.set("best_of_3", "enabled", "true")
        c.set("best_of_3", "sample_count", "3")
        c.set("best_of_3", "scorer_min_total", "8")

        c.add_section("multi_view")
        c.set("multi_view", "enabled", "false")

        c.add_section("micro_oracle")
        c.set("micro_oracle", "enabled", "true")

        c.add_section("dynamic_tier")
        c.set("dynamic_tier", "enabled", "false")
        c.set("dynamic_tier", "complexity_threshold_simple", "0.3")
        c.set("dynamic_tier", "complexity_threshold_complex", "0.5")

        c.add_section("semantic_selection")
        c.set("semantic_selection", "enabled", "false")
        c.set("semantic_selection", "max_canon_tokens", "1200")

        c.add_section("anti_rules")
        c.set("anti_rules", "enabled", "false")

        c.add_section("memory")
        c.set("memory", "enable_vector_memory", "false")
        c.set("memory", "embed_model", "nomic-embed-text")
        c.set("memory", "vector_top_k", "3")
        c.set("memory", "max_vector_entries", "500")

        c.add_section("performance")
        c.set("performance", "auto_degrade_enabled", "true")
        c.set("performance", "sample_count_degrade_1", "2")
        c.set("performance", "sample_count_degrade_2", "1")
        c.set("performance", "multi_view_degrade_1", "false")

        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            c.write(f)

        self._config = c
        self._loaded = True
        import logging
        logging.getLogger("MaNA").info("Default v2 config created at %s", self.CONFIG_PATH)
