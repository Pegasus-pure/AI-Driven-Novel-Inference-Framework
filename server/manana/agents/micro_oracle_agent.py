"""MaNA v4 — MicroOracleAgent (model_tier: light) (model_tier: light).

Contains: MicroOracleAgentActionDirector, StateExtractor, PlanScorerAgent,
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




class MicroOracleAgent(BaseAgent):
    """v4 P1-1 — Micro-Oracle quality feedback at end of each beat.

    model_tier: light, temperature: 0, max_tokens: 240, json_mode: true.
    """

    agent_name: str = "MicroOracle"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """评估上一拍的叙事质量，输出方向建议 JSON:

{
  "system_health": "healthy|warning|critical",
  "suggestions": [
    {"aspect": "pacing|character|thread|tension|adherence",
     "direction": "加速|减速|聚焦|放松",
     "reason": "详细说明"}
  ],
  "one_line_feedback": "一句话反馈摘要"
}

- system_health: 叙事健康度
  - healthy: 一切正常
  - warning: 略微失衡，建议关注
  - critical: 需要立即调整方向
- suggestions: 具体方向建议（0~3条）
  - aspect: 关注的方面
  - direction: 建议方向
  - reason: 详细理由
- one_line_feedback: 简明反馈摘要，给下一拍的导演参考
"""

    def build_user_prompt(self, input_data: dict) -> str:
        return "上一拍摘要:\n" + str(input_data.get("narrative_summary", ""))


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"temperature": 0.0, "max_tokens": 240, "json_mode": True}

