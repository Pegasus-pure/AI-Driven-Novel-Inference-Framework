# -*- coding: utf-8 -*-
"""Canon 存储后端抽象接口

定义 CanonStorage 抽象基类，所有存储后端必须实现此接口。
支持文件存储、数据库存储、云存储等可替换实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class CanonStorage(ABC):
    """Canon 存储后端抽象接口

    所有 Canon 存储后端必须继承此类并实现所有抽象方法。

    设计说明:
        - 存储后端负责 Canon 数据的持久化
        - 支持目录结构存储（当前实现）或单文件存储（未来）
        - 实现者需保证线程安全（如果应用在多线程环境）

    接口约定:
        - title 是小说标题，用作存储标识
        - source_file 是初始 Canon JSON 文件路径
        - section 是数据分区：'characters' | 'locations' | 'world_rules' | 'meta'
        - entry_id 是条目 ID（如 'char_001'）
    """

    @abstractmethod
    def create_running_canon(
        self,
        source_file: str,
    ) -> bool:
        """从初始 Canon JSON 创建运行副本

        Args:
            source_file: 初始 Canon JSON 文件路径（如 novel/canon_xxx.json）

        Returns:
            是否成功创建/已存在
        """
        ...

    @abstractmethod
    def load_running_canon(
        self,
        title: str,
    ) -> Optional[dict]:
        """加载运行中的 Canon

        Args:
            title: 小说标题

        Returns:
            运行 Canon 字典，或 None（不存在时）
        """
        ...

    @abstractmethod
    def save_running_canon(
        self,
        title: str,
        canon_data: dict,
    ) -> None:
        """将完整 Canon 数据写入存储

        Args:
            title: 小说标题
            canon_data: 完整 Canon 字典
        """
        ...

    @abstractmethod
    def save_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
        data: dict,
    ) -> bool:
        """保存单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations' | 'world_rules' | 'meta'
            entry_id: 条目 ID
            data: 条目数据

        Returns:
            是否保存成功
        """
        ...

    @abstractmethod
    def load_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
    ) -> Optional[dict]:
        """加载单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'
            entry_id: 条目 ID

        Returns:
            条目数据字典，或 None（不存在时）
        """
        ...

    @abstractmethod
    def delete_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
    ) -> bool:
        """删除单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'
            entry_id: 条目 ID

        Returns:
            是否删除成功
        """
        ...

    @abstractmethod
    def mark_character_dead(
        self,
        title: str,
        char_id: str,
        death_info: dict,
    ) -> bool:
        """标记角色死亡

        Args:
            title: 小说标题
            char_id: 角色 ID
            death_info: {"death_location": str, "death_time": str, "death_cause": str}

        Returns:
            是否标记成功
        """
        ...

    @abstractmethod
    def get_entry_count(
        self,
        title: str,
        section: str,
    ) -> int:
        """获取分区中条目数量

        用于自动 ID 生成（取最大编号 +1）。

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'

        Returns:
            条目数量
        """
        ...
