"""Reward Tracker for MaNA Pipeline.

Computes per-beat reward scores and appends them to metrics/reward_log.jsonl.

Reward = w1*auditor_score + w2*micro_oracle_health
        + w3*narrative_tension + w4*canon_adherence
        - w5*issue_penalty
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

_log = logging.getLogger("MaNA.Reward")


class RewardTracker:
    """Computes and logs reward for each narrative beat."""

    def __init__(self, config: dict) -> None:
        reward_cfg = config.get("reward", {})
        self._enabled: bool = reward_cfg.get("enabled", True)
        self._weights: dict[str, float] = {
            "auditor_score": float(reward_cfg.get("weights", {}).get("auditor_score", 0.3)),
            "micro_oracle_health": float(reward_cfg.get("weights", {}).get("micro_oracle_health", 0.2)),
            "narrative_tension": float(reward_cfg.get("weights", {}).get("narrative_tension", 0.2)),
            "canon_adherence": float(reward_cfg.get("weights", {}).get("canon_adherence", 0.2)),
            "issue_penalty": float(reward_cfg.get("weights", {}).get("issue_penalty", 0.1)),
        }
        log_path: str = reward_cfg.get("log_path", "server/manana/metrics/reward_log.jsonl")
        # Resolve relative to project root
        if not os.path.isabs(log_path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            log_path = os.path.join(project_root, log_path)
        self._log_path: str = log_path
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        _log.info("RewardTracker init: log_path=%s, weights=%s", self._log_path, self._weights)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self, beat_result: dict, beat_id: str, beat_count: int) -> dict:
        """Compute reward from a completed beat result.

        Args:
            beat_result: The dict returned by pipeline.run_beat()
            beat_id: e.g. "beat_003"
            beat_count: integer beat counter

        Returns:
            {"reward": float, "components": dict, "beat_id": str, ...}
        """
        if not self._enabled:
            return {"reward": 0.0, "enabled": False}

        components: dict[str, float] = {}

        # ── 1. Auditor score (0.0–1.0) ──
        audit_data: dict = (beat_result.get("audit") or {}).get("raw", {}) or {}
        auditor_score: float = 0.0
        overall_quality = audit_data.get("overall_quality")
        if isinstance(overall_quality, dict):
            # Use character_consistency as proxy for overall quality
            auditor_score = float(overall_quality.get("character_consistency", 0.5))
        elif isinstance(overall_quality, (int, float)):
            auditor_score = float(overall_quality)
        # Verdict bonus/penalty
        verdict = str(audit_data.get("verdict", "PASS"))
        if verdict == "PASS":
            auditor_score = max(auditor_score, 0.8)
        elif verdict == "WARNING":
            auditor_score *= 0.7
        elif verdict == "FAIL":
            auditor_score *= 0.3
        components["auditor_score"] = _clamp(auditor_score, 0.0, 1.0)

        # ── 2. Micro-Oracle health → numeric score ──
        mo: dict = beat_result.get("micro_oracle") or {}
        health_str: str = str(mo.get("system_health", "healthy")).lower()
        health_score: float = _health_to_score(health_str)
        components["micro_oracle_health"] = health_score

        # ── 3. Narrative tension (already 0.0–1.0) ──
        state_patch: dict = beat_result.get("state_patch") or {}
        tension: float = float(state_patch.get("narrative_tension", 0.5))
        components["narrative_tension"] = _clamp(tension, 0.0, 1.0)

        # ── 4. Canon adherence (already 0.0–1.0) ──
        canon: float = float(state_patch.get("canon_adherence", 0.5))
        components["canon_adherence"] = _clamp(canon, 0.0, 1.0)

        # ── 5. Issue penalty (normalized) ──
        issues: list = audit_data.get("issues", []) or []
        issue_penalty: float = min(len(issues) * 0.05, 0.5)  # max 0.5 penalty
        components["issue_penalty"] = issue_penalty

        # ── Compute weighted reward ──
        w = self._weights
        reward: float = (
            w["auditor_score"] * components["auditor_score"]
            + w["micro_oracle_health"] * components["micro_oracle_health"]
            + w["narrative_tension"] * components["narrative_tension"]
            + w["canon_adherence"] * components["canon_adherence"]
            - w["issue_penalty"] * components["issue_penalty"]
        )
        reward = _clamp(reward, -1.0, 1.0)

        result = {
            "beat_id": beat_id,
            "beat_count": beat_count,
            "reward": round(reward, 4),
            "components": components,
            "timestamp": datetime.now().isoformat(),
        }
        _log.info("Reward[%s] = %.4f  components=%s", beat_id, reward, components)
        return result

    def log(self, reward_record: dict) -> None:
        """Append reward record to the JSONL log file."""
        if not self._enabled:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(reward_record, ensure_ascii=False) + "\n")
        except OSError as e:
            _log.error("Failed to write reward log: %s", e)

    def compute_and_log(self, beat_result: dict, beat_id: str, beat_count: int) -> dict:
        """Convenience: compute + log in one call."""
        record = self.compute(beat_result, beat_id, beat_count)
        self.log(record)
        return record


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _health_to_score(health: str) -> float:
    """Convert MicroOracle system_health string to 0.0–1.0 score."""
    mapping = {
        "healthy": 1.0,
        "good": 0.85,
        "fair": 0.6,
        "degraded": 0.4,
        "unhealthy": 0.2,
        "critical": 0.0,
    }
    return mapping.get(health, 0.5)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
