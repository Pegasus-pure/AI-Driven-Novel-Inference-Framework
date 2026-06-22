"""MaNA v4 — PlanScorerAgent (model_tier: light) (model_tier: light).

Contains: PlanScorerAgentActionDirector, StateExtractor, PlanScorerAgent,
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




class PlanScorerAgent(BaseAgent):
    """v4 P0-2 — Plan Scorer for Best-of-3 Director selection.

    model_tier: light, temperature: 0, max_tokens: 80, json_mode: true.
    """

    agent_name: str = "PlanScorer"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """评估以下节拍计划，输出方向建议 JSON:

{
  "system_health": "healthy|warning|critical",
  "suggestions": [
    {"aspect": "pacing|character|thread|tension",
     "direction": "加快节奏|聚焦某角色|推进某线索|放松",
     "reason": "详细说明"}
  ],
  "scores": {
    "thread_progress": int (1-5),
    "character_naturalness": int (1-5),
    "causal_link": int (1-5),
    "total": int (3-15)
  }
}

- system_health: 整体叙事健康度
  - healthy: 一切正常
  - warning: 可能出现问题，建议关注
  - critical: 需要立即调整
- suggestions: 方向建议列表（0~3条），包含具体方面、建议方向和理由
- scores: 内部参考评分，保留原有 three-dimension 评分体系
"""

    def build_user_prompt(self, input_data: dict) -> str:
        # PlanScorer receives the beat plan directly as input_data
        return "评估以下节拍计划：\n" + json.dumps(input_data, ensure_ascii=False, indent=2)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        result = await self._call_llm(sys, usr, {"temperature": 0.0, "max_tokens": 120, "json_mode": True})

        parsed = self._parse_json_response(result)
        if not parsed.get("ok", False):
            return {"ok": False, "error": str(parsed.get("error", "scorer parse failed")), "raw": input_data}

        data: dict = parsed.get("data", {}) or {}
        scores: dict = data.get("scores", {}) or {}
        return {
            "ok": True,
            "total": int(float(scores.get("total") or data.get("total") or 0)),
            "scores": {
                "thread_progress": int(scores.get("thread_progress", 0)),
                "character_naturalness": int(scores.get("character_naturalness", 0)),
                "causal_link": int(scores.get("causal_link", 0)),
            },
            "system_health": str(data.get("system_health", "healthy")),
            "suggestions": list(data.get("suggestions", []) or []),
            "raw": input_data,
        }


# ============================================================
# L2R3: RoleReflector
# ============================================================


