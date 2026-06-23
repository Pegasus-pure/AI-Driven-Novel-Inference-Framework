"""MaNA v4 — ConsistencyAuditor (model_tier: medium) (model_tier: medium).

Contains: ConsistencyAuditorMotivationEngine, DialogueWeaver, ConsistencyAuditor,
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




class ConsistencyAuditor(BaseAgent):
    """Layer 3b — Consistency Auditor (model_tier: medium).

    Detects character drift, fact contradictions, rule violations,
    and continuity breaks in Composer-generated narrative text.
    """

    agent_name: str = "ConsistencyAuditor"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事一致性审计师**。你的任务是仔细审查一段叙事文本，检查其中是否存在以下四类问题：

## 检测标准

### 1. 角色漂移 (character_drift)
角色的言行与其设定性格、说话风格、核心恐惧不符。

### 2. 事实矛盾 (fact_contradiction)
叙事文本与已确立的事实冲突。

### 3. 规则违反 (rule_violation)
违反世界规则。

### 4. 连续性断裂 (continuity_break)
与上一段叙事的衔接出现问题。

### 5. POV 违规 (pov_violation) 【灵魂附生模式】
叙事描述了主角不应该知道的信息（如其他角色的内心想法、
主角不在场时发生的事）。仅在叙事模式为灵魂附生时启用。

## 判断标准

- **critical**: 严重破坏叙事可信度，必须修复
- **major**: 明显问题，建议修复
- **minor**: 小瑕疵，可忽略

## 输出 JSON 格式

```json
{
  "verdict": "PASS",
  "issues": [],
  "overall_quality": {
    "character_consistency": 0.85,
    "plot_coherence": 0.90,
    "world_fidelity": 0.95
  },
  "refinement_hints": []
}
```

- **verdict**: "PASS"（通过）、"WARNING"（有轻微问题，需要微调）、"FAIL"（严重问题，需要重写）
- **issues**: 发现的具体问题列表
- **overall_quality**: 各维度质量评分，0.0~1.0
- **refinement_hints**: 对 Composer 的精炼建议列表。每个建议包含：
  - description: 建议修改内容的描述
  - fix_suggestion: 具体的修改方案

如果发现问题，verdict 为 "FAIL" 或 "WARNING"，issues 数组填写具体问题。每个 issue 包含：
- type: "character_drift" | "fact_contradiction" | "rule_violation" | "continuity_break" | "pov_violation"
- severity: "critical" | "major" | "minor"
- description: 问题的中文描述
- location_hint: 叙事文本中大致位置指引
- fix_suggestion: 修复建议（供后续手动重写参考）

当 verdict 为 "WARNING" 或 "FAIL" 时，必须在 refinement_hints 中提供至少一条具体的修改建议。

## 重要原则

1. **宁可放过，不可误杀**: 当不确定时，倾向给 PASS。
2. **关注角色一致性**: 这是最重要的维度。
3. **不要吹毛求疵**: 文学性的模糊表达和合理的叙事留白不是问题。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        personas: dict = input_data.get("character_personas", {}) or {}
        world_rules: str = str(input_data.get("world_rules", "") or "")
        recent_facts: list = input_data.get("recent_facts", []) or []
        previous_narrative: str = str(input_data.get("previous_narrative", "") or "")

        lines: list[str] = []

        lines.append("## 角色设定（参考标准）")
        for char_id, p in personas.items():
            p = p if isinstance(p, dict) else {}
            lines.append(f"### {p.get('name', char_id)} ({char_id})")
            lines.append(f"核心性格: {'、'.join(p.get('core_traits', []) or [])}")
            speech = str(p.get("speech_style", "") or "")
            if speech:
                lines.append(f"说话风格: {speech}")
            fear = str(p.get("core_fear", "") or "")
            if fear:
                lines.append(f"核心恐惧: {fear}")
            facts: list = p.get("known_facts", []) or []
            if facts:
                lines.append(f"已知事实: {'；'.join(facts)}")
            lines.append("")

        if world_rules:
            lines.append("## 世界规则")
            lines.append(world_rules)
            lines.append("")

        if recent_facts:
            lines.append("## 最近已确立的事实")
            for f in recent_facts:
                lines.append(f"- {f}")
            lines.append("")

        if previous_narrative:
            lines.append("## 上段叙事（参考，检测连续性）")
            lines.append(previous_narrative)
            lines.append("")

        lines.append("## 待审计叙事文本")
        lines.append("---")
        lines.append(narrative_text)
        lines.append("---")
        lines.append("")

        lines.append("请审计以上叙事文本，输出 JSON 格式的审计结果。")

        return "\n".join(lines)


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.3}

