# -*- coding: utf-8 -*-
"""世界状态容器 — Python 移植自 Godot world_state.gd

WorldState 是游戏世界的唯一真相源，所有状态变更都通过此类进行。
"""

from __future__ import annotations

import copy
from typing import Any, Optional


class WorldState:
    """世界状态容器

    持有全部游戏状态数据，支持序列化/反序列化。
    移植自 Godot 版 WorldState 单例。
    """

    # 存档数据版本号（v2: 偏离度 -1.0~1.0, progress→intensity, closed→evolved）
    SAVE_VERSION: int = 2

    def __init__(self) -> None:
        # ── 时间 ──
        self.game_time: str = "第一月·第一日·清晨"
        self.time_index: int = 0

        # ── 位置 ──
        self.player_location: str = ""

        # ── 玩家 ──
        self.player_profile: dict[str, Any] = {
            "traits": [],
            "motivation": "",
            "tendency": "中立",
        }
        self.player_reputation: dict[str, float] = {}

        # ── 角色 ──
        self.characters_state: dict[str, dict] = {}

        # ── 叙事线索 ──
        self.narrative_threads: dict[str, list] = {
            "active": [],
            "evolved": [],
        }

        # ── 动态 Canon ──
        self.dynamic_canon: dict[str, Any] = {
            "character_states": {},
            "evolved_threads": [],
            "new_npcs": [],
            "divergence_events": [],
        }

        # ── 动态 NPC ──
        self.dynamic_npcs: dict[str, dict] = {}

        # ── 动态地点 ──
        self.dynamic_locations: dict[str, dict] = {}

        # ── 世界偏离度（-1.0~1.0，0.0 为 Canon 基线） ──
        self.world_divergence: float = 0.0

        # ── 叙事张力（0.0~1.0，影响叙事紧迫感） ──
        self.narrative_tension: float = 0.5

        # ── 叙事历史 ──
        self.narrative_history: list[dict] = []

        # ── 记忆系统 ──
        self.scene_memory: list[str] = []
        self.long_term_memory: list[str] = []

        # ── 知识图谱 ──
        self.knowledge_graph: dict[str, list[str]] = {}

        # ── 世界规则 ──
        self.custom_world_rules: list[dict] = []

        # ── Canon ──
        self.canon: dict[str, Any] = {}

        # ── 涌现建议队列（不暴露给前端） ──
        self.pending_emergences: dict[str, dict] = {}

        # ── 记忆系统（MemoryManager 懒加载） ──
        self._memory_manager: "MemoryManager" = None  # type: ignore

    # ────────────────────────────────────────────────
    # 序列化
    # ────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """将完整世界状态序列化为字典"""
        return {
            "version": self.SAVE_VERSION,
            "game_time": self.game_time,
            "time_index": self.time_index,
            "player_location": self.player_location,
            "player_profile": copy.deepcopy(self.player_profile),
            "player_reputation": copy.deepcopy(self.player_reputation),
            "characters_state": copy.deepcopy(self.characters_state),
            "narrative_threads": copy.deepcopy(self.narrative_threads),
            "dynamic_canon": copy.deepcopy(self.dynamic_canon),
            "dynamic_npcs": copy.deepcopy(self.dynamic_npcs),
            "dynamic_locations": copy.deepcopy(self.dynamic_locations),
            "world_divergence": self.world_divergence,
            "narrative_tension": self.narrative_tension,
            "narrative_history": copy.deepcopy(self.narrative_history),
            "scene_memory": list(self.scene_memory),
            "long_term_memory": list(self.long_term_memory),
            "knowledge_graph": copy.deepcopy(self.knowledge_graph),
            "custom_world_rules": copy.deepcopy(self.custom_world_rules),
            "canon": copy.deepcopy(self.canon),
            "pending_emergences": copy.deepcopy(self.pending_emergences),
            "memory_stream": self.memory.to_dict() if self._memory_manager else {},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldState":
        """从字典反序列化世界状态（含 v1→v2 存档迁移）"""
        ws = cls()

        version = data.get("version", 0)
        if version > cls.SAVE_VERSION:
            raise ValueError(f"存档版本 {version} 高于当前支持版本 {cls.SAVE_VERSION}")

        ws.game_time = str(data.get("game_time", ws.game_time))
        ws.time_index = int(data.get("time_index", 0))
        ws.player_location = str(data.get("player_location", ""))
        ws.player_profile = copy.deepcopy(data.get("player_profile", ws.player_profile))
        ws.player_reputation = copy.deepcopy(data.get("player_reputation", ws.player_reputation))
        ws.characters_state = copy.deepcopy(data.get("characters_state", ws.characters_state))

        # ── 叙事线索：v1→v2 迁移 ──
        raw_threads: dict = copy.deepcopy(data.get("narrative_threads", {}))
        if version < 2:
            # migration: "closed" → "evolved"
            if "closed" in raw_threads:
                raw_threads["evolved"] = raw_threads.pop("closed")
            elif "evolved" not in raw_threads:
                raw_threads["evolved"] = []
        # 确保 evolved 键存在
        raw_threads.setdefault("active", [])
        raw_threads.setdefault("evolved", [])
        # 迁移活跃线索中的 progress → intensity / 补 complexity
        for t in raw_threads.get("active", []):
            if isinstance(t, dict):
                if "progress" in t and "intensity" not in t:
                    t["intensity"] = t.pop("progress")
                elif "intensity" not in t:
                    t["intensity"] = 0.0
                if "complexity" not in t:
                    t["complexity"] = 0.3
        # 同样处理 evolved 线索
        for t in raw_threads.get("evolved", []):
            if isinstance(t, dict):
                if "progress" in t and "intensity" not in t:
                    t["intensity"] = t.pop("progress")
                elif "intensity" not in t:
                    t["intensity"] = 0.0
                if "complexity" not in t:
                    t["complexity"] = 0.3
        # 清理残留 old key
        raw_threads.pop("closed", None)
        ws.narrative_threads = raw_threads

        # ── 动态 Canon：v1→v2 迁移 ──
        raw_dc: dict = copy.deepcopy(data.get("dynamic_canon", {}))
        if version < 2:
            if "closed_threads" in raw_dc:
                raw_dc["evolved_threads"] = raw_dc.pop("closed_threads")
        raw_dc.setdefault("character_states", {})
        raw_dc.setdefault("evolved_threads", [])
        raw_dc.setdefault("new_npcs", [])
        raw_dc.setdefault("divergence_events", [])
        # 清理残留 old key
        raw_dc.pop("closed_threads", None)
        ws.dynamic_canon = raw_dc

        ws.dynamic_npcs = copy.deepcopy(data.get("dynamic_npcs", ws.dynamic_npcs))
        ws.dynamic_locations = copy.deepcopy(data.get("dynamic_locations", {}))
        ws.world_divergence = float(data.get("world_divergence", 0.0))

        # ── 叙事张力（v2 新增，兼容旧存档使用默认值） ──
        ws.narrative_tension = float(data.get("narrative_tension", 0.5))

        ws.narrative_history = copy.deepcopy(data.get("narrative_history", []))
        ws.scene_memory = list(data.get("scene_memory", []) or [])
        ws.long_term_memory = list(data.get("long_term_memory", []) or [])
        ws.knowledge_graph = copy.deepcopy(data.get("knowledge_graph", {}))
        ws.custom_world_rules = copy.deepcopy(data.get("custom_world_rules", []))
        ws.canon = copy.deepcopy(data.get("canon", {}))
        ws.pending_emergences = copy.deepcopy(data.get("pending_emergences", {}))

        # 恢复记忆
        memory_data = data.get("memory_stream", None)
        if memory_data:
            ws.memory.from_dict(memory_data)

        return ws

    # ────────────────────────────────────────────────
    # 状态变更
    # ────────────────────────────────────────────────

    def apply_patch(self, patch: dict) -> None:
        """应用 Pipeline 返回的状态补丁"""
        # 位置更新
        player_loc = patch.get("player_location", "")
        if player_loc:
            self.player_location = str(player_loc)

        # 角色状态直接覆盖
        chars = patch.get("characters_state", {})
        if isinstance(chars, dict):
            for cid, cs in chars.items():
                if isinstance(cs, dict):
                    existing = self.characters_state.get(cid, {})
                    existing.update(cs)
                    self.characters_state[cid] = existing

        # 活跃线索
        active = patch.get("active_threads", [])
        if isinstance(active, list) and active:
            self.narrative_threads["active"] = active

        # 偏离度增量（支持叙事张力驱动）
        div_delta = patch.get("divergence_delta", None)
        if div_delta is not None:
            self.update_divergence(float(div_delta))

        # 叙事张力更新
        tension = patch.get("narrative_tension", None)
        if tension is not None:
            self.narrative_tension = max(0.0, min(1.0, float(tension)))

    def add_narrative_event(self, summary: str, beat_id: str) -> None:
        """添加一条叙事历史记录"""
        self.narrative_history.append({
            "time": self.game_time,
            "summary": summary,
            "event_id": beat_id,
        })

    def advance_time(self) -> None:
        """推进游戏时间（简化版）"""
        self.time_index += 1
        # 每 3 拍切换时间段
        phase_index = (self.time_index // 3) % 4
        phases = ["清晨", "正午", "黄昏", "深夜"]
        day = (self.time_index // 12) + 1
        month = (day // 30) + 1
        day_in_month = (day % 30) + 1
        self.game_time = f"第{month}月·第{day_in_month}日·{phases[phase_index]}"

    def update_divergence(self, delta: float) -> None:
        """更新世界偏离度（限制在 -1.0~1.0 范围内）"""
        self.world_divergence = max(-1.0, min(1.0, self.world_divergence + delta))

    def add_scene_memory(self, entry: str) -> None:
        """添加场景记忆（最多保留 5 条）"""
        self.scene_memory.append(entry)
        if len(self.scene_memory) > 5:
            self.scene_memory.pop(0)

    def add_long_term_memory(self, entry: str) -> None:
        """添加长期记忆（最多保留 8 条）"""
        self.long_term_memory.append(entry)
        if len(self.long_term_memory) > 8:
            self.long_term_memory.pop(0)

    def add_knowledge(self, char_id: str, fact: str) -> None:
        """添加角色知识"""
        if char_id not in self.knowledge_graph:
            self.knowledge_graph[char_id] = []
        if fact not in self.knowledge_graph[char_id]:
            self.knowledge_graph[char_id].append(fact)

    # ── Pipeline 状态补丁方法 ──

    def apply_reputation_change(self, char_id: str, delta: float) -> None:
        """更新玩家在特定角色处的声望"""
        self.player_reputation[char_id] = self.player_reputation.get(char_id, 0.0) + delta

    def apply_mood_change(self, char_id: str, new_mood: str, intensity: float = None) -> None:
        """更新角色情绪状态"""
        cs = self.characters_state.setdefault(char_id, {})
        if new_mood:
            cs["mood"] = new_mood
        if intensity is not None:
            cs["mood_intensity"] = float(intensity)

    def apply_location_change(self, char_id: str, to_loc: str) -> None:
        """更新角色位置"""
        if char_id and to_loc:
            cs = self.characters_state.setdefault(char_id, {})
            cs["location"] = to_loc

    def add_dynamic_npc(self, npc_data: dict) -> None:
        """添加动态生成的 NPC"""
        name = str((npc_data or {}).get("name", ""))
        if name:
            npc_id = f"dyn_{name}"
            self.dynamic_npcs[npc_id] = npc_data

    def add_player_trait(self, trait: str) -> None:
        """添加玩家性格特质"""
        self.player_profile.setdefault("traits", []).append(trait)

    def update_player_motivation(self, motivation: str) -> None:
        """更新玩家当前动机"""
        self.player_profile["motivation"] = motivation

    def update_player_tendency(self, tendency: str) -> None:
        """更新玩家行为倾向"""
        self.player_profile["tendency"] = tendency

    def apply_thread_updates(self, updates: dict) -> None:
        """应用 ThreadManager 返回的线索变更"""
        # Thread advances（兼容新旧两种格式：
        #   旧: delta — 仅推进 intensity
        #   新: intensity_delta + complexity_delta — 双维度推进）
        for adv in (updates.get("thread_advances", []) or []):
            adv = adv if isinstance(adv, dict) else {}
            tid = str(adv.get("thread_id", ""))
            # 兼容新旧格式
            idelta = float(adv.get("intensity_delta", adv.get("delta", 0.0)))
            cdelta = float(adv.get("complexity_delta", 0.0))
            if tid:
                for t in self.narrative_threads.get("active", []):
                    t = t if isinstance(t, dict) else {}
                    if t.get("id", "") == tid:
                        if idelta > 0:
                            t["intensity"] = min(1.0, float(t.get("intensity", 0.0)) + idelta)
                        if cdelta > 0:
                            t["complexity"] = min(1.0, float(t.get("complexity", 0.0)) + cdelta)
                        break

        # New threads（使用 intensity + complexity）
        for nt in (updates.get("new_threads", []) or []):
            nt = nt if isinstance(nt, dict) else {}
            title = str(nt.get("title", ""))
            if title:
                new_t = {
                    "id": f"thread_{len(self.narrative_threads.get('active', [])) + 1:03d}",
                    "title": title,
                    "type": str(nt.get("type", "side")),
                    "intensity": 0.0,
                    "complexity": 0.3,
                    "tension": 0.3,
                    "priority": 0.5,
                    "question": nt.get("question", ""),
                    "involved_characters": [],
                    "player_attention": 0.5,
                }
                self.narrative_threads.setdefault("active", []).append(new_t)

        # Evolved threads（原 closed，兼容旧版 closed_threads 输入）
        evolved_ids: set[str] = set()
        for et in (updates.get("evolved_threads", []) or []):
            evolved_ids.add(str(et))
        # 兼容旧版 closed_threads
        for ct in (updates.get("closed_threads", []) or []):
            evolved_ids.add(str(ct))
        if evolved_ids:
            remaining_active = []
            for t in (self.narrative_threads.get("active", []) or []):
                t = t if isinstance(t, dict) else {}
                tid = str(t.get("id", ""))
                if tid in evolved_ids:
                    # 移入 evolved
                    self.narrative_threads.setdefault("evolved", []).append(t)
                else:
                    remaining_active.append(t)
            self.narrative_threads["active"] = remaining_active

        # Tension adjustments
        for ta in (updates.get("tension_adjustments", []) or []):
            ta = ta if isinstance(ta, dict) else {}
            tid = str(ta.get("thread_id", ""))
            tension = float(ta.get("new_tension", 0.5))
            if tid:
                for t in (self.narrative_threads.get("active", []) or []):
                    t = t if isinstance(t, dict) else {}
                    if t.get("id", "") == tid:
                        t["tension"] = tension
                        break

    def get_active_threads(self) -> list[dict]:
        """获取活跃线索列表"""
        return list(self.narrative_threads.get("active", []) or [])

    # ── 涌现建议队列 ──

    def add_pending_emergence(self, name: str, entity_type: str,
                               mention: str, tags: list[str]) -> None:
        """添加或合并涌现实体到建议队列。"""
        # 归一化名称
        norm_name = name.strip()

        if norm_name in self.pending_emergences:
            # 已存在：累加
            pe = self.pending_emergences[norm_name]
            pe["hit_count"] = pe.get("hit_count", 0) + 1
            pe["last_seen_beat"] = self.time_index
            samples = pe.setdefault("mention_samples", [])
            if mention and mention not in samples:
                samples.append(mention)
            existing_tags = set(pe.get("feature_tags", []) or [])
            existing_tags.update(tags)
            pe["feature_tags"] = list(existing_tags)
        else:
            # 新建
            self.pending_emergences[norm_name] = {
                "entity_type": entity_type,
                "normalized_name": norm_name,
                "hit_count": 1,
                "first_seen_beat": self.time_index,
                "last_seen_beat": self.time_index,
                "mention_samples": [mention] if mention else [],
                "feature_tags": list(tags),
                "generated_profile": None,
                "readiness": "ACCUMULATING",
            }

    def get_pending_emergence(self, name: str) -> Optional[dict]:
        """获取涌现实体。"""
        norm_name = name.strip()
        return self.pending_emergences.get(norm_name)

    def get_all_pending_emergences(self) -> dict[str, dict]:
        """获取所有涌现实体（仅内部使用）。"""
        return dict(self.pending_emergences)

    def promote_emergence(self, name: str) -> Optional[dict]:
        """将 READY 的涌现实体正式加入动态实体列表。"""
        norm_name = name.strip()
        pe = self.pending_emergences.get(norm_name)
        if not pe or pe.get("generated_profile") is None:
            return None
        if pe.get("readiness") != "READY":
            return None

        profile = pe["generated_profile"]
        entity_type = pe.get("entity_type", "character")

        if entity_type == "character":
            char_id = f"emr_{norm_name}"
            self.dynamic_npcs[char_id] = profile
        elif entity_type == "location":
            loc_id = f"emr_{norm_name}"
            self.dynamic_locations[loc_id] = profile

        # 从建议队列移除（已采纳）
        del self.pending_emergences[norm_name]
        return profile

    # ── 记忆系统 ──

    @property
    def memory(self) -> "MemoryManager":  # type: ignore
        """懒加载 MemoryManager。"""
        if self._memory_manager is None:
            # 兼容 server/ 和 project_root 两种导入上下文
            try:
                from server.manana.memory import MemoryManager as _MemoryManager
            except ImportError:
                from manana.memory import MemoryManager as _MemoryManager
            self._memory_manager = _MemoryManager()
        return self._memory_manager

    @memory.setter
    def memory(self, mgr: "MemoryManager") -> None:  # type: ignore
        self._memory_manager = mgr
