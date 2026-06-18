"""Utility functions for MaNA v4 Python port.

Provides JSON parsing strategies, logging configuration, and helper functions
that are shared across the pipeline.
"""

import json
import logging
import re
import time
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_logger: Optional[logging.Logger] = None
_beat_id: str = "beat_000"


def get_logger(name: str = "MaNA") -> logging.Logger:
    """Get or create a MaNA logger instance."""
    global _logger
    if _logger is None:
        _logger = logging.getLogger(name)
        if not _logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S",
            ))
            _logger.addHandler(handler)
            _logger.setLevel(logging.DEBUG)
    return _logger


def set_current_beat(beat_id: str) -> None:
    """Set the current beat ID for contextual logging."""
    global _beat_id
    _beat_id = beat_id


def log_layer(layer: str, msg: str) -> None:
    """Log a pipeline layer event."""
    get_logger().info("[%s] [%s] %s", _beat_id, layer, msg)


def log_agent_request(agent_name: str, prompt: str) -> None:
    """Log an agent's LLM request."""
    preview = prompt[:200].replace("\n", " ")
    get_logger().debug("[%s] [%s] → request: %s...", _beat_id, agent_name, preview)


def log_agent_response(agent_name: str, content: str, tokens: int, success: bool) -> None:
    """Log an agent's LLM response."""
    status = "✓" if success else "✗"
    preview = content[:200].replace("\n", " ")
    get_logger().debug("[%s] [%s] ← %s (%d tokens): %s...",
                       _beat_id, agent_name, status, tokens, preview)


def log_error(agent_name: str, msg: str) -> None:
    """Log an agent error."""
    get_logger().error("[%s] [%s] ERROR: %s", _beat_id, agent_name, msg)


def log_warning(agent_name: str, msg: str) -> None:
    """Log an agent warning."""
    get_logger().warning("[%s] [%s] WARNING: %s", _beat_id, agent_name, msg)


# ---------------------------------------------------------------------------
# JSON Parsing — 3-strategy extraction from LLM responses
# ---------------------------------------------------------------------------


def parse_json_response(response: dict) -> dict:
    """Extract a JSON object from an LLM response string.

    Three strategies, tried in order:
      1. Direct parse of the entire content.
      2. Extract from markdown ```json ... ``` code blocks.
      3. Regex match the outermost { ... } braces.

    Args:
        response: {"ok": bool, "content": str, ...}

    Returns:
        {"ok": bool, "data": dict, "error": str}
    """
    if not response.get("ok", False):
        return {"ok": False, "data": {}, "error": response.get("error", "LLM call failed")}

    content: str = response.get("content", "") or ""
    if not content.strip():
        return {"ok": False, "data": {}, "error": "Empty LLM response"}

    # Strategy 1: direct parse
    data = _try_parse_json(content)
    if data:
        return {"ok": True, "data": data, "error": ""}

    # Strategy 2: markdown code block
    code_block = _extract_markdown_json(content)
    if code_block:
        data = _try_parse_json(code_block)
        if data:
            return {"ok": True, "data": data, "error": ""}

    # Strategy 3: outermost braces
    brace_content = _extract_brace_block(content)
    if brace_content:
        data = _try_parse_json(brace_content)
        if data:
            return {"ok": True, "data": data, "error": ""}

    return {
        "ok": False,
        "data": {},
        "error": f"Failed to parse JSON from response: {content[:200]}",
    }


def _try_parse_json(text: str) -> dict:
    """Attempt to parse text as JSON. Returns empty dict on failure."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _extract_markdown_json(text: str) -> str:
    """Extract content from ```json ... ``` or ``` ... ``` code blocks."""
    # Try ```json first
    pattern = r"```json\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try generic ``` ```
    pattern = r"```\s*\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return ""


def _extract_brace_block(text: str) -> str:
    """Extract the outermost { ... } block using brace counting."""
    start = text.find("{")
    if start == -1:
        return ""

    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return ""


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


async def retry_with_backoff(
    coro_factory,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> dict:
    """Execute an async callable with exponential backoff retry.

    Args:
        coro_factory: An async callable (no args) that returns a dict with "ok".
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubles each retry).

    Returns:
        The first successful result, or the last failure.
    """
    last_result: dict = {}
    for attempt in range(max_retries + 1):
        result = await coro_factory()
        if result.get("ok", False):
            return result
        last_result = result
        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            get_logger().warning(
                "Retry %d/%d after %.2fs: %s",
                attempt + 1, max_retries, delay, result.get("error", "?"),
            )
            await _async_sleep(delay)
    return last_result


async def _async_sleep(seconds: float) -> None:
    """Async sleep wrapper (for testability)."""
    import asyncio
    await asyncio.sleep(seconds)


# ---------------------------------------------------------------------------
# Trace saving
# ---------------------------------------------------------------------------

_traces: dict[str, list[dict]] = {}


def save_trace(beat_id: str, trace_entry: dict) -> None:
    """Save a pipeline trace entry for a beat."""
    _traces.setdefault(beat_id, []).append(trace_entry)


def save_traces(beat_id: str) -> None:
    """Persist all traces for a beat (no-op in pure Python, logs summary)."""
    entries = _traces.get(beat_id, [])
    if entries:
        get_logger().info("[%s] Saved %d trace entries", beat_id, len(entries))


def get_traces(beat_id: str) -> list[dict]:
    """Retrieve saved traces for a beat."""
    return _traces.get(beat_id, [])


def clear_traces() -> None:
    """Clear all saved traces."""
    _traces.clear()
