"""MaNA v4 LLM Provider subsystem.

Abstract base provider + concrete implementations for:
  - Ollama (local, /api/chat endpoint)
  - OpenAI (standard /v1/chat/completions)
  - DeepSeek (OpenAI-compatible /v1/chat/completions)

Plus a ProviderFactory for constructing providers by type name.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import aiohttp


_log = logging.getLogger("MaNA.Provider")


# ============================================================
# Base Provider
# ============================================================


class BaseProvider(ABC):
    """Abstract base class for all LLM providers.

    Each provider instance is bound to a single tier (strong/medium/light)
    and exposes `chat()` for async LLM calls.
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider type identifier (e.g. "ollama")."""
        ...

    def configure(self, config: dict[str, Any]) -> None:
        """Apply a tier-specific configuration dict."""
        self._config = dict(config)

    def get_model_name(self, tier: str = "") -> str:
        """Return the model name for this provider instance."""
        return str(self._config.get("model", ""))

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Create or return the aiohttp session."""
        if self._session is None or self._session.closed:
            timeout_sec = self._config.get("timeout", 120)
            timeout = aiohttp.ClientTimeout(total=timeout_sec)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        options: Optional[dict[str, Any]] = None,
    ) -> dict:
        """Execute an async chat completion request.

        Args:
            system_prompt: The system prompt text.
            user_message: The user message text.
            options: Optional overrides: {"model", "temperature", "max_tokens", "json_mode"}.

        Returns:
            {"ok": bool, "content": str, "raw": str, "tokens": int, "error": str}
        """
        opts = self._normalize_options(options or {})
        body = self._build_request_body(system_prompt, user_message, opts)
        endpoint = self._config.get("endpoint", "")

        max_retries = self._config.get("max_retries", 3)
        last_result: dict = {}

        for attempt in range(max_retries + 1):
            try:
                result = await self._do_request(endpoint, body)
                if result.get("ok", False):
                    return result
                last_result = result
            except Exception as exc:
                last_result = {"ok": False, "error": str(exc), "content": "", "raw": "", "tokens": 0}

            if attempt < max_retries:
                delay = 1.0 * (2 ** attempt)
                _log.warning("%s retry %d/%d: %s",
                             self.get_provider_name(), attempt + 1, max_retries,
                             last_result.get("error", ""))
                await asyncio.sleep(delay)

        return last_result

    async def embed(self, text: str) -> list[float]:
        """Text embedding. Returns empty list if unsupported by this provider."""
        _log.warning("embed() not implemented for provider: %s", self.get_provider_name())
        return []

    async def cleanup(self) -> None:
        """Release HTTP session resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def health_check(self) -> tuple[bool, str]:
        """快速连通性检查（不执行推理）。

        Returns:
            (ok: bool, message: str)
        """
        return True, ""

    # ------------------------------------------------------------------
    # Internal – to be overridden by subclasses
    # ------------------------------------------------------------------

    def _build_request_body(self, system_prompt: str, user_message: str, options: dict) -> dict:
        """Build the JSON request body for the LLM API call."""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        if options.get("json_mode", False):
            messages.append({"role": "system", "content": "You must respond with valid JSON only."})

        return {
            "model": options.get("model", self._config.get("model", "")),
            "messages": messages,
            "temperature": options.get("temperature", 0.7),
            "max_tokens": options.get("max_tokens", 1024),
            "stream": False,
        }

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP request headers."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._config.get("api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _parse_response(self, body_text: str) -> dict:
        """Parse the raw HTTP response body. Subclasses should override."""
        return {"ok": False, "error": "NOT_IMPLEMENTED", "content": "", "raw": body_text, "tokens": 0}

    async def _do_request(self, url: str, body: dict) -> dict:
        """Execute HTTP POST and return a parsed result dict."""
        session = await self._ensure_session()
        headers = self._build_headers()

        async with session.post(url, json=body, headers=headers) as resp:
            body_text = await resp.text()

            if resp.status != 200:
                return {
                    "ok": False,
                    "error": f"HTTP {resp.status}: {body_text[:500]}",
                    "content": "",
                    "raw": body_text,
                    "tokens": 0,
                }

            return self._parse_response(body_text)

    def _normalize_options(self, options: dict) -> dict:
        """Merge caller options with config defaults."""
        return {
            "model": options.get("model", self._config.get("model", "")),
            "temperature": options.get("temperature", self._config.get("temperature", 0.7)),
            "max_tokens": options.get("max_tokens", self._config.get("max_tokens", 1024)),
            "json_mode": options.get("json_mode", False),
        }


# ============================================================
# OpenAI-compatible response parser (shared by OpenAI & DeepSeek)
# ============================================================


def _parse_openai_response(body_text: str) -> dict:
    """Parse an OpenAI-compatible /v1/chat/completions response.

    Format: {"choices": [{"message": {"content": "...", "role": "assistant"}}], "usage": {...}}
    """
    try:
        resp = json.loads(body_text)
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON parse error: {e}", "content": "", "raw": body_text, "tokens": 0}

    if not isinstance(resp, dict):
        return {"ok": False, "error": "Response is not a dict", "content": "", "raw": body_text, "tokens": 0}

    if "error" in resp:
        err = resp["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        return {"ok": False, "error": msg, "content": "", "raw": body_text, "tokens": 0}

    choices: list = resp.get("choices", [])
    if not choices:
        return {"ok": False, "error": "No choices in response", "content": "", "raw": body_text, "tokens": 0}

    choice = choices[0]
    message = choice.get("message", {})
    content = message.get("content", "") or ""

    tokens = 0
    usage = resp.get("usage", {})
    if usage:
        tokens = usage.get("total_tokens", 0)
    else:
        tokens = len(content) // 4

    return {"ok": True, "content": content, "raw": body_text, "tokens": tokens}


# ============================================================
# Ollama Provider
# ============================================================


class OllamaProvider(BaseProvider):
    """Ollama provider using the native /api/chat endpoint.

    No API key required. Supports embedding via /api/embed.
    """

    def get_provider_name(self) -> str:
        return "ollama"

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        # 不再自动回退到 localhost，允许空端点（由 _ensure_session 报错提示）
        self._config.setdefault("timeout", 120)
        self._config.setdefault("max_retries", 3)

    async def health_check(self) -> tuple[bool, str]:
        """通过 HEAD 请求检查 Ollama 是否可达。"""
        endpoint = self._config.get("endpoint", "")
        if not endpoint:
            return False, "endpoint 未配置"
        try:
            import aiohttp
            base_url = endpoint.replace("/api/chat", "")
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(base_url + "/api/tags") as resp:
                    if resp.status == 200:
                        return True, "Ollama 服务可达"
                    return False, f"Ollama 返回 HTTP {resp.status}"
        except Exception as exc:
            return False, f"Ollama 连接失败: {exc}"

    async def list_models(self) -> tuple[list[str], str]:
        """获取 Ollama 已安装的模型列表。

        Returns:
            (models: list[str], error: str) — 成功时 error 为空字符串
        """
        endpoint = self._config.get("endpoint", "")
        if not endpoint:
            return [], "endpoint 未配置"
        try:
            import aiohttp
            base_url = endpoint.replace("/api/chat", "")
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(base_url + "/api/tags") as resp:
                    if resp.status != 200:
                        return [], f"HTTP {resp.status}"
                    data = await resp.json()
                    models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                    models.sort()
                    return models, ""
        except Exception as exc:
            return [], str(exc)

    def _build_request_body(self, system_prompt: str, user_message: str, options: dict) -> dict:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        body: dict[str, Any] = {
            "model": options.get("model", self._config.get("model", "")),
            "messages": messages,
            "stream": False,
            "think": False,  # disable qwen3 thinking mode
        }

        if "temperature" in options:
            body["temperature"] = options["temperature"]
        if "max_tokens" in options:
            body["max_tokens"] = options["max_tokens"]

        if options.get("json_mode", False):
            messages.append({"role": "system", "content": "You must respond with valid JSON only."})

        return body

    def _parse_response(self, body_text: str) -> dict:
        try:
            resp = json.loads(body_text)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"JSON parse error: {e}", "content": "", "raw": body_text, "tokens": 0}

        if not isinstance(resp, dict):
            return {"ok": False, "error": "Response is not a dict", "content": "", "raw": body_text, "tokens": 0}

        if "error" in resp:
            return {"ok": False, "error": str(resp["error"]), "content": "", "raw": body_text, "tokens": 0}

        message = resp.get("message", {})
        content = message.get("content", "") or ""

        tokens = resp.get("eval_count", len(content) // 4)

        return {"ok": True, "content": content, "raw": body_text, "tokens": tokens}

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings via Ollama /api/embed endpoint."""
        model = self._config.get("embed_model", "nomic-embed-text")
        base_endpoint = self._config.get("endpoint", "http://localhost:11434/api/chat")
        embed_url = base_endpoint.replace("/api/chat", "/api/embed")

        body = {"model": model, "input": text}

        try:
            session = await self._ensure_session()
            async with session.post(embed_url, json=body) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    _log.error("Ollama embed failed: HTTP %d", resp.status)
                    return []
                data = json.loads(raw)
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return [float(v) for v in embeddings[0]]
                return []
        except Exception as exc:
            _log.error("Ollama embed exception: %s", exc)
            return []


# ============================================================
# OpenAI Provider
# ============================================================


class OpenAIProvider(BaseProvider):
    """OpenAI provider using the standard /v1/chat/completions endpoint."""

    def get_provider_name(self) -> str:
        return "openai"

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        if not self._config.get("endpoint"):
            self._config["endpoint"] = "https://api.openai.com/v1/chat/completions"
        self._config.setdefault("timeout", 60)
        self._config.setdefault("max_retries", 3)

    def _parse_response(self, body_text: str) -> dict:
        return _parse_openai_response(body_text)


# ============================================================
# DeepSeek Provider
# ============================================================


class DeepSeekProvider(BaseProvider):
    """DeepSeek provider (OpenAI-compatible /v1/chat/completions endpoint)."""

    def get_provider_name(self) -> str:
        return "deepseek"

    def configure(self, config: dict[str, Any]) -> None:
        super().configure(config)
        if not self._config.get("endpoint"):
            self._config["endpoint"] = "https://api.deepseek.com/v1/chat/completions"
        self._config.setdefault("timeout", 60)
        self._config.setdefault("max_retries", 3)

    def _parse_response(self, body_text: str) -> dict:
        return _parse_openai_response(body_text)


# ============================================================
# Provider Factory
# ============================================================


class ProviderFactory:
    """Static factory for constructing LLM provider instances by type name."""

    _registry: dict[str, type[BaseProvider]] = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "deepseek": DeepSeekProvider,
    }

    @staticmethod
    def create(provider_type: str, config: dict[str, Any]) -> Optional[BaseProvider]:
        """Create and configure a provider instance.

        Args:
            provider_type: "ollama" | "openai" | "deepseek"
            config: Tier configuration dict.

        Returns:
            Configured BaseProvider instance, or None if type unknown.
        """
        provider_type_lower = provider_type.lower()
        cls = ProviderFactory._registry.get(provider_type_lower)
        if cls is None:
            _log.error("Unknown provider type: '%s'", provider_type)
            return None

        provider = cls()
        provider.configure(config)
        return provider

    @staticmethod
    def get_supported_types() -> list[str]:
        """Return list of supported provider type names."""
        return list(ProviderFactory._registry.keys())

    @staticmethod
    def is_supported(provider_type: str) -> bool:
        """Check if a provider type name is supported."""
        return provider_type.lower() in ProviderFactory._registry
