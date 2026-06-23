# -*- coding: utf-8 -*-
"""Rain Web — 统一日志格式化配置

各模块导入此模块获取已配置的 logger，而非各自调用 logging.basicConfig。
"""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 logger，确保格式已配置。

    Args:
        name: Logger 名称（如 "Rain.Server", "Rain.Pipeline"）

    Returns:
        已配置格式的 Logger 实例
    """
    log = logging.getLogger(name)

    # 仅在首次调用时添加 handler（防止重复）
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        log.addHandler(handler)
        log.setLevel(logging.DEBUG)

    return log
