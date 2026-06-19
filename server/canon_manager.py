# -*- coding: utf-8 -*-
"""Canon 目录结构管理器 — Canon 从单文件改为目录存储

职责:
  - 从初始 Canon JSON 创建运行目录 (novel/{title}/)
  - 加载/保存运行 Canon（目录结构）
  - 条目 CRUD（角色、地点、世界观规则）
  - 角色软删除（标记死亡而非移除）
  - 自动 ID 生成（通过存储后端获取当前最大 ID）

架构:
  - 此类作为高层管理器，处理业务逻辑
  - 存储操作委托给 CanonStorage 接口（可替换）
  - 默认使用 FileStorage（文件系统存储）

目录结构:
  novel/{小说名}/
    meta.json                ← 小说元信息（title, author, genre, extraction_confidence 等）
    rules/
      world_rules.json       ← 世界观规则
    characters/
      char_001.json          ← 每个角色独立文件
      char_002.json
      ...
    locations/
      loc_001.json           ← 每个地点独立文件
      loc_002.json
      ...
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

# 导入存储后端
from .storage import get_storage, CanonStorage
from .storage.file_storage import FileStorage

_log = logging.getLogger("AINovelFramework.CanonManager")


class CanonManager:
    """Canon 目录结构管理器

    管理小说 Canon 为目录结构。
    通过 CanonStorage 接口进行持久化，支持可替换存储后端。

    向后兼容旧的单文件 canon_{title}_running.json 格式（在 FileStorage 中实现）。
    """

    def __init__(
        self,
        novel_dir_root: str = "novel",
        storage: Optional[CanonStorage] = None,
    ) -> None:
        """初始化 CanonManager

        Args:
            novel_dir_root: 小说根目录路径（仅当 storage 为 None 时使用）
            storage: Canon 存储后端实例（可选）
                     如果为 None，则创建 FileStorage(novel_dir_root)
        """
        if storage is None:
            storage = FileStorage(novel_dir_root=novel_dir_root)

        self._storage: CanonStorage = storage
        self._running_canon: Optional[dict] = None
        self._current_novel: Optional[str] = None
        self._initial_source: Optional[str] = None

    # ────────────────────────────────────────────────
    # 运行 Canon 生命周期
    # ────────────────────────────────────────────────

    def create_running_canon(self, initial_canon_path: str) -> bool:
        """从初始 Canon JSON 创建运行副本

        委托给存储后端处理。
        如果运行目录已存在，存储后端会跳过（保留已有编辑）。

        Args:
            initial_canon_path: 初始 Canon JSON 文件路径 (如 novel/canon_xxx.json)

        Returns:
            是否成功创建/已存在
        """
        ok = self._storage.create_running_canon(initial_canon_path)
        if ok:
            # 加载到内存
            title = self._extract_title_from_path(initial_canon_path)
            self._running_canon = self._storage.load_running_canon(title)
            if self._running_canon is not None:
                self._current_novel = title
                self._initial_source = initial_canon_path
        return ok

    def load_running_canon(self, title: str) -> Optional[dict]:
        """从存储后端加载运行 Canon

        Args:
            title: 小说标题

        Returns:
            运行 Canon 字典，或 None（不存在时）
        """
        canon_data = self._storage.load_running_canon(title)
        if canon_data is not None:
            self._running_canon = canon_data
            self._current_novel = title
            _log.info(
                "运行 Canon 已加载: %s (%d 角色, %d 地点)",
                title,
                len(canon_data.get("characters", []) or []),
                len(canon_data.get("locations", []) or []),
            )
        else:
            _log.info("运行 Canon 不存在: %s", title)
        return canon_data

    def is_running(self) -> bool:
        """当前是否已加载运行 Canon"""
        return self._running_canon is not None

    def get_running_title(self) -> Optional[str]:
        """获取当前运行 Canon 的标题"""
        return self._current_novel

    # ────────────────────────────────────────────────
    # ID 生成
    # ────────────────────────────────────────────────

    def _generate_id(self, section: str) -> str:
        """自动生成新条目 ID

        通过存储后端获取当前最大 ID，然后 +1。

        Args:
            section: 分区 — 'characters' | 'locations'

        Returns:
            新 ID (如 "char_005", "loc_003")
        """
        if not self._current_novel:
            raise RuntimeError("未设置当前小说")

        # 通过存储后端获取当前最大 ID
        max_idx = self._storage.get_entry_count(self._current_novel, section)

        if section == "characters":
            prefix = "char_"
        elif section == "locations":
            prefix = "loc_"
        else:
            raise ValueError(f"不支持的分区: {section}")

        return f"{prefix}{max_idx + 1:03d}"

    # ────────────────────────────────────────────────
    # 条目 CRUD
    # ────────────────────────────────────────────────

    def save_canon_entry(
        self,
        section: str,
        action: str,
        entry_data: dict,
        entry_id: str = "",
    ) -> tuple:
        """增/改/删 Canon 条目

        Args:
            section: 目标分区 — 'characters' | 'locations' | 'world_rules' | 'meta'
            action: 操作 — 'create' | 'update' | 'delete'
            entry_data: 条目数据
            entry_id: 目标条目 ID（update/delete 时必需）

        Returns:
            (success: bool, canon: dict, message: str)
        """
        if not self._running_canon or not self._current_novel:
            return (False, {}, "未加载运行 Canon，请先选择小说")

        if section == "world_rules":
            return self._save_world_rules(action, entry_data)
        elif section == "meta":
            return self._save_meta(action, entry_data)
        elif section == "characters":
            return self._save_character_entry(action, entry_data, entry_id)
        elif section == "locations":
            return self._save_location_entry(action, entry_data, entry_id)
        else:
            return (False, self._running_canon, f"未知分区: {section}")

    def _save_character_entry(
        self,
        action: str,
        entry_data: dict,
        entry_id: str,
    ) -> tuple:
        """角色的增/改/删

        - create: 生成新 ID → 委托给存储后端写入
        - update: 更新内存 → 委托给存储后端写入
        - delete: 标记死亡 → 委托给存储后端
        """
        chars: list = self._running_canon.setdefault("characters", [])

        if action == "create":
            # 生成新 ID
            new_id = self._generate_id("characters")
            entry_data["id"] = new_id
            # 设置默认值
            entry_data.setdefault("name", "新角色")
            entry_data.setdefault("aliases", [])
            entry_data.setdefault("role", "")
            entry_data.setdefault("personality", {})
            entry_data.setdefault("appearance", "")
            entry_data.setdefault("abilities", [])
            entry_data.setdefault("relationships", [])
            entry_data.setdefault("starting_location", "")
            entry_data.setdefault("key_traits", [])
            entry_data.setdefault("anti_rules", [])
            entry_data.setdefault("status", "alive")
            chars.append(entry_data)
            # 委托给存储后端
            self._storage.save_entry(
                self._current_novel, "characters", new_id, entry_data
            )
            _log.info("角色已新增: %s (%s)", entry_data.get("name", ""), new_id)
            return (True, self._running_canon, new_id)

        elif action == "update":
            for i, c in enumerate(chars):
                c = c if isinstance(c, dict) else {}
                if c.get("id") == entry_id:
                    # 合并更新（不覆盖 id）
                    entry_data.pop("id", None)
                    # 数组字段处理：前端可能传来逗号分隔字符串
                    self._normalize_array_fields(entry_data)
                    chars[i].update(entry_data)
                    # 委托给存储后端
                    self._storage.save_entry(
                        self._current_novel, "characters", entry_id, chars[i]
                    )
                    _log.info("角色已更新: %s", entry_id)
                    return (True, self._running_canon, entry_id)
            return (False, self._running_canon, f"未找到角色: {entry_id}")

        elif action == "delete":
            # 角色删除 = 标记死亡
            return self.mark_character_dead(entry_id, entry_data)

        return (False, self._running_canon, f"未知操作: {action}")

    def _save_location_entry(
        self,
        action: str,
        entry_data: dict,
        entry_id: str,
    ) -> tuple:
        """地点的增/改/删

        - create: 生成新 ID → 委托给存储后端写入
        - update: 更新内存 → 委托给存储后端写入
        - delete: 从列表移除并委托给存储后端删除
        """
        locs: list = self._running_canon.setdefault("locations", [])

        if action == "create":
            new_id = self._generate_id("locations")
            entry_data["id"] = new_id
            entry_data.setdefault("name", "新地点")
            entry_data.setdefault("type", "")
            entry_data.setdefault("parent", "")
            entry_data.setdefault("description", "")
            entry_data.setdefault("atmosphere", "")
            locs.append(entry_data)
            # 委托给存储后端
            self._storage.save_entry(
                self._current_novel, "locations", new_id, entry_data
            )
            _log.info("地点已新增: %s (%s)", entry_data.get("name", ""), new_id)
            return (True, self._running_canon, new_id)

        elif action == "update":
            for i, loc in enumerate(locs):
                loc = loc if isinstance(loc, dict) else {}
                if loc.get("id") == entry_id:
                    entry_data.pop("id", None)
                    locs[i].update(entry_data)
                    # 委托给存储后端
                    self._storage.save_entry(
                        self._current_novel, "locations", entry_id, locs[i]
                    )
                    _log.info("地点已更新: %s", entry_id)
                    return (True, self._running_canon, entry_id)
            return (False, self._running_canon, f"未找到地点: {entry_id}")

        elif action == "delete":
            # 地点删除：直接从列表移除并委托给存储后端
            for i, loc in enumerate(locs):
                loc = loc if isinstance(loc, dict) else {}
                if loc.get("id") == entry_id:
                    removed = locs.pop(i)
                    # 委托给存储后端
                    self._storage.delete_entry(
                        self._current_novel, "locations", entry_id
                    )
                    _log.info("地点已删除: %s (%s)", entry_id, removed.get("name", ""))
                    return (True, self._running_canon, entry_id)
            return (False, self._running_canon, f"未找到地点: {entry_id}")

        return (False, self._running_canon, f"未知操作: {action}")

    def _save_world_rules(self, action: str, entry_data: dict) -> tuple:
        """世界规则的整体更新

        世界规则作为一个整体编辑，不支持逐字段拆分。
        委托给存储后端写入。
        """
        if action == "update":
            world_rules = entry_data.get("world_rules", entry_data)
            # 清理：只保留 world_rules 的顶层字段
            cleaned: dict = {}
            for key in ("era", "magic_system", "society", "species"):
                if key in world_rules:
                    cleaned[key] = world_rules[key]
            # 保留原有字段中未修改的部分
            existing = self._running_canon.get("world_rules", {}) or {}
            for key in ("era", "magic_system", "society", "species"):
                if key not in cleaned and key in existing:
                    cleaned[key] = existing[key]
            self._running_canon["world_rules"] = cleaned
            # 委托给存储后端
            self._storage.save_entry(
                self._current_novel, "world_rules", "", cleaned
            )
            _log.info("世界规则已更新")
            return (True, self._running_canon, "world_rules")
        else:
            return (False, self._running_canon, f"世界规则不支持 {action} 操作")

    def _save_meta(self, action: str, entry_data: dict) -> tuple:
        """小说元信息的整体更新

        委托给存储后端写入。
        """
        if action == "update":
            meta = entry_data.get("meta", entry_data)
            existing_meta = self._running_canon.get("meta", {}) or {}
            if isinstance(existing_meta, dict):
                existing_meta.update(meta)
            else:
                existing_meta = meta
            self._running_canon["meta"] = existing_meta
            # 委托给存储后端
            self._storage.save_entry(
                self._current_novel, "meta", "", existing_meta
            )
            _log.info("小说元信息已更新")
            return (True, self._running_canon, "meta")
        else:
            return (False, self._running_canon, f"元信息不支持 {action} 操作")

    # ────────────────────────────────────────────────
    # 角色死亡标记
    # ────────────────────────────────────────────────

    def mark_character_dead(self, char_id: str, death_info: dict) -> tuple:
        """标记角色死亡（软删除）

        设置 status="dead"，写入死亡地点/时间/原因。
        同时更新所有关联此角色的 relationships。
        委托给存储后端写入。

        Args:
            char_id: 角色 ID
            death_info: {"death_location": str, "death_time": str, "death_cause": str}

        Returns:
            (success: bool, canon: dict, message: str)
        """
        if not self._running_canon or not self._current_novel:
            return (False, {}, "未加载运行 Canon")

        chars: list = self._running_canon.get("characters", []) or []
        target_char = None

        for i, c in enumerate(chars):
            c = c if isinstance(c, dict) else {}
            if c.get("id") == char_id:
                target_char = chars[i]
                break

        if target_char is None:
            return (False, self._running_canon, f"未找到角色: {char_id}")

        # 标记死亡
        target_char["status"] = "dead"
        target_char["death_location"] = str(death_info.get("death_location", ""))
        target_char["death_time"] = str(death_info.get("death_time", ""))
        target_char["death_cause"] = str(death_info.get("death_cause", ""))

        # 更新所有角色中与此角色的 relationships
        for c in chars:
            c = c if isinstance(c, dict) else {}
            rels = c.get("relationships", []) or []
            for rel in rels:
                rel = rel if isinstance(rel, dict) else {}
                if rel.get("target") == char_id:
                    existing_type = str(rel.get("type", ""))
                    if "（已死亡）" not in existing_type:
                        rel["type"] = existing_type + "（已死亡）"
                    rel["intensity"] = 0

        # 委托给存储后端标记死亡
        self._storage.mark_character_dead(
            self._current_novel, char_id, death_info
        )
        _log.info(
            "角色已标记死亡: %s (地点=%s, 时间=%s, 原因=%s)",
            char_id,
            death_info.get("death_location", ""),
            death_info.get("death_time", ""),
            death_info.get("death_cause", ""),
        )
        return (True, self._running_canon, char_id)

    # ────────────────────────────────────────────────
    # 删除实体（硬删除）
    # ────────────────────────────────────────────────

    def delete_canon_entry(self, section: str, entry_id: str) -> tuple:
        """硬删除 Canon 条目

        从内存列表中移除，并委托给存储后端删除。

        Args:
            section: 分区 — 'characters' | 'locations'
            entry_id: 条目 ID

        Returns:
            (success: bool, canon: dict, message: str)
        """
        if not self._running_canon or not self._current_novel:
            return (False, {}, "未加载运行 Canon")

        if section == "characters":
            entities: list = self._running_canon.setdefault("characters", [])
        elif section == "locations":
            entities: list = self._running_canon.setdefault("locations", [])
        else:
            return (False, self._running_canon, f"不支持硬删除分区: {section}")

        # 从内存列表中移除
        removed = None
        for i, e in enumerate(entities):
            e = e if isinstance(e, dict) else {}
            if e.get("id") == entry_id:
                removed = entities.pop(i)
                break

        # 委托给存储后端删除
        if removed is not None:
            self._storage.delete_entry(
                self._current_novel, section, entry_id
            )
            _log.info("条目已硬删除: %s/%s (%s)", section, entry_id, removed.get("name", ""))
            return (True, self._running_canon, entry_id)
        else:
            return (False, self._running_canon, f"未找到条目: {entry_id}")

    # ────────────────────────────────────────────────
    # 持久化
    # ────────────────────────────────────────────────

    def save_running_canon(self) -> None:
        """将当前运行 Canon 全部写回存储后端

        委托给存储后端处理。
        """
        if not self._running_canon or not self._current_novel:
            _log.warning("save_running_canon: 无运行 Canon 或标题")
            return

        self._storage.save_running_canon(
            self._current_novel, self._running_canon
        )
        _log.debug("运行 Canon 已保存: %s", self._current_novel)

    # ────────────────────────────────────────────────
    # 辅助方法
    # ────────────────────────────────────────────────

    @staticmethod
    def _extract_title_from_path(source_path: str) -> str:
        """从 canon 文件路径提取小说标题

        novel/canon_魔王去上學.json → 魔王去上學
        """
        stem = Path(source_path).stem  # canon_魔王去上學
        if stem.startswith("canon_"):
            return stem[len("canon_"):]
        return stem

    @staticmethod
    def _normalize_array_fields(data: dict) -> None:
        """将逗号分隔字符串转换为数组

        处理字段: traits, abilities, key_traits, aliases
        前端以逗号分隔文本输入，后端转为数组。
        """
        array_fields = ["traits", "abilities", "key_traits", "aliases"]

        # 处理扁平字段
        for field in array_fields:
            if field in data and isinstance(data[field], str):
                parts = [s.strip() for s in data[field].split(",") if s.strip()]
                data[field] = parts

        # 处理 personality.traits（嵌套字段）
        if "personality" in data and isinstance(data["personality"], dict):
            personality = data["personality"]
            if "traits" in personality and isinstance(personality["traits"], str):
                parts = [s.strip() for s in personality["traits"].split(",") if s.strip()]
                personality["traits"] = parts

    def get_initial_source(self) -> Optional[str]:
        """获取初始 Canon 源文件路径"""
        return self._initial_source

    def set_storage(self, storage: CanonStorage) -> None:
        """切换存储后端（运行时）

        Args:
            storage: 新的存储后端实例
        """
        self._storage = storage
        _log.info("存储后端已切换: %s", type(storage).__name__)
