"""MaNA v4 Data Contract Centre.

Defines all Agent input/output key definitions and validation rules.
All methods are static — no instance state.
"""

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
        "ending_hook", "action_hints", "music_mood",
    ]

    AUDITOR_OUTPUT_KEYS: list[str] = [
        "verdict", "issues", "overall_quality", "refinement_hints",
    ]

    STATE_EXTRACTOR_OUTPUT_KEYS: list[str] = [
        "reputation_changes", "mood_changes", "location_changes",
        "new_knowledge", "new_dynamic_npcs", "player_profile_updates",
        "narrative_summary", "scene_memory_entry",
    ]

    THREAD_MANAGER_OUTPUT_KEYS: list[str] = [
        "thread_advances", "new_threads", "closed_threads", "tension_adjustments",
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

    _THREAD_TYPE_MAP: dict[str, str] = {
        "thread_advances": "array",
        "new_threads": "array",
        "closed_threads": "array",
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
            divergence: World divergence score (0.0–1.0).
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
                if expected == "string" and not isinstance(value, str):
                    errors.append(f"Key '{key}' expected str, got {type(value).__name__}")
                elif expected in ("int", "float") and not isinstance(value, (int, float)):
                    errors.append(f"Key '{key}' expected number, got {type(value).__name__}")
                elif expected == "array" and not isinstance(value, list):
                    errors.append(f"Key '{key}' expected list, got {type(value).__name__}")
                elif expected == "dictionary" and not isinstance(value, dict):
                    errors.append(f"Key '{key}' expected dict, got {type(value).__name__}")
                elif expected == "bool" and not isinstance(value, bool):
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
        """Validate Extractor output."""
        return MananaSchema._validate_keys(data, MananaSchema.STATE_EXTRACTOR_OUTPUT_KEYS, MananaSchema._EXTRACTOR_TYPE_MAP)

    @staticmethod
    def validate_thread_output(data: dict) -> dict:
        """Validate ThreadManager output."""
        return MananaSchema._validate_keys(data, MananaSchema.THREAD_MANAGER_OUTPUT_KEYS, MananaSchema._THREAD_TYPE_MAP)

    @staticmethod
    def validate_oracle_output(data: dict) -> dict:
        """Validate Oracle output."""
        return MananaSchema._validate_keys(data, MananaSchema.ORACLE_OUTPUT_KEYS, MananaSchema._ORACLE_TYPE_MAP)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _deep_copy_dict(d: dict) -> dict:
    """Recursive copy of a dict (only dict/list/str/int/float/bool scalars)."""
    import copy
    return copy.deepcopy(d)


def _deep_copy_list(lst: list) -> list:
    """Deep copy of a list."""
    import copy
    return copy.deepcopy(lst)
