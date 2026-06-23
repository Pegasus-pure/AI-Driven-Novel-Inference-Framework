# -*- coding: utf-8 -*-
"""灵魂附生 — 数据模型

核心数据结构：
  - PlayerSoulProfile: 玩家灵魂人格
  - SoulPossessionState: 双人格并存状态
  - NPCCognitiveDissonance: NPC 对主角的认知冲突
  - ObservationEntry: 单条观察记录（角色认知笔记条目）
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# 1. 玩家灵魂人格
# ──────────────────────────────────────────────

@dataclass
class PlayerSoulProfile:
    """玩家灵魂人格 —— 从前 N 次选择中自然派生"""

    soul_name: str = "异界旅人"
    """玩家自定义灵魂名"""

    personality: dict = field(default_factory=lambda: {
        "openness": 0.5,
        "conscientiousness": 0.5,
        "extraversion": 0.5,
        "agreeableness": 0.5,
        "neuroticism": 0.5,
    })
    """Big Five 简化版人格 (0~1)"""

    behavioral_tendencies: dict = field(default_factory=lambda: {
        "面对危险": "谨慎",
        "社交风格": "随机应变",
        "决策方式": "权衡利弊",
    })
    """行为倾向"""

    core_motivation: str = "了解这个世界"
    """核心动机"""

    core_fear: str = ""
    """核心恐惧"""

    speech_markers: list[str] = field(default_factory=lambda: ["……", "原来如此"])
    """口头禅/习惯用语"""

    moral_alignment: dict = field(default_factory=lambda: {
        "law_chaos": 0.0,   # -1(守序) ~ +1(混乱)
        "good_evil": 0.0,   # -1(善良) ~ +1(邪恶)
    })
    """伦理倾向"""

    # ── 派生统计 ──
    total_choices: int = 0
    """已统计的选择次数"""
    authentic_count: int = 0
    """本我选择次数"""
    conforming_count: int = 0
    """贴合选择次数"""

    @property
    def is_derived(self) -> bool:
        """人格是否已派生（前 N 拍后为 True）"""
        return self.total_choices >= 10

    @property
    def authentic_ratio(self) -> float:
        """本我比例 0~1"""
        if self.total_choices == 0:
            return 0.5
        return self.authentic_count / self.total_choices

    def record_choice(self, action_type: str) -> None:
        """记录一次选择，推进人格派生"""
        self.total_choices += 1
        if action_type == "authentic":
            self.authentic_count += 1
        elif action_type == "conforming":
            self.conforming_count += 1
        if self.total_choices >= 10:
            self._derive_personality()

    def _derive_personality(self) -> None:
        """从选择历史推导五大维度。authentic 比例高 → 开放/外向偏高。"""
        ratio = self.authentic_ratio
        self.personality["openness"] = round(0.3 + ratio * 0.4, 2)
        self.personality["extraversion"] = round(0.3 + ratio * 0.4, 2)
        self.personality["conscientiousness"] = round(0.4 + (1 - ratio) * 0.3, 2)
        self.personality["agreeableness"] = round(0.4 + (1 - ratio) * 0.3, 2)
        self.personality["neuroticism"] = round(0.5 - ratio * 0.2, 2)
        self.behavioral_tendencies["决策方式"] = (
            "跟随直觉" if ratio > 0.6 else "权衡利弊" if ratio > 0.4 else "谨慎行事"
        )

    def to_dict(self) -> dict:
        return {
            "soul_name": self.soul_name,
            "personality": dict(self.personality),
            "behavioral_tendencies": dict(self.behavioral_tendencies),
            "core_motivation": self.core_motivation,
            "core_fear": self.core_fear,
            "speech_markers": list(self.speech_markers),
            "moral_alignment": dict(self.moral_alignment),
            "total_choices": self.total_choices,
            "authentic_count": self.authentic_count,
            "conforming_count": self.conforming_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerSoulProfile":
        return cls(
            soul_name=data.get("soul_name", "异界旅人"),
            personality=data.get("personality", {}),
            behavioral_tendencies=data.get("behavioral_tendencies", {}),
            core_motivation=data.get("core_motivation", "了解这个世界"),
            core_fear=data.get("core_fear", ""),
            speech_markers=data.get("speech_markers", []),
            moral_alignment=data.get("moral_alignment", {}),
            total_choices=data.get("total_choices", 0),
            authentic_count=data.get("authentic_count", 0),
            conforming_count=data.get("conforming_count", 0),
        )

    @classmethod
    def default(cls) -> "PlayerSoulProfile":
        """返回均衡默认人格（前 10 拍使用）"""
        return cls()


# ──────────────────────────────────────────────
# 2. 灵魂附生状态
# ──────────────────────────────────────────────

@dataclass
class SoulPossessionState:
    """灵魂附生状态 —— 双人格并存

    canon_soul: 主角原始人格（只读，从 Canon 加载）
    player_soul: 玩家灵魂人格（可变，从前 N 次选择派生）
    """

    canon_soul: dict = field(default_factory=dict)
    """主角的 Canon 原始人格（只读）"""

    player_soul: PlayerSoulProfile = field(default_factory=PlayerSoulProfile)
    """玩家灵魂人格"""

    dominant_soul: str = "player"
    """当前主导灵魂: player | canon | blended"""

    blend_ratio: float = 0.8
    """玩家支配权重 (0~1)"""

    memory_access: str = "partial"
    """主角记忆访问权限: none | partial | full"""

    soul_awareness: dict = field(default_factory=lambda: {
        "player_thinking": "",
        "canon_echo": "",
        "internal_conflict": "",
    })
    """双灵魂的当前内心对话"""

    def is_player_dominant(self) -> bool:
        return self.blend_ratio > 0.5

    def to_dict(self) -> dict:
        return {
            "canon_soul": dict(self.canon_soul),
            "player_soul": self.player_soul.to_dict(),
            "dominant_soul": self.dominant_soul,
            "blend_ratio": self.blend_ratio,
            "memory_access": self.memory_access,
            "soul_awareness": dict(self.soul_awareness),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SoulPossessionState":
        return cls(
            canon_soul=data.get("canon_soul", {}),
            player_soul=PlayerSoulProfile.from_dict(
                data.get("player_soul", {})
            ),
            dominant_soul=data.get("dominant_soul", "player"),
            blend_ratio=data.get("blend_ratio", 0.8),
            memory_access=data.get("memory_access", "partial"),
            soul_awareness=data.get("soul_awareness", {}),
        )


# ──────────────────────────────────────────────
# 3. NPC 认知冲突状态
# ──────────────────────────────────────────────

@dataclass
class ObservationEntry:
    """单条观察记录 —— 角色认知笔记条目"""

    beat_id: str = ""
    """观察发生时的节拍 ID"""
    action_type: str = ""
    """观察到的行动类型: authentic | conforming"""
    observed_behavior: str = ""
    """观察到的具体行为摘要"""
    npc_reaction: str = ""
    """NPC 当时的反应"""
    is_important: bool = False
    """是否为关键事件"""

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "action_type": self.action_type,
            "observed_behavior": self.observed_behavior,
            "npc_reaction": self.npc_reaction,
            "is_important": self.is_important,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ObservationEntry":
        return cls(
            beat_id=data.get("beat_id", ""),
            action_type=data.get("action_type", ""),
            observed_behavior=data.get("observed_behavior", ""),
            npc_reaction=data.get("npc_reaction", ""),
            is_important=data.get("is_important", False),
        )


@dataclass
class NPCCognitiveDissonance:
    """NPC 对主角的认知冲突状态"""

    char_id: str = ""
    """NPC 的角色 ID"""

    # ── 初始化自 Canon（不可变基准） ──
    memory_of_protagonist: dict = field(default_factory=dict)
    """NPC 对主角的历史记忆
    {
        "expected_behavior": str,
        "trust_level": float,
        "relationship_note": str,
        "key_memories": [str],
        "impression": str,
    }
    """

    # ── 双维度评价 ──
    affinity: float = 0.0
    """情感亲近度 (-100 ~ +100)"""
    credibility: float = 100.0
    """身份可信度 (0 ~ 100)"""

    # ── 冲突状态 ──
    dissonance_score: float = 0.0
    """认知冲突度 (0~1)"""
    phase: str = "normal"
    """当前阶段: normal | subtle | questioning | confrontational | adapted"""

    # ── 认知演化 ──
    theory_of_change: str = ""
    """NPC 对自己观察到的变化的解释理论"""
    adaptation_progress: float = 0.0
    """适应进度 (0~1)"""

    # ── 角色认知笔记 ──
    scratchpad: list = field(default_factory=list)
    """观察日志列表 [ObservationEntry, ...]"""

    # ── 配置（可全局覆盖） ──
    dissonance_decay_rate: float = 0.05
    dissonance_threshold: float = 0.7

    # ────────────────────────────────────────
    # 方法
    # ────────────────────────────────────────

    def update_phase(self) -> None:
        """根据当前状态更新 phase"""
        if self.adaptation_progress >= 0.9:
            self.phase = "adapted"
        elif self.dissonance_score >= self.dissonance_threshold:
            self.phase = "confrontational"
        elif self.dissonance_score >= 0.5:
            self.phase = "questioning"
        elif self.dissonance_score >= 0.25:
            self.phase = "subtle"
        else:
            self.phase = "normal"

    def to_dict(self) -> dict:
        return {
            "char_id": self.char_id,
            "memory_of_protagonist": dict(self.memory_of_protagonist),
            "affinity": self.affinity,
            "credibility": self.credibility,
            "dissonance_score": self.dissonance_score,
            "phase": self.phase,
            "theory_of_change": self.theory_of_change,
            "adaptation_progress": self.adaptation_progress,
            "scratchpad": [e.to_dict() for e in self.scratchpad],
            "dissonance_decay_rate": self.dissonance_decay_rate,
            "dissonance_threshold": self.dissonance_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCCognitiveDissonance":
        state = cls(
            char_id=data.get("char_id", ""),
            memory_of_protagonist=data.get("memory_of_protagonist", {}),
            affinity=data.get("affinity", 0.0),
            credibility=data.get("credibility", 100.0),
            dissonance_score=data.get("dissonance_score", 0.0),
            phase=data.get("phase", "normal"),
            theory_of_change=data.get("theory_of_change", ""),
            adaptation_progress=data.get("adaptation_progress", 0.0),
            scratchpad=[
                ObservationEntry.from_dict(e)
                for e in (data.get("scratchpad") or [])
            ],
            dissonance_decay_rate=data.get("dissonance_decay_rate", 0.05),
            dissonance_threshold=data.get("dissonance_threshold", 0.7),
        )
        return state
