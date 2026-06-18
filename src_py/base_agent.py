"""MaNA v4 Agent Base Class.

All narrative agents (Director, MotivationEngine, DialogueWeaver, etc.)
inherit from BaseAgent, which provides:
  - Provider injection
  - LLM call wrapper with logging
  - 3-strategy JSON response parsing
  - Abstract hooks for system/user prompt construction
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .providers import BaseProvider
from .utils import parse_json_response, log_agent_request, log_agent_response


_log = logging.getLogger("MaNA.Agent")


class BaseAgent(ABC):
    """Abstract base class for all MaNA narrative agents.

    Subclasses must override:
      - agent_name: str
      - model_tier: str  ("strong" | "medium" | "light")
      - build_system_prompt() → str
      - build_user_prompt(input_data: dict) → str
      - run(input_data: dict) → dict
    """

    agent_name: str = "base"
    model_tier: str = "medium"

    def __init__(self) -> None:
        self._provider: Optional[BaseProvider] = None

    # ------------------------------------------------------------------
    # Dependency injection
    # ------------------------------------------------------------------

    def configure(self, provider: BaseProvider) -> None:
        """Inject the LLM provider instance for this agent."""
        self._provider = provider

    def get_model_name(self) -> str:
        """Return the model name from the bound provider."""
        if self._provider:
            return self._provider.get_model_name(self.model_tier)
        return ""

    # ------------------------------------------------------------------
    # Abstract hooks — subclasses MUST override
    # ------------------------------------------------------------------

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Build the system prompt. Must be overridden by subclasses."""
        ...

    @abstractmethod
    def build_user_prompt(self, input_data: dict) -> str:
        """Build the user prompt from input data. Must be overridden by subclasses."""
        ...

    @abstractmethod
    async def run(self, input_data: dict) -> dict:
        """Core execution method. Must be overridden by subclasses.

        Returns:
            {"ok": bool, "content": str, "raw": dict, "error": str}
        """
        ...

    # ------------------------------------------------------------------
    # LLM call helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Execute an LLM call through the bound provider.

        Args:
            system_prompt: System prompt text.
            user_prompt: User prompt text.
            options: Optional call-level overrides {"model_tier", "temperature", "max_tokens", "json_mode"}.

        Returns:
            {"ok": bool, "content": str, "raw": str, "tokens": int, "error": str}
        """
        if self._provider is None:
            return {"ok": False, "content": "", "raw": "", "tokens": 0, "error": "No provider configured"}

        opts = options or {}
        tier = opts.get("model_tier", self.model_tier)
        model = self._provider.get_model_name(tier) or self._provider._config.get("model", "")

        _log.info("%s → request (model: %s, tier: %s)", self.agent_name, model, tier)
        log_agent_request(self.agent_name, user_prompt)

        result = await self._provider.chat(system_prompt, user_prompt, opts)

        if result.get("ok", False):
            _log.info("%s ← response (tokens: %d)", self.agent_name, result.get("tokens", 0))
            log_agent_response(self.agent_name, result.get("content", ""), result.get("tokens", 0), True)
        else:
            _log.error("%s ✗ error: %s", self.agent_name, result.get("error", "unknown"))
            log_agent_response(self.agent_name, "", 0, False)

        return result

    # ------------------------------------------------------------------
    # JSON parsing (delegates to utils)
    # ------------------------------------------------------------------

    def _parse_json_response(self, response: dict) -> dict:
        """Extract a JSON dict from an LLM response using 3-strategy parsing.

        Args:
            response: Raw response dict from _call_llm.

        Returns:
            {"ok": bool, "data": dict, "error": str}
        """
        return parse_json_response(response)

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def _log_info(self, msg: str) -> None:
        _log.info("%s %s", self.agent_name, msg)

    def _log_warn(self, msg: str) -> None:
        _log.warning("%s %s", self.agent_name, msg)

    def _log_error(self, msg: str) -> None:
        _log.error("%s %s", self.agent_name, msg)
