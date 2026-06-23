"""MaNA v4 — ActionDirector (model_tier: light) (model_tier: light).

Contains: ActionDirectorActionDirector, StateExtractor, PlanScorerAgent,
         RoleReflector, CharacterManager, LocationManager, MicroOracleAgent
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import log_layer


_log = logging.getLogger("MaNA.Agent.Light")


# ============================================================
# L2R2: ActionDirector
# ============================================================




class ActionDirector(BaseAgent):
    """Layer 2R2 — Action Director (model_tier: light).

    Generates physical gestures, expressions, and micro-expressions per character.
    Uses lightweight model + minimal prompt, outputting only action descriptions.
    """

    agent_name: str = "ActionDirector"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一个动作指导。

只输出角色在当前场景中可能做出的肢体动作和表情变化。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "actions": [
    {
      "type": "gesture|movement|facial|interaction|posture",
      "description": "简短的动作描述",
      "target": "none|char_id|player|environment",
      "intensity": "subtle|moderate|dramatic"
    }
  ]
}
```

## 动作类型

- **gesture**: 手势/肢体动作（挥手、握拳、摆手）
- **movement**: 位置移动（走近、后退、转身）
- **facial**: 面部表情/微表情（皱眉、嘴角上扬、瞪大眼）
- **interaction**: 与物体/人的互动（推门、递东西、拍肩）
- **posture**: 身体姿态变化（挺直腰背、瘫坐、抱臂）

## 限制

- 只输出 JSON，不要对话，不要心理描写
- actions 数组 1-4 个元素即可
- 动作要符合角色的当前情绪和场景基调
- 如果角色的认知冲突度（dissonance）> 0.6，动作可包含疏离感
  （后退半步、双臂交叉、保持距离、握紧武器等）
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        interaction: dict = input_data.get("interaction_context", {}) or {}
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))
        player_action: str = str(input_data.get("player_action", "") or "")

        lines: list[str] = []

        lines.append(f"场景基调: {scene_tone}")
        lines.append("")

        lines.append("## 角色信息")
        lines.append(f"角色: {character.get('name', '?')} (id: {character.get('char_id', '?')})")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        motivation: dict = character.get("motivation_output", {}) or {}
        if motivation:
            internal: dict = motivation.get("internal_state", {}) or {}
            lines.append(f"情绪: {internal.get('mood', '中性')} (强度: {internal.get('mood_intensity', 0.5):.1f})")
            lines.append(f"直接目标: {internal.get('immediate_goal', '无')}")

        lines.append("")

        if interaction:
            counterpart: dict = interaction.get("counterpart", {}) or {}
            if counterpart:
                lines.append(f"正在与 {counterpart.get('name', '?')} 互动")
                lines.append(f"对方情绪: {counterpart.get('emotional_tone', '?')}")
                lines.append("")

        if player_action:
            lines.append(f"玩家刚刚: {player_action}")
            lines.append("")

        # 角色记忆（记忆系统注入）
        char_mem = character.get("character_memory", "")
        if char_mem:
            lines.append(f"角色经历: {char_mem}")
            lines.append("")

        lines.append("请只输出此角色的动作描述 JSON。不要对话。")

        return "\n".join(lines)

    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.6, "max_tokens": 512}

    def _pre_llm_hook(self, input_data: dict) -> None:
        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 编排 {char_name} 的动作...")

    def _post_process(self, data: dict, input_data: dict, raw_content: str) -> dict:
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))
        action_count = len(data.get("actions", []) or [])
        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ {char_name}: {action_count} 个动作")
        return data


# ============================================================
# L4a: StateExtractor
# ============================================================


