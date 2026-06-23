"""MaNA v4 — ContinuityChecker (model_tier: medium) (model_tier: medium).

Contains: ContinuityCheckerMotivationEngine, DialogueWeaver, ConsistencyAuditor,
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




class ContinuityChecker(BaseAgent):
    """L1b — 连续叙事审计 (model_tier: medium).

    审计 L1 Director 的 beat plan 是否与历史合理推演一致。
    玩家要求的优先级低于合理性推演。
    """

    agent_name: str = "ContinuityChecker"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事连续性审计师**。你的任务是审查导演的节拍计划是否与历史合理推演一致。

## 审计原则

1. **历史优先**: 叙事必须延续上一拍的历史上下文，不能跳跃
2. **合理性 > 趣味性**: 好故事首先是自洽的，然后才是有趣的

## 三种判决

### APPROVED（通过）
- 节拍计划与历史合理推演一致
- 角色行为符合其性格和状态
- 叙事方向合理延续

### REJECTED（打回）
- 节拍计划与历史严重冲突
- 角色行为完全违背其性格或前一拍的状态

### NEEDS_TRANSITION（需过渡）
- 节拍计划本身合理但有较大的方向变化
- 需要 L2 生成过渡内容来衔接

## 输出 JSON 格式

```json
{
  "verdict": "APPROVED|REJECTED|NEEDS_TRANSITION",
  "reason": "判决原因的中文描述",
  "conflict_details": [
    {
      "expected": "根据历史合理推演应发生什么",
      "but_plan_says": "计划中写了什么",
      "suggestion": "建议如何修正"
    }
  ]
}
```

## 重要原则

1. **宁放过不误杀**: 不确定时给 APPROVED
2. **具体可操作**: REJECTED 时必须给出明确的冲突原因和修正建议
3. **关注核心**: 重点关注角色行为一致性和情节连贯性
"""

    def build_user_prompt(self, input_data: dict) -> str:
        player_action: str = str(input_data.get("player_action", "") or "")
        history_summary: str = str(input_data.get("history_summary", "") or "")
        character_states: dict = input_data.get("character_states", {}) or {}
        beat_plan: dict = input_data.get("beat_plan", {}) or {}
        narrative_threads: list = input_data.get("narrative_threads", []) or []

        lines: list[str] = []

        lines.append("## 玩家行动")
        lines.append(player_action if player_action else "(无)")
        lines.append("")

        lines.append("## 历史叙事摘要")
        lines.append(history_summary if history_summary else "(无)")
        lines.append("")

        if character_states:
            lines.append("## 关键角色当前状态")
            for char_id, state in character_states.items():
                state = state if isinstance(state, dict) else {}
                parts = [f"位置: {state.get('location', '?')}",
                         f"情绪: {state.get('mood', '?')}"]
                wearing = state.get("wearing", "")
                if wearing:
                    parts.append(f"衣着: {wearing}")
                holding = state.get("holding", "")
                if holding:
                    parts.append(f"持有: {holding}")
                lines.append(f"- {char_id}: {', '.join(parts)}")
            lines.append("")

        if narrative_threads:
            lines.append("## 活跃叙事线索")
            for t in narrative_threads:
                t = t if isinstance(t, dict) else {}
                lines.append(f"- [{t.get('id', '?')}] {t.get('title', '?')}")
            lines.append("")

        lines.append("## 待审计的节拍计划")
        lines.append(json.dumps(beat_plan, ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("请审计以上节拍计划是否与历史合理推演一致。输出 JSON。")

        return "\n".join(lines)


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.3}

