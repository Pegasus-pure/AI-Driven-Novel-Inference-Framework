# -*- coding: utf-8 -*-
"""Canon 存储后端模块

提供存储后端注册表和工厂函数，支持:
    - 内置存储: "file" (文件系统)
    - 第三方自定义存储后端注册

使用示例:
    from server.storage import get_storage, register_storage

    # 获取文件存储后端
    storage = get_storage("file")

    # 注册自定义存储后端
    class MyStorage(CanonStorage):
        ...
    register_storage("my_storage", MyStorage)
"""

from __future__ import annotations

from typing import Any, Optional, Type

from .base import CanonStorage
from .file_storage import FileStorage

# ────────────────────────────────────────────────
# 内置存储后端注册表
# ────────────────────────────────────────────────

_REGISTRY: dict[str, Type[CanonStorage]] = {
    "file": FileStorage,
}

# ────────────────────────────────────────────────
# 工厂函数
# ────────────────────────────────────────────────


def get_storage(name: str, **kwargs: Any) -> CanonStorage:
    """根据名称获取存储后端实例

    Args:
        name: 存储后端名称（"file" 或自定义名称）
        **kwargs: 传递给存储后端构造函数的参数
                  （如 novel_dir_root="novel"）

    Returns:
        存储后端实例

    Raises:
        ValueError: 未知的存储后端名称
    """
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(
            f"未知存储后端: {name}。"
            f"可用存储后端: {available}。"
            f"使用 register_storage() 注册自定义存储后端。"
        )

    storage_cls = _REGISTRY[name]
    return storage_cls(**kwargs)


def register_storage(name: str, cls: Type[CanonStorage]) -> None:
    """注册自定义存储后端（供第三方插件使用）

    Args:
        name: 存储后端名称（唯一标识符）
        cls: 存储后端类（必须继承 CanonStorage）

    Example:
        class DatabaseStorage(CanonStorage):
            def create_running_canon(self, source_file: str) -> bool:
                ...

        register_storage("database", DatabaseStorage)
    """
    if not issubclass(cls, CanonStorage):
        raise TypeError(f"存储后端必须继承 CanonStorage: {cls}")

    _REGISTRY[name] = cls
    import logging
    _log = logging.getLogger("Rain.Storage")
    _log.info("注册自定义存储后端: %s -> %s", name, cls.__name__)


def list_storages() -> dict[str, str]:
    """列出所有已注册的存储后端

    Returns:
        {名称: 类名} 字典
    """
    return {name: cls.__name__ for name, cls in _REGISTRY.items()}
