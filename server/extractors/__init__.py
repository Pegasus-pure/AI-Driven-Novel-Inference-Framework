# -*- coding: utf-8 -*-
"""Canon 提取器模块

提供提取器注册表和工厂函数，支持:
    - 内置提取器: "llm", "regex"
    - 第三方自定义提取器注册

使用示例:
    from server.extractors import get_extractor, register_extractor

    # 获取 LLM 提取器
    extractor = get_extractor("llm")

    # 注册自定义提取器
    class MyExtractor(CanonExtractor):
        ...
    register_extractor("my_extractor", MyExtractor)
"""

from __future__ import annotations

from typing import Any, Optional, Type

from .base import CanonExtractor
from .llm_extractor import LLMExtractor
from .regex_extractor import RegexExtractor

# ────────────────────────────────────────────────
# 内置提取器注册表
# ────────────────────────────────────────────────

_REGISTRY: dict[str, Type[CanonExtractor]] = {
    "llm": LLMExtractor,
    "regex": RegexExtractor,
}

# ────────────────────────────────────────────────
# 工厂函数
# ────────────────────────────────────────────────


def get_extractor(name: str, **kwargs: Any) -> CanonExtractor:
    """根据名称获取提取器实例

    Args:
        name: 提取器名称（"llm", "regex", 或自定义名称）
        **kwargs: 传递给提取器构造函数的参数

    Returns:
        提取器实例

    Raises:
        ValueError: 未知的提取器名称
    """
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(
            f"未知提取器: {name}。"
            f"可用提取器: {available}。"
            f"使用 register_extractor() 注册自定义提取器。"
        )

    extractor_cls = _REGISTRY[name]
    return extractor_cls(**kwargs)


def register_extractor(name: str, cls: Type[CanonExtractor]) -> None:
    """注册自定义提取器（供第三方插件使用）

    Args:
        name: 提取器名称（唯一标识符）
        cls: 提取器类（必须继承 CanonExtractor）

    Example:
        class MyExtractor(CanonExtractor):
            async def extract(self, text, filename, provider=None):
                ...

        register_extractor("my_extractor", MyExtractor)
    """
    if not issubclass(cls, CanonExtractor):
        raise TypeError(f"提取器必须继承 CanonExtractor: {cls}")

    _REGISTRY[name] = cls
    import logging
    _log = logging.getLogger("Rain.Extractors")
    _log.info("注册自定义提取器: %s -> %s", name, cls.__name__)


def list_extractors() -> dict[str, str]:
    """列出所有已注册的提取器

    Returns:
        {名称: 类名} 字典
    """
    return {name: cls.__name__ for name, cls in _REGISTRY.items()}
