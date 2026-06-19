"""MaNA v4 Memory System.

基于 Generative Agents (Stanford) 记忆流 + 三因子检索设计：
  score = α·recency + β·relevance + γ·importance

Memory 按 agent_id 分区存储：
  - "director"       → 导演记忆（决策历史、被拒计划）
  - "world"          → 世界记忆（全局叙事、长期摘要）
  - "<char_id>"      → 角色记忆（经历、状态变化链、知识）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from math import exp
from typing import Any, Optional

_log = logging.getLogger("MaNA.Memory")


# ============================================================
# Data structures
# ============================================================


@dataclass
class MemoryEntry:
    """单条记忆条目。

    Attributes:
        agent_id: 所属 agent（"director" / "world" / char_id）
        content: 自然语言描述
        timestamp: 节拍号（全局递增）
        importance: 重要度 1-10（LLM 打分或默认值）
        memory_type: "observation" / "decision" / "reflection" / "state_change" / "knowledge"
        tags: 标签 ["服装", "位置", "情绪", "冲突", ...]
        source: 来源层（"L1 Director" / "L2R2" / "Auditor" / "ContinuityChecker" / ...）
    """
    agent_id: str
    content: str
    timestamp: int
    importance: float = 5.0
    memory_type: str = "observation"
    tags: list[str] = field(default_factory=list)
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            agent_id=str(d.get("agent_id", "")),
            content=str(d.get("content", "")),
            timestamp=int(d.get("timestamp", 0)),
            importance=float(d.get("importance", 5.0)),
            memory_type=str(d.get("memory_type", "observation")),
            tags=list(d.get("tags", []) or []),
            source=str(d.get("source", "")),
        )


# ============================================================
# MemoryManager
# ============================================================


class MemoryManager:
    """统一记忆管理器。

    管理所有 agent 的 memory_stream，提供检索和反思能力。
    底层是 append-only 的流，通过三因子排序做检索。
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self.config: dict = config or {}

        # memory_stream[agent_id] = [MemoryEntry, ...]
        self.memory_stream: dict[str, list[MemoryEntry]] = {}

        # 快捷引用
        self.director_memory: list[MemoryEntry] = []   # memory_stream["director"]
        self.character_memory: dict[str, list[MemoryEntry]] = {}  # memory_stream[char_id]

        # 内部: 累计 importance（用于触发 reflection）
        self._cumulative_importance: dict[str, float] = {}

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def add_memory(self, entry: MemoryEntry) -> None:
        """添加一条记忆。

        - 自动累加 importance 用于后续 reflection 触发
        - 超过 max_entries 时 FIFO 驱逐
        """
        aid = entry.agent_id

        # 确保流存在
        if aid not in self.memory_stream:
            self.memory_stream[aid] = []
            if aid == "director":
                self.director_memory = self.memory_stream[aid]
            elif aid != "world":
                self.character_memory[aid] = self.memory_stream[aid]

        stream = self.memory_stream[aid]
        stream.append(entry)

        # 累计 importance
        self._cumulative_importance[aid] = \
            self._cumulative_importance.get(aid, 0.0) + entry.importance

        # FIFO 驱逐
        max_entries = int(self.config.get("max_entries_per_agent", 200))
        while len(stream) > max_entries:
            removed = stream.pop(0)
            self._cumulative_importance[aid] = \
                max(0.0, self._cumulative_importance.get(aid, 0.0) - removed.importance)

    def add_observation(self, agent_id: str, content: str, *,
                        timestamp: int, importance: float = 3.0,
                        tags: list[str] = None, source: str = "") -> None:
        """快捷添加观察型记忆。"""
        self.add_memory(MemoryEntry(
            agent_id=agent_id, content=content, timestamp=timestamp,
            importance=importance, memory_type="observation",
            tags=tags or [], source=source,
        ))

    def add_decision(self, agent_id: str, content: str, *,
                     timestamp: int, importance: float = 6.0,
                     tags: list[str] = None, source: str = "") -> None:
        """快捷添加决策型记忆（默认重要度更高）。"""
        self.add_memory(MemoryEntry(
            agent_id=agent_id, content=content, timestamp=timestamp,
            importance=importance, memory_type="decision",
            tags=tags or [], source=source,
        ))

    def add_state_change(self, agent_id: str, content: str, *,
                         timestamp: int, importance: float = 4.0,
                         tags: list[str] = None, source: str = "") -> None:
        """快捷添加状态变化记忆。"""
        self.add_memory(MemoryEntry(
            agent_id=agent_id, content=content, timestamp=timestamp,
            importance=importance, memory_type="state_change",
            tags=tags or [], source=source,
        ))

    # ------------------------------------------------------------------
    # 读操作 — 三因子检索
    # ------------------------------------------------------------------

    def retrieve(self, agent_id: str, query: str,
                 top_k: int = 5, current_beat: int = 0) -> list[MemoryEntry]:
        """三因子检索记忆。

        检索公式:
            score = α·recency + β·relevance + γ·importance

        Args:
            agent_id: 目标 agent
            query: 查询上下文（用于 relevance 评分）
            top_k: 返回数量上限
            current_beat: 当前节拍号（用于计算 recency 衰减）
        """
        stream = self.memory_stream.get(agent_id, [])
        if not stream:
            return []

        # 配置参数
        alpha = float(self.config.get("recency_weight", 0.4))
        beta = float(self.config.get("relevance_weight", 0.3))
        gamma = float(self.config.get("importance_weight", 0.3))
        decay_lambda = float(self.config.get("decay_lambda", 0.05))

        # 先按 recency 快速过滤：只取最近 N 条（避免每次检索全量）
        recency_window = int(self.config.get("retrieve_recency_window", 100))
        if len(stream) > recency_window:
            stream = stream[-recency_window:]

        # 计算 recency 分数
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in stream:
            recency = exp(-decay_lambda * (current_beat - entry.timestamp))
            importance = entry.importance / 10.0
            # relevance 先用 importance 作为代理分数
            # 精确 relevance 需要 LLM 打分，可在外层调用时重写
            relevance = importance

            score = alpha * recency + beta * relevance + gamma * importance
            scored.append((score, entry))

        # 按分数降序，取 top_k
        scored.sort(key=lambda x: -x[0])
        return [entry for _, entry in scored[:top_k]]

    def retrieve_director(self, query: str = "", top_k: int = 5,
                          current_beat: int = 0) -> list[MemoryEntry]:
        """快捷检索导演记忆。"""
        return self.retrieve("director", query, top_k=top_k, current_beat=current_beat)

    def retrieve_character(self, char_id: str, query: str = "",
                           top_k: int = 3, current_beat: int = 0) -> list[MemoryEntry]:
        """快捷检索角色记忆。"""
        return self.retrieve(char_id, query, top_k=top_k, current_beat=current_beat)

    # ------------------------------------------------------------------
    # Reflection
    # ------------------------------------------------------------------

    def should_reflect(self, agent_id: str) -> bool:
        """检查是否达到反思阈值。"""
        threshold = float(self.config.get("reflection_threshold", 30))
        return self._cumulative_importance.get(agent_id, 0.0) >= threshold

    def mark_reflected(self, agent_id: str) -> None:
        """标记已反思（重置累计 importance）。"""
        self._cumulative_importance[agent_id] = 0.0

    def get_memory_text(self, entries: list[MemoryEntry],
                        max_chars: int = 500) -> str:
        """将记忆条目列表格式化为供 LLM 读取的文本。"""
        lines: list[str] = []
        for entry in entries[-20:]:  # 最多取最近 20 条
            ts = entry.timestamp
            tags_str = f"[{', '.join(entry.tags)}]" if entry.tags else ""
            lines.append(f"#{ts} ({entry.memory_type}){tags_str}: {entry.content}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """序列化为字典（用于 WorldState 持久化）。"""
        result: dict[str, list[dict]] = {}
        for aid, stream in self.memory_stream.items():
            result[aid] = [e.to_dict() for e in stream]
        return result

    def from_dict(self, data: dict) -> None:
        """从字典恢复记忆。"""
        self.memory_stream = {}
        self.director_memory = []
        self.character_memory = {}
        self._cumulative_importance = {}

        for aid, entries in (data or {}).items():
            stream = [MemoryEntry.from_dict(e) for e in (entries or [])]
            self.memory_stream[aid] = stream
            if aid == "director":
                self.director_memory = stream
            elif aid != "world":
                self.character_memory[aid] = stream

    # ------------------------------------------------------------------
    # 压缩（Compaction）
    # ------------------------------------------------------------------

    def compact(self, agent_id: str = "", current_beat: int = 0,
                max_entries: int = 100, keep_summary: bool = True) -> int:
        """压缩指定 agent 的记忆流，保留最近重要记忆，将旧记忆合并为摘要。

        对每个 agent 的记忆流，将超过 retention_window 且重要性低的条目
        压缩成一条 summaries。模仿 MemGPT 的递归摘要思路。

        Args:
            agent_id: 目标 agent，空字符串则压缩所有
            current_beat: 当前节拍号（用于判断新旧）
            max_entries: 截断上限（软上限，超出才压缩）
            keep_summary: 是否保留摘要（否则直接丢弃旧低重要度记忆）

        Returns:
            压缩后减少的条目数
        """
        retention_window = int(self.config.get("retention_window", 50))
        # 低重要度阈值：低于此值且较旧的记忆会被压缩
        low_importance = float(self.config.get("low_importance_threshold", 4.0))

        targets: list[str] = []
        if agent_id:
            if agent_id in self.memory_stream:
                targets.append(agent_id)
        else:
            targets = list(self.memory_stream.keys())

        total_removed = 0

        for aid in targets:
            stream = self.memory_stream.get(aid, [])
            if len(stream) <= max_entries:
                continue

            _log.info("压缩记忆: agent=%s, 当前%d条, 目标<=%d",
                      aid, len(stream), max_entries)

            # 保留窗口内的（最近 N 拍）
            boundary_beat = current_beat - retention_window
            recent: list[MemoryEntry] = []
            old_low: list[MemoryEntry] = []  # 旧 + 低重要度
            old_high: list[MemoryEntry] = []  # 旧 + 高重要度

            for entry in stream:
                if entry.timestamp >= boundary_beat:
                    recent.append(entry)
                elif entry.importance < low_importance and entry.memory_type != "reflection":
                    old_low.append(entry)
                else:
                    old_high.append(entry)

            # 需要压缩的旧低重要度记忆
            if not old_low:
                continue  # 没有可压缩的

            # 构建新流：recent + old_high + summaries
            new_stream = list(recent)
            new_stream.extend(old_high)

            total_removed += len(old_low)

            if keep_summary and old_low:
                # 将 old_low 压缩为一条摘要
                content_parts = []
                for entry in old_low:
                    content_parts.append(f"#{entry.timestamp}: {entry.content}")
                summary_text = "；".join(content_parts)
                # 截断摘要长度
                if len(summary_text) > 300:
                    summary_text = summary_text[:300] + "..."

                compressed = MemoryEntry(
                    agent_id=aid,
                    content=f"[压缩摘要] {summary_text}",
                    timestamp=current_beat,
                    importance=5.0,  # 摘要中等重要
                    memory_type="reflection",
                    tags=old_low[0].tags if old_low[0].tags else ["compressed"],
                    source="MemoryCompact",
                )
                new_stream.append(compressed)

            self.memory_stream[aid] = new_stream
            # 更新快捷引用
            if aid == "director":
                self.director_memory = new_stream
            elif aid != "world":
                self.character_memory[aid] = new_stream

            _log.info("压缩完成: agent=%s, 移除%d条, 剩余%d条",
                      aid, len(old_low), len(new_stream))

        return total_removed

    def compact_if_needed(self, current_beat: int = 0) -> int:
        """检查是否需要压缩（超出上限时自动触发）。

        Returns:
            压缩后减少的条目数
        """
        max_entries = int(self.config.get("max_entries_per_agent", 200))
        total = 0
        for aid in list(self.memory_stream.keys()):
            if len(self.memory_stream[aid]) > max_entries:
                total += self.compact(
                    agent_id=aid, current_beat=current_beat,
                    max_entries=max_entries,
                )
        return total
