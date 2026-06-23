# -*- coding: utf-8 -*-
"""存档管理器 — saves/ 目录 JSON 读写

3 个存档槽位 (slot_0, slot_1, slot_2)，JSON 格式。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger("Rain.Save")


class SaveManager:
    """存档管理器

    管理 saves/ 目录下的 3 个 JSON 存档槽位。
    """

    DEFAULT_SLOTS: int = 3

    def __init__(self, saves_dir: str = "saves") -> None:
        """初始化存档管理器

        Args:
            saves_dir: 存档目录路径（相对于项目根目录或绝对路径）
        """
        self._saves_dir = Path(saves_dir)
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """确保存档目录存在"""
        self._saves_dir.mkdir(parents=True, exist_ok=True)

    def _slot_path(self, slot: int) -> Path:
        """获取指定槽位的文件路径"""
        return self._saves_dir / f"slot_{slot}.json"

    # ────────────────────────────────────────────────
    # 存档操作
    # ────────────────────────────────────────────────

    def save(self, slot: int, session: Any, name: str = "") -> dict:
        """保存游戏到指定槽位

        Args:
            slot: 槽位编号 (0, 1, 2)
            session: GameSession 实例
            name: 存档名称（空字符串则自动生成）

        Returns:
            {"slot": int, "name": str, "timestamp": str}
        """
        if not 0 <= slot < self.DEFAULT_SLOTS:
            raise ValueError(f"槽位编号必须在 0-{self.DEFAULT_SLOTS - 1} 之间")

        # 从 GameSession 获取状态快照
        ws_snapshot = session.world_state.to_dict()
        now = datetime.now(timezone.utc).isoformat()

        # 获取运行 Canon 标题（目录结构模式，仅需 novel_title）
        if hasattr(session, 'canon_manager') and session.canon_manager.is_running():
            # 确保运行 Canon 目录已保存
            try:
                session.canon_manager.save_running_canon()
            except Exception:
                pass

        save_data: dict[str, Any] = {
            "slot": slot,
            "name": name or f"自动存档",
            "timestamp": now,
            "beat_id": f"beat_{session.beat_count:03d}",
            "beat_count": session.beat_count,
            "novel_title": getattr(session, "current_novel", "") or "",
            "game_time": session.world_state.game_time,
            "divergence": session.world_state.world_divergence,
            "player_location": session.world_state.player_location,
            "event_log": session.event_log if hasattr(session, "event_log") else [],
            "soul_protagonist_id": getattr(session, "_soul_protagonist_id", ""),
            "world_state_snapshot": ws_snapshot,
        }

        filepath = self._slot_path(slot)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        return {
            "slot": slot,
            "name": save_data["name"],
            "timestamp": now,
        }

    def load(self, slot: int) -> Optional[dict]:
        """从指定槽位加载存档

        Args:
            slot: 槽位编号

        Returns:
            存档数据字典，或 None（如槽位为空）
        """
        filepath = self._slot_path(slot)
        if not filepath.is_file():
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, IOError) as exc:
            _log.error("加载存档失败: slot=%d, error=%s", slot, exc)
            return None

    def list_slots(self) -> list[dict]:
        """列出所有存档槽位信息

        Returns:
            槽位信息列表 [{"slot": 0, "name": "...", "beat_id": "...", ...}, ...]
        """
        slots: list[dict] = []
        for slot in range(self.DEFAULT_SLOTS):
            filepath = self._slot_path(slot)
            if filepath.is_file():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    slots.append({
                        "slot": data.get("slot", slot),
                        "name": data.get("name", ""),
                        "beat_id": data.get("beat_id", ""),
                        "beat_count": data.get("beat_count", 0),
                        "timestamp": data.get("timestamp", ""),
                        "location": data.get("player_location", ""),
                        "novel_title": data.get("novel_title", ""),
                        "divergence": data.get("divergence", 0.0),
                    })
                except Exception:
                    slots.append({
                        "slot": slot,
                        "name": "(存档已损坏)",
                        "beat_id": "",
                        "timestamp": "",
                        "location": "",
                    })
            else:
                slots.append({
                    "slot": slot,
                    "name": "(空)",
                    "beat_id": "",
                    "timestamp": "",
                    "location": "",
                })
        return slots

    def delete_slot(self, slot: int) -> bool:
        """删除指定槽位的存档

        Args:
            slot: 槽位编号

        Returns:
            是否成功删除
        """
        filepath = self._slot_path(slot)
        if filepath.is_file():
            try:
                filepath.unlink()
                return True
            except OSError:
                return False
        return False
