# -*- coding: utf-8 -*-
"""Rain Web — 统一异常层级树

各层异常按模块职责分类，支持携带结构化上下文信息（code + context）。
遵循设计文档 P1-C 规范。
"""

from typing import Any, Optional


class RainWebException(Exception):
    """所有自定义异常的基类"""

    def __init__(self, message: str, code: str = "", context: dict = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.context = context or {}


# ── 配置层 ──

class ConfigException(RainWebException):
    """配置加载/解析相关异常"""


# ── Pipeline 层 ──

class PipelineException(RainWebException):
    """Pipeline 编排/执行相关异常"""


class AgentException(PipelineException):
    """Agent 执行异常（含 Agent 名 + 重试次数）"""

    def __init__(self, agent_name: str, message: str, attempt: int = 0) -> None:
        super().__init__(f"[{agent_name}] {message}", code="AGENT_ERROR")
        self.agent_name = agent_name
        self.attempt = attempt


class LLMProviderException(PipelineException):
    """LLM Provider 调用异常（含 Provider 名 + 模型名）"""

    def __init__(self, provider: str, model: str, message: str) -> None:
        super().__init__(f"{provider}/{model}: {message}", code="LLM_ERROR")
        self.provider = provider
        self.model = model


class ValidationException(PipelineException):
    """Agent 输出验证异常（含字段名 + 值）"""

    def __init__(self, field: str, value: Any, message: str) -> None:
        super().__init__(f"{field}={value}: {message}", code="VALIDATION_ERROR")
        self.field = field
        self.value = value


# ── Session 层 ──

class SessionException(RainWebException):
    """游戏会话相关异常"""


class SaveException(SessionException):
    """存档/读档异常"""


class CanonException(SessionException):
    """Canon 数据异常"""


# ── 协议层 ──

class ProtocolException(RainWebException):
    """WebSocket 协议相关异常"""


class WSDisconnectException(ProtocolException):
    """WebSocket 断连异常"""


class MessageFormatException(ProtocolException):
    """WebSocket 消息格式异常"""


# ── 存储层 ──

class StorageException(RainWebException):
    """文件/持久化存储相关异常"""
