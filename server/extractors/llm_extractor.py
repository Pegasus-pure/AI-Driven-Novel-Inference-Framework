# -*- coding: utf-8 -*-
"""LLM 提取器 — 使用 LLM 从小说文本中提取高质量 Canon

⚠️ 重要：此文件不修改 LLM 相关逻辑，仅作为包装器（Wrapper）
   LLM 调用代码保持在原位置不变。

设计:
    - LLMExtractor 是一个薄包装层
    - 实际的 LLM 调用逻辑仍在 novel_loader.py 中（不改动）
    - 此类通过回调函数或直接导入来调用原有逻辑
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .base import CanonExtractor

_log = logging.getLogger("Rain.Extractors.LLM")


class LLMExtractor(CanonExtractor):
    """LLM 提取器（薄包装器）

    此提取器不修改任何 LLM 相关逻辑，仅提供统一的提取器接口。

    使用方式:
        1. 传入一个 callable 作为 llmm_callabl 参数
        2. 或直接调用 novel_loader.py 中的现有函数

    注意:
        - LLM 调用逻辑完全不改动
        - 此类仅提供接口适配
    """

    def __init__(
        self,
        llm_callable: Any = None,
    ) -> None:
        """初始化 LLM 提取器

        Args:
            llmm_callable: LLM 调用回调函数（可选）
                       如果为 None，则使用默认导入方式
        """
        self._llm_callable = llm_callable

    async def extract(
        self,
        text: str,
        filename: str,
        provider: Any = None,
    ) -> Optional[dict]:
        """使用 LLM 从小说文本中提取高质量 Canon 数据

        此方法是 CanonExtractor 接口的实现。
        直接调用 NovelLoader.extract_canon_with_llm()（薄包装，不改动 LLM 逻辑）。

        Args:
            text: 小说全文
            filename: 原始文件名
            provider: BaseProvider 实例（已配置）

        Returns:
            Canon 字典（含角色/地点/世界观/时间线），或 None
        """
        # 直接调用 NovelLoader 的原有方法（薄包装，不改动 LLM 逻辑）
        from ..novel_loader import NovelLoader
        loader = NovelLoader()
        return await loader.extract_canon_with_llm(provider, text, filename)
