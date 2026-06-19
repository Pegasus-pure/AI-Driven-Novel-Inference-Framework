# -*- coding: utf-8 -*-
"""Canon 提取器抽象接口

定义 CanonExtractor 抽象基类，所有提取器必须实现 extract() 方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class CanonExtractor(ABC):
    """Canon 提取器抽象接口

    所有 Canon 提取器必须继承此类并实现 extract() 方法。

    设计说明:
        - extract() 是异步方法，支持 LLM 等需要异步操作的提取器
        - provider 参数仅 LLM 提取器需要，其他提取器忽略即可
        - 提取器应该是无状态的，所有配置通过构造函数注入
    """

    @abstractmethod
    async def extract(
        self,
        text: str,
        filename: str,
        provider: Any = None,
    ) -> Optional[dict]:
        """从小说文本提取 Canon 结构化数据

        Args:
            text: 小说原始文本
            filename: 文件名（用于生成 title）
            provider: LLM provider（仅 LLM 提取器需要，可选）

        Returns:
            Canon 字典，失败返回 None

        Raises:
            NotImplementedError: 子类未实现此方法
        """
        ...
