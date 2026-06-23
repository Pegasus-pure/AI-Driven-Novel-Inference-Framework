"""MaNA v4 — LocationManager (model_tier: light) (model_tier: light).

Contains: LocationManagerActionDirector, StateExtractor, PlanScorerAgent,
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




class LocationManager(BaseAgent):
    """L3b — 地点涌现检测 (model_tier: light).

    扫描叙事文本中不在 Canon 的新地名，暂存并积累。
    达到阈值后由 LLM 判定 readiness 并生成 JSON 档案。
    """

    agent_name: str = "LocationManager"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一位**地点涌现扫描器**。你的任务是扫描一段叙事文本，找出其中可能出现的、不在已有地点列表中的新地点。

## 检测规则

1. 扫描叙事文本中的地名/场所指代
2. 与已有地点列表对比，标记不在列表中的
3. 提取特征标签（如"阴暗、神秘、地下"等关键词）
4. 不重复检测已有地点

## 第二项任务: 判定 pending 实体的 readiness

对于已积累了一段文本的涌现实体，判断它是否已经"信息丰富、可以登场"。

### READY（准备就绪）
- 叙事中多次提到该地点，有足够的氛围/功能/关联角色描述

### ACCUMULATING（积累中）
- 被提到但描述还不够丰富

### VAGUE（模糊）
- 提到的太少或太模糊，无法确定是否是一个独立地点

## 输出 JSON 格式

```json
{
  "detected_emergences": [
    {
      "name": "检测到的新地名",
      "mention": "叙述原文中出现的片段",
      "feature_tags": ["特征1", "特征2"]
    }
  ],
  "readiness_results": [
    {
      "name": "待判定实体名称",
      "readiness": "READY|ACCUMULATING|VAGUE",
      "reason": "判定的中文理由",
      "profile": {"name": "...", "description": "...", "atmosphere": "...", "associated_characters": []}
    }
  ]
}
```

注意: readiness_results 中 profile 字段仅在 READY 时填写。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        canon_locations: dict = input_data.get("canon_locations", {}) or {}
        dynamic_locations: dict = input_data.get("dynamic_locations", {}) or {}
        pending_emergences: dict = input_data.get("pending_emergences", {}) or {}

        lines: list[str] = []

        lines.append("## 任务1: 扫描叙事文本中的新地点")
        lines.append("---")
        lines.append(narrative_text)
        lines.append("---")
        lines.append("")

        lines.append("### 已有地点（请排除）")
        all_existing = set(canon_locations.keys()) | set(dynamic_locations.keys())
        lines.append(", ".join(sorted(all_existing)) if all_existing else "(无)")
        lines.append("")

        if pending_emergences:
            lines.append("## 任务2: 判定已有涌现实体的 readiness")
            for name, pe in pending_emergences.items():
                pe = pe if isinstance(pe, dict) else {}
                lines.append(f"### {name}")
                lines.append(f"命中次数: {pe.get('hit_count', 0)}")
                lines.append(f"特征标签: {', '.join(pe.get('feature_tags', []) or [])}")
                samples = pe.get("mention_samples", []) or []
                if samples:
                    lines.append("相关叙事摘录:")
                    for s in samples[-3:]:
                        lines.append(f"- {s}")
                lines.append("")

        lines.append("请按 JSON 格式输出检测结果和判定结果。")
        return "\n".join(lines)


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.3, "max_tokens": 512}

