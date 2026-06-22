"""MaNA v4 — DialogueWeaver (model_tier: medium) (model_tier: medium).

Contains: DialogueWeaverMotivationEngine, DialogueWeaver, ConsistencyAuditor,
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




class DialogueWeaver(BaseAgent):
    """Layer 2R2 — Dialogue Weaver (model_tier: medium).

    Generates dialogue content, tone, wording, and emotional arcs per character.
    Characters in interaction pairs receive counterpart motivation summaries
    (only emotional tone and visible goals, no hidden_intent).
    """

    agent_name: str = "DialogueWeaver"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一个互动叙事系统的**对话编织者 (Dialogue Weaver)**。

你的任务是：为一个角色生成在当前场景中的对话和情绪弧线。

## 关键原则

1. **角色一致性**: 对话必须符合角色的性格、身份和语言风格
2. **情绪流动**: 对话是动态的——情绪可能在对话过程中发生变化（emotional_arc）
3. **潜台词**: 角色说的和心里想的可能不一样。利用动机分析中的 subtext
4. **互动性**: 如果角色在对话中（有 counterpart），注意反应和互动
5. **玩家驱动**: 玩家的行动是触发因素。角色应对玩家的行为有语言上的回应

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "dialogue": [
    {
      "text": "角色说出的对白文本",
      "tone": "愤怒|平静|讽刺|热情|冷淡|紧张|温柔|戏谑|严肃|悲伤|好奇|威胁",
      "target": "char_id 或 player",
      "subtext": "这句话背后的真正含义"
    }
  ],
  "actions": [
    {
      "type": "gesture|movement|facial|interaction",
      "description": "动作描述",
      "target": "动作对象"
    }
  ],
  "emotional_arc": "情绪弧线描述——从对话开始时到结束时的情绪变化",
  "stance_change": {
    "new_attitude": "友善|中立|冷淡|敌视|戒备",
    "reason": "态度变化的原因"
  }
}
```

## 字段说明

- **dialogue**: 对话数组。每个元素是一条对白。可以有多条（角色可能说多句话、换语气）
- **dialogue[].text**: 角色说出的具体话语。用中文
- **dialogue[].tone**: 说这句话时的语气
- **dialogue[].target**: 说话对象。可以是其他角色 char_id 或 "player"
- **dialogue[].subtext**: 这句话的潜台词——角色真正的意思
- **actions**: 伴随对话的肢体动作。由 DialogueWeaver 生成基础版，ActionDirector 会细化
- **emotional_arc**: 情绪弧线，描述对话全程的情绪变化（如 "由警惕逐渐转为好奇"）
- **stance_change**: 可选。如果角色对玩家的态度在对话中发生变化则填写，无变化则为 null

## 注意事项

- 对话应当自然、有呼吸感——不要写成长篇大论
- 角色的性格要体现在措辞和语气中
- 如果有 interaction_context（对手机制），回应对方的话语和情绪
- 如果没有 interaction_context（独立角色），可以是自言自语、观察反应或环境互动
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        interaction: dict = input_data.get("interaction_context", {}) or {}
        beat_summary: str = str(input_data.get("beat_summary", "") or "")
        player_action: str = str(input_data.get("player_action", "") or "")
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))

        lines: list[str] = []

        lines.append("## 场景信息")
        lines.append(f"场景基调: {scene_tone}")
        if beat_summary:
            lines.append(f"节拍摘要: {beat_summary}")
        if player_action:
            lines.append(f"玩家行动: {player_action}")
        lines.append("")

        lines.append("## 当前角色")
        lines.append(f"角色 ID: {character.get('char_id', '')}")
        lines.append(f"名字: {character.get('name', '?')}")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        role = str(character.get("role", "") or "")
        if role:
            lines.append(f"原著定位: {role}")

        # Motivation output
        motivation: dict = character.get("motivation_output", {}) or {}
        if motivation:
            lines.append("")
            lines.append("### 动机分析")
            internal: dict = motivation.get("internal_state", {}) or {}
            lines.append(f"情绪: {internal.get('mood', '?')} (强度: {internal.get('mood_intensity', 0.5):.1f})")
            lines.append(f"主导情绪: {internal.get('dominant_emotion', '?')}")
            lines.append(f"潜台词: {internal.get('subtext', '(无)')}")
            lines.append(f"隐藏意图: {internal.get('hidden_intent', '(无)')}")
            lines.append(f"直接目标: {internal.get('immediate_goal', '(无)')}")

            stance: dict = motivation.get("stance_toward_player", {}) or {}
            if stance:
                lines.append(f"对玩家态度: {stance.get('attitude', '?')} (信任: {stance.get('trust_level', 0.5):.1f})")
                lines.append(f"想对玩家: {stance.get('wants_to', '?')}")

        lines.append("")

        # Interaction context
        if interaction:
            counterpart: dict = interaction.get("counterpart", {}) or {}
            if counterpart:
                lines.append("## 对话对象")
                lines.append(f"正在与 **{counterpart.get('name', '?')}** 对话")
                lines.append(f"对方情绪: {counterpart.get('emotional_tone', '?')}")
                lines.append(f"对方可见目标: {counterpart.get('visible_goal', '?')}")
                lines.append("")
                lines.append(f"请生成 {character.get('name', '?')} 对 {counterpart.get('name', '?')} 的回应对话。要体现角色的性格和真实意图。")
        else:
            lines.append("## 交互模式: 独立")
            lines.append("此角色当前不参与对话交互。可以是对环境的反应、自言自语、或对玩家行动的观察。")
            lines.append("")

        lines.append("输出 JSON。")

        anti_rules: list = character.get("anti_rules", []) or []
        if anti_rules:
            lines.append("")
            lines.append("## 行为禁区（绝对不能违反）")
            for rule in anti_rules:
                lines.append(f"- {rule}")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 编织 {char_name} 的对话...")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.85})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))

        validation = MananaSchema.validate_dialogue_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证失败: {validation.get('errors', [])}")

        dialogue_count = len(data.get("dialogue", []) or [])
        self._log_info(f"→ {char_name}: {dialogue_count} 条对话")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L3b: ConsistencyAuditor
# ============================================================


