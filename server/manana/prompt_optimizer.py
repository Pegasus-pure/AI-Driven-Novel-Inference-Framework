"""Prompt Optimizer for MaNA Pipeline — Stage 3.

Reads high-reward beat samples and uses a stronger model
(to generate optimization hints that are injected into
SceneComposer's system prompt.

Runs periodically (every N beats) when enough high-reward samples
have been collected.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .config import MananaConfig
from .providers import BaseProvider, ProviderFactory

_log = logging.getLogger("MaNA.Optimizer")


class PromptOptimizer:
    """Analyzes high-reward narrative samples and generates prompt optimization hints."""

    def __init__(self, config: dict) -> None:
        self._config: dict = config
        opt_cfg: dict = config.get("prompt_optimization", {})
        self._enabled: bool = opt_cfg.get("enabled", False)
        self._provider_name: str = opt_cfg.get("provider", "导演层")
        self._threshold: float = float(opt_cfg.get("high_reward_threshold", 0.7))
        self._min_samples: int = int(opt_cfg.get("min_samples_for_optimization", 50))
        self._interval: int = int(opt_cfg.get("optimization_interval", 50))
        self._beat_count: int = 0

        # Paths
        project_root: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._reward_log_path: str = os.path.join(project_root, "server", "manana", "metrics", "reward_log.jsonl")
        self._opt_hints_path: str = os.path.join(project_root, "server", "manana", "metrics", "opt_hints.jsonl")

        os.makedirs(os.path.dirname(self._opt_hints_path), exist_ok=True)

        _log.info(
            "PromptOptimizer init: enabled=%s, provider=%s, threshold=%.2f",
            self._enabled, self._provider_name, self._threshold,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def maybe_run(self, beat_count: int) -> dict | None:
        """Check if optimization should run this beat; if so, run it.

        Returns:
            Optimization result dict, or None if skipped.
        """
        self._beat_count = beat_count
        if not self._enabled:
            return None
        if beat_count % self._interval != 0:
            return None

        samples: list[dict] = self._load_high_reward_samples()
        if len(samples) < self._min_samples:
            _log.info(
                "PromptOptimizer: only %d high-reward samples (need %d), skipping",
                len(samples), self._min_samples,
            )
            return None

        _log.info("PromptOptimizer: running with %d high-reward samples...", len(samples))
        result: dict = self._run_optimization(samples)
        self._save_opt_hints(result)
        return result

    def get_latest_hints(self) -> str:
        """Return the most recent optimization hints as a string
        that can be injected into SceneComposer's system prompt.
        """
        if not os.path.exists(self._opt_hints_path):
            return ""
        try:
            lines: list[str] = []
            with open(self._opt_hints_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)
            if not lines:
                return ""
            latest: dict = json.loads(lines[-1])
            return str(latest.get("hints_text", ""))
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("Failed to read opt_hints: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_high_reward_samples(self) -> list[dict]:
        """Load reward log and filter for high-reward beats.

        Note: this only returns reward records. To get the actual
        narrative text, the pipeline should also log narrative snippets
        to a parallel file. For now, we return the reward records
        and rely on the caller to cross-reference.
        """
        if not os.path.exists(self._reward_log_path):
            return []

        high: list[dict] = []
        try:
            with open(self._reward_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record: dict = json.loads(line)
                    if float(record.get("reward", 0.0)) >= self._threshold:
                        high.append(record)
        except (OSError, json.JSONDecodeError) as e:
            _log.error("Failed to load reward log: %s", e)

        # Sort by reward descending, take top
        high.sort(key=lambda r: float(r.get("reward", 0.0)), reverse=True)
        return high[: self._min_samples * 2]  # load extra so we can pick best

    def _run_optimization(self, samples: list[dict]) -> dict:
        """Use the configured provider's model to analyze high-reward samples.

        Returns:
            {"hints_text": str, "beat_count": int, "num_samples": int}
        """
        # Build analysis prompt
        analysis_prompt: str = self._build_analysis_prompt(samples)

        # Create provider from config
        provider_cfg: dict = self._get_provider_config()
        provider: BaseProvider | None = ProviderFactory.create(
            provider_cfg.get("type", "ollama"), provider_cfg,
        )
        if not provider:
            _log.error("PromptOptimizer: failed to create provider")
            return {"hints_text": "", "beat_count": self._beat_count, "num_samples": len(samples)}

        try:
            # Call LLM — use the provider directly
            messages: list[dict] = [
                {
                    "role": "system",
                    "content": "你是一个叙事质量分析专家。分析高质量叙事样本，提炼出可复用的写作特征和技巧。",
                },
                {"role": "user", "content": analysis_prompt},
            ]
            # Use provider's chat interface
            response = provider.chat(messages, temperature=0.3, max_tokens=2048)

            hints_text: str = ""
            if isinstance(response, dict):
                hints_text = str(response.get("content", ""))
            elif isinstance(response, str):
                hints_text = response

            result = {
                "hints_text": hints_text,
                "beat_count": self._beat_count,
                "num_samples": len(samples),
                "timestamp": self._iso_now(),
            }
            _log.info("PromptOptimizer: generated %d chars of hints", len(hints_text))
            return result

        finally:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(provider.cleanup())
                else:
                    asyncio.run(provider.cleanup())
            except Exception:
                pass

    def _build_analysis_prompt(self, samples: list[dict]) -> str:
        """Build the prompt for the optimizer LLM."""
        lines: list[str] = [
            f"以下是最新的 {len(samples)} 条高质量叙事样本的 reward 分析数据：",
            "",
            "```jsonl",
        ]
        for s in samples[:20]:  # only send first 20 to keep prompt short
            lines.append(json.dumps(s, ensure_ascii=False))
        lines += [
            "```",
            "",
            "请分析这些高质量样本的 reward 分项特征，提炼出：",
            "1. 高 reward 叙事在 auditor_score、narrative_tension、canon_adherence 上的共同特征",
            "2. 具体可复用的写作技巧（如对白风格、描写密度、节奏控制）",
            "3. 用一段简洁的中文描述这些特征，作为 SceneComposer 的写作风格参考",
            "",
            "输出格式：直接输出可注入 system prompt 的风格描述文本，200字以内。",
        ]
        return "\n".join(lines)

    def _get_provider_config(self) -> dict:
        """Get the provider config dict for the configured provider name."""
        # Navigate from full config to providers section
        # The config passed to __init__ is the full yaml dict
        providers: dict = self._config.get("providers", {})
        if self._provider_name in providers:
            return providers[self._provider_name]
        # Fallback: use 导演层
        _log.warning("Provider '%s' not found, falling back to '导演层'", self._provider_name)
        return providers.get("导演层", {})

    def _save_opt_hints(self, result: dict) -> None:
        """Append optimization result to opt_hints.jsonl."""
        try:
            with open(self._opt_hints_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except OSError as e:
            _log.error("Failed to save opt hints: %s", e)

    @staticmethod
    def _iso_now() -> str:
        from datetime import datetime
        return datetime.now().isoformat()
