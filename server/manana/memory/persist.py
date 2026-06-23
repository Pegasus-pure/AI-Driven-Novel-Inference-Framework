# -*- coding: utf-8 -*-
"""Memory JSONL 持久化层

Agentopia-inspired append-only JSONL persistence.
Every memory entry is one JSON line.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

_log = logging.getLogger("MaNA.Memory.Persist")


class MemoryPersister:
    """JSONL 追加式记忆持久化"""

    def __init__(self, novel_dir_root: str = "novel") -> None:
        self._novel_dir_root: str = novel_dir_root
        self._title: str = ""

    def set_title(self, title: str) -> None:
        """设置当前小说标题（切换小说时调用）"""
        self._title = title

    def _agent_path(self, title: str, agent_id: str) -> Path:
        """novel/{title}/memory/{agent_id}.jsonl"""
        return Path(self._novel_dir_root) / title / "memory" / f"{agent_id}.jsonl"

    def append(self, title: str, agent_id: str, entry: dict) -> None:
        """追加一条记忆到磁盘"""
        path = self._agent_path(title, agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_agent(self, title: str, agent_id: str) -> list[dict]:
        """从磁盘加载某个 agent 的全部记忆"""
        path = self._agent_path(title, agent_id)
        if not path.exists():
            return []
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        _log.warning("跳过损坏的记忆行: %s", line[:80])
        return entries

    def load_all(self, title: str) -> dict[str, list[dict]]:
        """从磁盘加载所有 agent 的记忆 → {agent_id: [entries]}"""
        memory_dir = Path(self._novel_dir_root) / title / "memory"
        if not memory_dir.exists():
            return {}
        result = {}
        for fpath in memory_dir.glob("*.jsonl"):
            agent_id = fpath.stem
            entries = self.load_agent(title, agent_id)
            if entries:
                result[agent_id] = entries
        return result

    def delete_title(self, title: str) -> None:
        """删除整个小说的记忆文件"""
        import shutil
        memory_dir = Path(self._novel_dir_root) / title / "memory"
        if memory_dir.exists():
            shutil.rmtree(memory_dir)
            _log.info("已删除记忆目录: %s", memory_dir)
