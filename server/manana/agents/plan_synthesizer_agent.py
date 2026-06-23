"""MaNA v4 — PlanSynthesizerAgent (model_tier: medium) (model_tier: medium).

Contains: PlanSynthesizerAgentMotivationEngine, DialogueWeaver, ConsistencyAuditor,
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




class PlanSynthesizerAgent(BaseAgent):
    """v4 P1-3 — Multi-View Synthesizer.

    Fuses plot-driven and character-driven beat plans into a single plan.
    model_tier: medium, temperature: 0.4, max_tokens: 1024, json_mode: true.
    """

    agent_name: str = "PlanSynthesizer"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """融合两个节拍方案为单一方案，输出标准 beat_plan JSON。

你是一个叙事计划合成器。你会收到两个视角的节拍方案：
1. 剧情驱动视角 (plot-driven) — 从剧情线索推进角度出发
2. 角色驱动视角 (character-driven) — 从角色发展和互动角度出发

你需要融合两个方案的优点，输出一个单一的、连贯的节拍计划 JSON。
输出格式与标准 SceneDirector 输出完全一致。"""

    def build_user_prompt(self, input_data: dict) -> str:
        plot_plan: dict = input_data.get("plot_plan", {}) or {}
        char_plan: dict = input_data.get("character_plan", {}) or {}
        scene_context: dict = input_data.get("scene_context", {}) or {}

        return (
            "场景上下文:\n" + json.dumps(scene_context, ensure_ascii=False, indent=2) +
            "\n\n剧情视角方案:\n" + json.dumps(plot_plan, ensure_ascii=False, indent=2) +
            "\n\n角色视角方案:\n" + json.dumps(char_plan, ensure_ascii=False, indent=2)
        )


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"temperature": 0.4, "max_tokens": 1024, "json_mode": True}

