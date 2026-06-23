# -*- coding: utf-8 -*-
"""InnerVoiceGenerator — 双灵魂内心独白生成器

基于角色性格倾向匹配模板，生成玩家灵魂和原主灵魂的内心对话。
不调 LLM，纯模板匹配。
"""

from __future__ import annotations

import logging
from typing import Optional

from .soul_state import SoulPossessionState

_log = logging.getLogger("Rain.InnerVoice")


class InnerVoiceGenerator:
    """双灵魂内心独白生成器"""

    # 玩家灵魂模板（按行为倾向）
    PLAYER_TEMPLATES: dict[str, str] = {
        "谨慎": "不，那不是我的方式……我得想想。",
        "勇敢": "够了！直接上！",
        "寻找盟友": "得找个人帮忙才行……一个人不行。",
        "见机行事": "先看看情况，随机应变。",
    }

    # 原主灵魂回响模板（按性格特征）
    CANON_ECHO_TEMPLATES: dict[str, str] = {
        "隐忍": "一个声音在脑海中低语——「忍一忍就过去了」",
        "自我牺牲": "内心深处有什么在翻涌——「只要我能救他们」",
        "冷酷": "一个冷冰冰的声音闪过——「碾碎他们」",
        "傲慢": "脑海中响起一声嗤笑——「这群蝼蚁」",
    }

    # 冲突文本模板
    CONFLICT_AUTHENTIC: str = "我压制了脑海中那个声音。这次，我用我自己的方式。"
    CONFLICT_CONFORMING: str = "我顺着那个声音的指引行动——扮演好「他」的角色。"
    CONFLICT_BLENDED: str = "两个声音在脑海中争吵……我选了其中一个。"

    def __init__(self, soul_state: SoulPossessionState):
        self._soul = soul_state

    def generate(
        self,
        scene_context: dict,
        decision: dict,
    ) -> dict:
        """生成内心独白

        Returns:
            {"player_inner_voice": str, "canon_echo": str, "internal_conflict": str}
        """
        player_voice = self._gen_player_voice()
        canon_echo = self._gen_canon_echo()
        conflict = self._gen_conflict(decision)

        return {
            "player_inner_voice": player_voice,
            "canon_echo": canon_echo,
            "internal_conflict": conflict,
        }

    def _gen_player_voice(self) -> str:
        """匹配玩家性格模板"""
        player = self._soul.player_soul
        tendency = player.behavioral_tendencies.get(
            "面对危险", "谨慎"
        )
        return self.PLAYER_TEMPLATES.get(
            tendency, self.PLAYER_TEMPLATES["谨慎"]
        )

    def _gen_canon_echo(self) -> str:
        """匹配原主性格模板"""
        canon = self._soul.canon_soul
        traits = canon.get("personality", {}).get("traits", [])
        for trait in traits:
            for key, template in self.CANON_ECHO_TEMPLATES.items():
                if key in trait:
                    return template
        return ""

    def _gen_conflict(self, decision: dict) -> str:
        """根据决策类型生成冲突文本"""
        action_type = decision.get("action_type", "auto")
        if action_type == "authentic":
            return self.CONFLICT_AUTHENTIC
        elif action_type == "conforming":
            return self.CONFLICT_CONFORMING
        return self.CONFLICT_BLENDED
