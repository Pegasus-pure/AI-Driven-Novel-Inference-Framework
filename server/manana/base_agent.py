"""MaNA v4 Agent Base Class — 模板方法模式重构。

所有叙事 Agent（SceneDirector, MotivationEngine 等）继承自 BaseAgent。
基类提供模板方法 run()，子类只需覆写钩子方法即可。

模板链：_call_llm → parse_output → validate_output → enrich_output → _log_agent_output

v4 增强：
  - _call_llm_with_retry: 至多 3 次自动重试
  - enrich_output: 可选后处理钩子
  - validate_output: 可被子类覆写的验证逻辑
  - 外部 system_prompt 覆盖（通过 input_data["system_prompt"]）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from .providers import BaseProvider
from .utils import parse_json_response, log_agent_request, log_agent_response


_log = logging.getLogger("MaNA.Agent")


class BaseAgent(ABC):
    """Agent 基类 — 模板方法模式

    子类必须覆写:
      - agent_name: str
      - model_tier: str ("strong" | "medium" | "light")
      - build_system_prompt() → str
      - build_user_prompt(input_data: dict) → str

    子类可选覆写:
      - parse_output(raw: dict) → dict
      - validate_output(parsed: dict) → dict
      - enrich_output(validated: dict) → dict
      - _get_llm_options(input_data: dict) → dict
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
    # Template method — 子类可选择性覆写钩子
    # ------------------------------------------------------------------

    async def run(self, input_data: dict) -> dict:
        """模板方法：所有 Agent 共享的调用链

        子类不再需要覆写 run()，只需覆写钩子方法：
          - build_system_prompt()       [必须]
          - build_user_prompt()         [必须]
          - _get_llm_options()          [可选, 默认 json_mode + temp=0.7]
          - _pre_llm_hook(input_data)   [可选, LLM 调用前日志/预处理]
          - _post_process(data, input_data, raw_content) [可选, 解析后处理]
          - parse_output()              [可选]
          - validate_output()           [可选]
          - enrich_output()             [可选]

        Args:
            input_data: 包含 scene_context / character_outputs 等 Agent 输入

        Returns:
            {"ok": bool, "content": str, "raw": dict, "error": str}
        """
        system_prompt = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        user_prompt = self.build_user_prompt(input_data)

        # LLM 调用前钩子
        self._pre_llm_hook(input_data)

        llm_options = self._get_llm_options(input_data)
        raw_response = await self._call_llm_with_retry(system_prompt, user_prompt, llm_options)

        if not raw_response.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": raw_response.get("error", "LLM call failed")}

        parsed = self.parse_output(raw_response)
        if parsed.get("error", ""):
            return {"ok": False, "content": raw_response.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        processed = self._post_process(data, input_data, raw_response.get("content", ""))

        validated = self.validate_output(processed)
        enriched = self.enrich_output(validated)

        self._log_agent_output(enriched)
        return {"ok": True, "content": raw_response.get("content", ""), "raw": enriched}

    # ------------------------------------------------------------------
    # 可覆写的钩子方法
    # ------------------------------------------------------------------

    @abstractmethod
    def build_system_prompt(self) -> str:
        """构建系统 prompt。必须覆写。"""
        ...

    @abstractmethod
    def build_user_prompt(self, input_data: dict) -> str:
        """从输入数据构建用户 prompt。必须覆写。"""
        ...

    def _get_llm_options(self, input_data: dict) -> dict[str, Any]:
        """获取 LLM 调用选项。子类可覆写以自定义 temperature / json_mode 等。
        
        默认使用 json_mode，temperature=0.7。
        """
        return {"json_mode": True, "temperature": 0.7}

    def parse_output(self, raw_response: dict) -> dict:
        """解析 LLM 原始输出为结构化 JSON。

        子类可覆写（例如 SceneComposer 需 strip JSON）。
        默认使用 3 策略 JSON 解析。

        Args:
            raw_response: _call_llm 返回的完整响应 dict

        Returns:
            {"ok": bool, "data": dict, "error": str}
        """
        return parse_json_response(raw_response)

    def validate_output(self, parsed: dict) -> dict:
        """验证已解析的输出。

        子类可覆写以添加自定义校验（如数值范围、必填字段）。
        默认返回原值。

        Args:
            parsed: parse_output 返回的 data dict

        Returns:
            验证后的 dict（验证失败时返回空 dict 或带 error 标记）
        """
        return parsed

    def enrich_output(self, validated: dict) -> dict:
        """后处理增强钩子。

        子类可覆写以注入额外字段、补齐默认值、执行转换。

        Args:
            validated: validate_output 返回的 dict

        Returns:
            增强后的最终 raw dict
        """
        return validated

    # ------------------------------------------------------------------
    # v5 新增钩子 — 消除子类 run() 覆写
    # ------------------------------------------------------------------

    def _pre_llm_hook(self, input_data: dict) -> None:
        """LLM 调用前钩子。子类可覆写以添加日志或预处理。

        默认：打印 agent_name + model_tier 日志。
        """
        model_name = self.get_model_name()
        self._log_info(f"→ 开始 (model: {model_name or '?'})")

    def _post_process(self, data: dict, input_data: dict, raw_content: str) -> dict:
        """LLM 响应解析后处理钩子。

        子类可覆写以：
          - 注入额外字段到 data
          - 转换/清洗数据
          - 计算统计信息

        Args:
            data: parse_output 返回的 data dict
            input_data: 原始输入（含 scene_context / character 等）
            raw_content: LLM 原始响应文本

        Returns:
            处理后的 data dict
        """
        return data

    # ------------------------------------------------------------------
    # LLM 调用（带重试）
    # ------------------------------------------------------------------

    async def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        options: dict[str, Any] = None,
        max_retries: int = 5,
    ) -> dict:
        """带自动重试的 LLM 调用。

        仅对 JSON 解析错误和验证失败进行重试。
        非 JSON 错误（连接超时等）直接返回失败。

        Args:
            system_prompt: 系统 prompt
            user_prompt: 用户 prompt
            options: LLM 调用选项
            max_retries: 最大重试次数（默认 5）

        Returns:
            {"ok": bool, "content": str, "raw": str, "tokens": int, "error": str}
        """
        opts = options or {}
        last_error = ""

        for attempt in range(max_retries):
            if attempt > 0:
                _log.warning("%s 第 %d 次重试 (上次错误: %s)", self.agent_name, attempt + 1, last_error)
                # ★ 每次重试翻倍 max_tokens，应对 JSON 输出截断
                current_max = int(opts.get("max_tokens", 0))
                if current_max == 0 and hasattr(self, '_provider'):
                    current_max = getattr(self._provider, 'max_tokens', 1024)
                if current_max > 0:
                    opts["max_tokens"] = current_max * 2

            response = await self._call_llm(system_prompt, user_prompt, opts)
            if not response.get("ok", False):
                # 非 JSON 解析错误（如网络超时）——直接返回，不重试
                return response

            # 尝试解析
            parsed = parse_json_response(response)
            if not parsed.get("error", ""):
                # 解析成功
                return response

            last_error = str(parsed.get("error", "parse failed"))

        # 重试耗尽
        _log.error("%s 重试 %d 次后仍失败: %s", self.agent_name, max_retries, last_error)
        return {"ok": False, "content": "", "raw": "", "tokens": 0, "error": f"Retry exhausted: {last_error}"}

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        options: dict[str, Any] = None,
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

    def _log_agent_output(self, output_data: dict) -> None:
        """记录 Agent 输出摘要。子类可覆写以输出更详细的信息。"""
        key_info = output_data if isinstance(output_data, dict) else {}
        _log.info("%s → 输出: %s", self.agent_name, str(key_info)[:200])

    def _log_info(self, msg: str) -> None:
        _log.info("%s %s", self.agent_name, msg)

    def _log_warn(self, msg: str) -> None:
        _log.warning("%s %s", self.agent_name, msg)

    def _log_error(self, msg: str) -> None:
        _log.error("%s %s", self.agent_name, msg)
