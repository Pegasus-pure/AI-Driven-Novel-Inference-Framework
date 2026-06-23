# -*- coding: utf-8 -*-
"""Canon 冲突种子池 — 从 Canon timeline 加载冲突模板，
供叙事管线随机组合生成变体。

ConflictPool 管理冲突种子的生命周期：
  1. load_from_canon — 从 canon.json timeline[].conflicts 加载种子
  2. get_available_seeds — 获取当前可用种子（未耗尽、强度达标）
  3. get_random_combination — 随机组合冲突模板供 AI 生成变体
  4. add_seeds — 从 StateExtractor 的 new_seed_conflicts 注入新种子
  5. mark_used — 标记种子已被使用
  6. reset_exhausted — 重置所有 exhausted 状态
"""

from __future__ import annotations

import copy
import logging
import random
from typing import Any

_log = logging.getLogger("Rain.ConflictPool")


class ConflictPool:
    """Canon 冲突种子池

    种子是 dict 结构，遵循 ConflictSeed 格式：
    {
        "id": "conflict_001",
        "type": "character_conflict" | "moral_dilemma" | "environmental_crisis"
                | "social_tension" | "mystery",
        "description": "冲突描述",
        "involved_characters": ["char_001", "char_002"],
        "involved_locations": ["loc_001"],
        "intensity": 0.7,
        "times_used": 0,
        "is_exhausted": False,
        "variants": ["变体1", "变体2"]
    }
    """

    CONFLICT_TYPES: tuple[str, ...] = (
        "character_conflict", "moral_dilemma", "environmental_crisis",
        "social_tension", "mystery",
    )

    def __init__(self) -> None:
        self._seeds: list[dict[str, Any]] = []

    # ────────────────────────────────────────────────
    # 加载
    # ────────────────────────────────────────────────

    def load_from_canon(self, canon: dict) -> int:
        """从 canon.json timeline[].conflicts 加载种子。

        遍历 timeline 中的每个事件，从事件的 conflicts 数组中提取
        种子并注册到池中。重复 id 的种子会被跳过（幂等）。

        Args:
            canon: Canon 字典（必须包含 timeline 列表）

        Returns:
            本次加载的新种子数量
        """
        timeline: list[dict] = canon.get("timeline", []) or []
        existing_ids: set[str] = {s.get("id", "") for s in self._seeds if s.get("id")}
        loaded_count: int = 0

        for event in timeline:
            event = event if isinstance(event, dict) else {}
            conflicts: list[dict] = event.get("conflicts", []) or []
            for raw_seed in conflicts:
                raw_seed = raw_seed if isinstance(raw_seed, dict) else {}
                seed_id = str(raw_seed.get("id", ""))
                if not seed_id or seed_id in existing_ids:
                    continue
                seed = self._normalize_seed(raw_seed, event)
                self._seeds.append(seed)
                existing_ids.add(seed_id)
                loaded_count += 1

        _log.info(
            "ConflictPool: 从 canon 加载了 %d 个新种子（共 %d 个）",
            loaded_count,
            len(self._seeds),
        )
        return loaded_count

    @staticmethod
    def _normalize_seed(raw: dict, event: dict) -> dict[str, Any]:
        """规范化单个种子，补全缺失字段"""
        seed_type = str(raw.get("type", "mystery"))
        # 校验 type 合法性
        if seed_type not in ConflictPool.CONFLICT_TYPES:
            _log.warning("未知冲突类型 '%s'，回退为 mystery", seed_type)
            seed_type = "mystery"

        return {
            "id": str(raw.get("id", "")),
            "type": seed_type,
            "description": str(raw.get("description", "")),
            "involved_characters": list(raw.get("involved_characters", []) or []),
            "involved_locations": list(raw.get("involved_locations", []) or []),
            "intensity": float(raw.get("intensity", 0.5)),
            "times_used": int(raw.get("times_used", 0)),
            "is_exhausted": bool(raw.get("is_exhausted", False)),
            "variants": list(raw.get("variants", []) or []),
            "_source_event_id": str(event.get("id", "")),
        }

    # ────────────────────────────────────────────────
    # 查询
    # ────────────────────────────────────────────────

    def get_available_seeds(self, min_intensity: float = 0.3) -> list[dict[str, Any]]:
        """获取可用种子列表。

        可用条件：
          - is_exhausted == False
          - intensity >= min_intensity

        Args:
            min_intensity: 最低强度阈值（默认 0.3）

        Returns:
            可用种子列表
        """
        return [
            copy.deepcopy(s)
            for s in self._seeds
            if not s.get("is_exhausted", False)
            and s.get("intensity", 0.0) >= min_intensity
        ]

    def get_random_combination(self, count: int = 2) -> list[dict[str, Any]]:
        """从可用种子中随机组合指定数量的冲突模板。

        如果可用种子数量不足 count，返回全部可用种子。
        如果没有任何可用种子，返回空列表。

        Args:
            count: 需要的种子数量（默认 2）

        Returns:
            随机选中的种子列表（deep copy）
        """
        available = self.get_available_seeds()
        if not available:
            return []
        if len(available) <= count:
            selected = available
        else:
            selected = random.sample(available, count)

        # 标记 times_used
        selected_ids = {s.get("id", "") for s in selected}
        for seed in self._seeds:
            if seed.get("id", "") in selected_ids:
                seed["times_used"] = seed.get("times_used", 0) + 1

        return selected

    # ────────────────────────────────────────────────
    # 变更
    # ────────────────────────────────────────────────

    def add_seeds(self, new_seeds: list[dict]) -> None:
        """从 StateExtractor 的 new_seed_conflicts 注入新种子。

        重复 id 的种子会被跳过。如果没有 id，自动生成一个。

        Args:
            new_seeds: 新种子字典列表
        """
        existing_ids: set[str] = {s.get("id", "") for s in self._seeds if s.get("id")}
        added_count: int = 0
        existing_count_before = len(self._seeds)

        for raw in new_seeds:
            raw = raw if isinstance(raw, dict) else {}
            seed_id = str(raw.get("id", ""))
            if not seed_id:
                # 自动生成 id
                seed_id = f"conflict_dyn_{existing_count_before + added_count + 1:03d}"
                raw["id"] = seed_id
            if seed_id in existing_ids:
                continue
            seed = self._normalize_seed(raw, {})
            self._seeds.append(seed)
            existing_ids.add(seed_id)
            added_count += 1

        if added_count > 0:
            _log.info("ConflictPool: 注入了 %d 个新种子（共 %d 个）", added_count, len(self._seeds))

    def mark_used(self, seed_id: str) -> None:
        """标记指定种子已被使用（times_used++）。

        如果 times_used >= 3，自动将 is_exhausted 设为 True。

        Args:
            seed_id: 种子 ID
        """
        for seed in self._seeds:
            if seed.get("id", "") == seed_id:
                seed["times_used"] = seed.get("times_used", 0) + 1
                if seed["times_used"] >= 3:
                    seed["is_exhausted"] = True
                    _log.debug("种子 %s 已耗尽（使用 %d 次）", seed_id, seed["times_used"])
                break

    def reset_exhausted(self) -> None:
        """重置所有 exhausted 状态（保留 times_used 计数）。"""
        for seed in self._seeds:
            seed["is_exhausted"] = False
        _log.info("ConflictPool: 所有种子的 exhausted 状态已重置")

    # ────────────────────────────────────────────────
    # 序列化
    # ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """将冲突种子池序列化为字典（用于存档）。"""
        return {
            "seeds": copy.deepcopy(self._seeds),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConflictPool":
        """从字典反序列化冲突种子池。"""
        pool = cls()
        raw_seeds: list[dict] = data.get("seeds", []) or []
        for raw in raw_seeds:
            norm = cls._normalize_seed(raw, {})
            pool._seeds.append(norm)
        _log.info("ConflictPool: 从存档恢复了 %d 个种子", len(pool._seeds))
        return pool

    @property
    def seed_count(self) -> int:
        """当前种子总数"""
        return len(self._seeds)

    @property
    def available_count(self) -> int:
        """当前可用种子数"""
        return len(self.get_available_seeds())

    def __repr__(self) -> str:
        return (
            f"<ConflictPool seeds={self.seed_count} "
            f"available={self.available_count}>"
        )
