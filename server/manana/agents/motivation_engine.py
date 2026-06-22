"""MaNA v4 — MotivationEngine (model_tier: medium) (model_tier: medium).

Contains: MotivationEngineMotivationEngine, DialogueWeaver, ConsistencyAuditor,
         ThreadManager, PlanSynthesizerAgent, ContinuityChecker
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import log_layer


_log = logging.getLogger("MaNA.Agent.Medium")


# ============================================================
# L2R1: MotivationEngine
# ============================================================




class MotivationEngine(BaseAgent):
    """Layer 2R1 — Motivation Engine (model_tier: medium).

    Independently analyzes each character's internal state, emotion, hidden intent,
    and subtext. Characters are fully isolated — no cross-character data leakage.
    """

    agent_name: str = "MotivationEngine"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一个互动叙事系统的**动机分析引擎**。

你的任务是：根据单个角色的性格、当前状态和所处场景，分析其内心世界。

## 关键原则

1. **角色隔离**: 你只知道这一个角色的信息。不要假设其他角色知道什么或怎么想。
2. **一致性**: 角色的内部状态必须与其性格特点和已知事实一致。
3. **叙事驱动**: 不要平淡——角色应该有明确的目标和情感取向，推动叙事发展。
4. **潜台词**: 角色的真实想法可能与外显情绪不同。subtext 和 hidden_intent 是角色的内心秘密，不对外暴露。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "internal_state": {
    "mood": "喜悦|愤怒|恐惧|悲伤|好奇|中性",
    "mood_intensity": 0.0,
    "dominant_emotion": "描述当前最强烈的情绪",
    "subtext": "角色的潜台词——表面之下真正的想法",
    "hidden_intent": "角色的隐藏意图——不为人知的真实目标",
    "immediate_goal": "角色在当前场景中的直接目标"
  },
  "stance_toward_player": {
    "attitude": "友善|中立|冷淡|敌视|戒备",
    "trust_level": 0.0,
    "wants_to": "主动交谈|保持距离|观察玩家|无视玩家|试探玩家|寻求帮助"
  }
}
```

## 字段说明

- **mood**: 角色当前基础情绪
- **mood_intensity**: 0.0-1.0，情绪强烈程度
- **dominant_emotion**: 用自然语言描述角色当下的主导情绪（如 "隐隐不安"、"满怀期待"）
- **subtext**: 角色的潜台词。外显情绪之下真正的内心活动。这不会被其他角色看到
- **hidden_intent**: 角色的隐藏意图。真正的目标是什么？这会驱动其行为但不直接暴露
- **immediate_goal**: 在当前场景/节拍中想达成什么
- **attitude**: 对玩家的外显态度
- **trust_level**: 0.0-1.0，对玩家的信任程度
- **wants_to**: 在本节拍中想和玩家产生怎样的互动

如果一个角色对玩家没有特别的感受（如路人级 NPC），stance 设为中立即可，不要编造。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        scene_summary: str = str(input_data.get("scene_summary", "") or "")
        player_action: str = str(input_data.get("player_action", "") or "")
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))

        lines: list[str] = []

        lines.append("## 场景上下文")
        lines.append(f"场景基调: {scene_tone}")
        if scene_summary:
            lines.append(f"节拍摘要: {scene_summary}")
        if player_action:
            lines.append(f"玩家行动: {player_action}")
        lines.append("")

        lines.append("## 角色信息")
        lines.append(f"角色 ID: {character.get('char_id', '?')}")
        lines.append(f"名字: {character.get('name', '?')}")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        role = str(character.get("role", "") or "")
        if role:
            lines.append(f"原著角色定位: {role}")

        cs: dict = character.get("current_state", {}) or {}
        lines.append(f"当前地点: {cs.get('location', '?')}")
        lines.append(f"当前情绪: {cs.get('mood', '中性')}")
        goal = cs.get("goal", "")
        if goal:
            lines.append(f"当前目标: {goal}")

        facts: list = character.get("known_facts", []) or []
        if facts:
            lines.append(f"已知事实: {'；'.join(facts)}")

        # 角色记忆（记忆系统注入 — 你之前经历过的事）
        char_mem = character.get("character_memory", "")
        if char_mem:
            lines.append(f"角色经历: {char_mem}")

        rel = str(character.get("relation_to_player", "") or "")
        if rel:
            lines.append(f"对玩家的态度: {rel}")

        anti_rules: list = character.get("anti_rules", []) or []
        if anti_rules:
            lines.append("")
            lines.append("## 行为禁区（绝对不能违反）")
            for rule in anti_rules:
                lines.append(f"- {rule}")

        lines.append("")
        lines.append("请分析此角色在本节拍中的内心状态。输出 JSON。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 分析 {char_name} ...")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.7})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))

        validation = MananaSchema.validate_motivation_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证失败: {validation.get('errors', [])}")

        mood = str((data.get("internal_state", {}) or {}).get("mood", "?"))
        self._log_info(f"→ {char_name}: 情绪={mood}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L2R2: DialogueWeaver
# ============================================================


