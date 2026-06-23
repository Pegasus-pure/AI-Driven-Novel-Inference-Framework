"""MaNA v4 Data Contract Centre.

Defines all Agent input/output key definitions and validation rules.
All methods are static — no instance state.
"""

import copy
from typing import Any


class MananaSchema:
    """Static schema definitions and validators for the MaNA pipeline."""

    # ------------------------------------------------------------------
    # SceneContext schema
    # ------------------------------------------------------------------

    SCENE_CONTEXT_SCHEMA: dict = {
        "beat_id": "string",
        "scene_id": "string",
        "game_time": "string",
        "location": {"id": "", "name": "", "description": "", "atmosphere": ""},
        "player": {
            "action": "",
            "profile": {"traits": [], "motivation": "", "tendency": ""},
            "reputation": {},
        },
        "characters": [],
        "active_threads": [],
        "recent_history": [],
        "scene_memory": [],
        "long_term_memory": [],
        "divergence": 0.0,
        "relevant_world_rules": "",
        # soul_possession 模式扩展（可选）
        "game_mode": "interactive",
        "soul": {
            "decision": {"action_type": "", "dissonance_impact": 0.0},
            "inner_voice": {"player_inner_voice": "", "canon_echo": "", "internal_conflict": ""},
        },
    }

    # ------------------------------------------------------------------
    # Agent output key definitions
    # ------------------------------------------------------------------

    DIRECTOR_OUTPUT_KEYS: list[str] = [
        "beat_id", "narrative_mode", "beat_summary", "featured_characters",
        "interaction_pairs", "unpaired_characters", "scene_tone",
        "priority_thread_ids", "required_canon",
    ]

    MOTIVATION_OUTPUT_KEYS: list[str] = [
        "character_id", "internal_state", "stance_toward_player",
    ]

    DIALOGUE_WEAVER_OUTPUT_KEYS: list[str] = [
        "character_id", "dialogue", "actions", "emotional_arc", "stance_change",
    ]

    COMPOSER_OUTPUT_KEYS: list[str] = [
        "ending_hook", "action_hints", "music_mood", "choices",
    ]

    AUDITOR_OUTPUT_KEYS: list[str] = [
        "verdict", "issues", "overall_quality", "refinement_hints",
    ]

    STATE_EXTRACTOR_OUTPUT_KEYS: list[str] = [
        "reputation_changes", "mood_changes", "location_changes",
        "new_knowledge", "new_dynamic_npcs", "player_profile_updates",
        "narrative_summary", "scene_memory_entry",
        "divergence_delta", "narrative_tension", "canon_adherence",
        "narrative_mode", "character_arc_progress", "new_seed_conflicts",
    ]

    THREAD_MANAGER_OUTPUT_KEYS: list[str] = [
        "thread_advances", "new_threads", "evolved_threads", "tension_adjustments",
    ]

    ORACLE_OUTPUT_KEYS: list[str] = [
        "pacing_assessment", "character_observations", "thread_health",
        "narrative_opportunities", "tone_recommendation",
    ]

    # ------------------------------------------------------------------
    # Type maps (for validation)
    # ------------------------------------------------------------------

    _DIRECTOR_TYPE_MAP: dict[str, str] = {
        "beat_id": "string",
        "narrative_mode": "string",
        "beat_summary": "string",
        "featured_characters": "array",
        "interaction_pairs": "array",
        "unpaired_characters": "array",
        "scene_tone": "string",
        "priority_thread_ids": "array",
        "required_canon": "array",
    }

    _MOTIVATION_TYPE_MAP: dict[str, str] = {
        "character_id": "string",
        "internal_state": "dictionary",
        "stance_toward_player": "dictionary",
    }

    _DIALOGUE_TYPE_MAP: dict[str, str] = {
        "character_id": "string",
        "dialogue": "array",
        "actions": "array",
        "emotional_arc": "string",
        "stance_change": "dictionary",
    }

    _COMPOSER_TYPE_MAP: dict[str, str] = {
        "ending_hook": "string",
        "action_hints": "array",
        "music_mood": "string",
        "choices": "array",
    }

    _AUDITOR_TYPE_MAP: dict[str, str] = {
        "verdict": "string",
        "issues": "array",
        "overall_quality": "dictionary",
        "refinement_hints": "array",
    }

    _EXTRACTOR_TYPE_MAP: dict[str, str] = {
        "reputation_changes": "array",
        "mood_changes": "array",
        "location_changes": "array",
        "new_knowledge": "array",
        "new_dynamic_npcs": "array",
        "player_profile_updates": "dictionary",
        "narrative_summary": "string",
        "scene_memory_entry": "string",
    }

    _EXTRACTOR_EXTENDED_TYPE_MAP: dict[str, str] = {
        "divergence_delta": "float",
        "narrative_tension": "float",
        "canon_adherence": "float",
        "narrative_mode": "string",
        "character_arc_progress": "dictionary",
        "new_seed_conflicts": "array",
    }

    _THREAD_TYPE_MAP: dict[str, str] = {
        "thread_advances": "array",
        "new_threads": "array",
        "evolved_threads": "array",
        "tension_adjustments": "array",
    }

    _ORACLE_TYPE_MAP: dict[str, str] = {
        "pacing_assessment": "dictionary",
        "character_observations": "array",
        "thread_health": "array",
        "narrative_opportunities": "array",
        "tone_recommendation": "string",
    }

    # ------------------------------------------------------------------
    # SceneContext builder
    # ------------------------------------------------------------------

    @staticmethod
    def build_scene_context(
        chars: list[dict],
        threads: list[dict],
        location: dict,
        player: dict,
        history: list[dict],
        memory: dict,
        divergence: float,
        world_rules: str = "",
        beat_id: str = "",
        scene_id: str = "",
        game_time: str = "",
    ) -> dict:
        """Assemble a full SceneContext dictionary from raw world state data.

        Args:
            chars: List of character state dicts.
            threads: List of active narrative thread dicts.
            location: Current location info {id, name, description, atmosphere}.
            player: Player state {action, profile, reputation}.
            history: Recent narrative history entries.
            memory: {scene_memory: list, long_term_memory: list}.
            divergence: World divergence score (-1.0–1.0).
            world_rules: Relevant world rules text (may be empty).
            beat_id: Current beat identifier.
            scene_id: Current scene identifier.
            game_time: Current game time string.

        Returns:
            Complete SceneContext dictionary.
        """
        return {
            "beat_id": beat_id,
            "scene_id": scene_id,
            "game_time": game_time,
            "location": dict(location),
            "player": _deep_copy_dict(player),
            "characters": _deep_copy_list(chars),
            "active_threads": _deep_copy_list(threads),
            "recent_history": list(history),
            "scene_memory": list(memory.get("scene_memory", [])),
            "long_term_memory": list(memory.get("long_term_memory", [])),
            "divergence": divergence,
            "relevant_world_rules": world_rules,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_keys(data: dict, required_keys: list[str], type_map: dict[str, str] | None = None) -> dict:
        """Generic key validator with optional type checking.

        Returns:
            {"valid": bool, "errors": list[str]}
        """
        errors: list[str] = []
        tm = type_map or {}

        for key in required_keys:
            if key not in data:
                errors.append(f"Missing required key: '{key}'")
                continue
            if key in tm:
                expected = tm[key]
                value = data[key]
                if expected == "string" and value is not None and not isinstance(value, str):
                    errors.append(f"Key '{key}' expected str, got {type(value).__name__}")
                elif expected in ("int", "float") and value is not None and not isinstance(value, (int, float)):
                    errors.append(f"Key '{key}' expected number, got {type(value).__name__}")
                elif expected == "array" and value is not None and not isinstance(value, list):
                    errors.append(f"Key '{key}' expected list, got {type(value).__name__}")
                elif expected == "dictionary" and value is not None and not isinstance(value, dict):
                    errors.append(f"Key '{key}' expected dict, got {type(value).__name__}")
                elif expected == "bool" and value is not None and not isinstance(value, bool):
                    errors.append(f"Key '{key}' expected bool, got {type(value).__name__}")

        return {"valid": len(errors) == 0, "errors": errors}

    @staticmethod
    def validate_director_output(data: dict) -> dict:
        """Validate Director output."""
        return MananaSchema._validate_keys(data, MananaSchema.DIRECTOR_OUTPUT_KEYS, MananaSchema._DIRECTOR_TYPE_MAP)

    @staticmethod
    def validate_motivation_output(data: dict) -> dict:
        """Validate Motivation output."""
        return MananaSchema._validate_keys(data, MananaSchema.MOTIVATION_OUTPUT_KEYS, MananaSchema._MOTIVATION_TYPE_MAP)

    @staticmethod
    def validate_dialogue_output(data: dict) -> dict:
        """Validate Dialogue output."""
        return MananaSchema._validate_keys(data, MananaSchema.DIALOGUE_WEAVER_OUTPUT_KEYS, MananaSchema._DIALOGUE_TYPE_MAP)

    @staticmethod
    def validate_composer_output(data: dict) -> dict:
        """Validate Composer output."""
        return MananaSchema._validate_keys(data, MananaSchema.COMPOSER_OUTPUT_KEYS, MananaSchema._COMPOSER_TYPE_MAP)

    @staticmethod
    def validate_auditor_output(data: dict) -> dict:
        """Validate Auditor output."""
        return MananaSchema._validate_keys(data, MananaSchema.AUDITOR_OUTPUT_KEYS, MananaSchema._AUDITOR_TYPE_MAP)

    @staticmethod
    def validate_extractor_output(data: dict) -> dict:
        """Validate Extractor output (merges base + extended type maps)."""
        merged_map: dict[str, str] = {}
        merged_map.update(MananaSchema._EXTRACTOR_TYPE_MAP)
        merged_map.update(MananaSchema._EXTRACTOR_EXTENDED_TYPE_MAP)
        return MananaSchema._validate_keys(data, MananaSchema.STATE_EXTRACTOR_OUTPUT_KEYS, merged_map)

    @staticmethod
    def validate_thread_output(data: dict) -> dict:
        """Validate ThreadManager output."""
        return MananaSchema._validate_keys(data, MananaSchema.THREAD_MANAGER_OUTPUT_KEYS, MananaSchema._THREAD_TYPE_MAP)

    @staticmethod
    def validate_oracle_output(data: dict) -> dict:
        """Validate Oracle output."""
        return MananaSchema._validate_keys(data, MananaSchema.ORACLE_OUTPUT_KEYS, MananaSchema._ORACLE_TYPE_MAP)

    @staticmethod
    def build_reflection_context(
        beat_count: int,
        memory_text: str = "",
        agent_type: str = "director",
    ) -> dict:
        """Build reflection context for memory reflection.

        Args:
            beat_count: Current beat number.
            memory_text: Recent memory entries formatted as text.
            agent_type: "director" | "character" | "world"

        Returns:
            dict with reflection context.
        """
        return {
            "beat_count": beat_count,
            "memory_text": memory_text,
            "agent_type": agent_type,
        }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _deep_copy_dict(d: dict) -> dict:
    """Recursive copy of a dict (only dict/list/str/int/float/bool scalars)."""
    return copy.deepcopy(d)


def _deep_copy_list(lst: list) -> list:
    """Deep copy of a list."""
    return copy.deepcopy(lst)


# ═══════════════════════════════════════════════════════
# P2-B: 语义验证器
# ═══════════════════════════════════════════════════════

class SemanticValidator:
    """LLM 输出语义验证器。

    在 MananaSchema 类型验证基础上，增加：
      - 数值范围约束（如 divergence_delta: [-0.2, 0.2]）
      - 字符串非空检查（如 choice.text 不能为空）
      - 数组最小长度检查
    """

    # 数值范围约束
    RANGE_CONSTRAINTS: dict[str, tuple[float, float]] = {
        "divergence_delta": (-0.2, 0.2),
        "tension_adjustment": (-0.3, 0.3),
        "quality_score": (0.0, 1.0),
        "confidence": (0.0, 1.0),
        "intensity": (0.0, 1.0),
        "complexity": (0.0, 1.0),
        "canon_adherence": (0.0, 1.0),
        "overall_quality": (0.0, 1.0),
        "world_divergence": (-1.0, 1.0),
        "narrative_tension": (0.0, 1.0),
    }

    # 非空字符串字段
    NON_EMPTY_FIELDS: set[str] = {
        "choice.text", "ending_hook", "beat_summary",
    }

    # 数组最小长度
    MIN_ARRAY_LENGTH: dict[str, int] = {
        "choices": 2,
        "action_hints": 1,
        "featured_characters": 1,
    }

    @classmethod
    def validate_composer_output(cls, data: dict) -> dict:
        """验证 SceneComposer 输出（类型 + 语义）。

        Args:
            data: Composer 输出的 dict

        Returns:
            {"valid": bool, "errors": list[str]}
        """
        errors: list[str] = []
        data = data or {}

        # 类型检查（委托给现有验证器）
        type_result = MananaSchema._validate_keys(
            data, MananaSchema.COMPOSER_OUTPUT_KEYS, MananaSchema._COMPOSER_TYPE_MAP,
        )
        if not type_result.get("valid", False):
            errors.extend(type_result.get("errors", []))

        # ── 语义检查 ──
        # 数值范围
        for field, (lo, hi) in cls.RANGE_CONSTRAINTS.items():
            if field in data and data[field] is not None:
                val = data[field]
                if isinstance(val, (int, float)):
                    if not (lo <= val <= hi):
                        errors.append(f"{field}={val} 超出范围 [{lo}, {hi}]")

        # 非空字符串
        for field_path in cls.NON_EMPTY_FIELDS:
            val = cls._get_nested(data, field_path)
            if val is not None and not str(val).strip():
                errors.append(f"{field_path} 为空")

        # soul_decision 语义检查
        soul_decision = data.get("soul_decision")
        if isinstance(soul_decision, dict):
            for mode in ("authentic", "conforming"):
                actions = soul_decision.get(mode)
                if isinstance(actions, list):
                    for i, act in enumerate(actions):
                        if isinstance(act, dict):
                            for field in ("text", "hint", "next_scene_hint"):
                                if not str(act.get(field, "") or "").strip():
                                    errors.append(f"soul_decision.{mode}[{i}].{field} 为空")

        # 数组最小长度
        for field, min_len in cls.MIN_ARRAY_LENGTH.items():
            val = data.get(field)
            if isinstance(val, list) and len(val) < min_len:
                errors.append(f"{field} 长度({len(val)})小于最小值({min_len})")

        return {"valid": len(errors) == 0, "errors": errors}

    @classmethod
    def validate_extractor_output(cls, data: dict) -> dict:
        """验证 StateExtractor 输出（含数值范围）。"""
        errors: list[str] = []

        # 数值范围
        for field, (lo, hi) in cls.RANGE_CONSTRAINTS.items():
            if field in data and data[field] is not None:
                val = data[field]
                if isinstance(val, (int, float)):
                    if not (lo <= val <= hi):
                        errors.append(f"{field}={val} 超出范围 [{lo}, {hi}]")

        return {"valid": len(errors) == 0, "errors": errors}

    @classmethod
    def _get_nested(cls, data: dict, dotted_path: str) -> Any:
        """按点分路径获取嵌套值。例如 \"choice.text\" """
        parts = dotted_path.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
