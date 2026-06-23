"""MaNA v4 — CharacterManager (model_tier: light) (model_tier: light).

Contains: CharacterManagerActionDirector, StateExtractor, PlanScorerAgent,
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




class CharacterManager(BaseAgent):
    """L3b — 角色涌现检测 (model_tier: light).

    扫描叙事文本中不在 Canon 的新角色名，暂存并积累。
    达到阈值后由 LLM 判定 readiness 并生成 JSON 档案。
    """

    agent_name: str = "CharacterManager"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一位**角色涌现扫描器**。你的任务是扫描一段叙事文本，找出其中可能出现的、不在已有角色列表中的新角色。

## 检测规则

1. 扫描叙事文本中的人名/角色指代
2. 与已有角色列表对比，标记不在列表中的
3. 提取特征标签（如"红发、用剑、神秘"等关键词）
4. 不重复检测已有角色

## 第二项任务: 判定 pending 实体的 readiness

对于已积累了一段文本的涌现实体，判断它是否已经"信息丰富、可以登场"。

### READY（准备就绪）
- 叙事中多次提到该实体，有足够的身世/性格/动机线索
- 可以生成完整的角色档案供后续使用

### ACCUMULATING（积累中）
- 被提到但描述还不够丰富，需要更多信息才能生成完整档案

### VAGUE（模糊）
- 提到的太少或太模糊，无法确定是否是一个独立角色

## 输出 JSON 格式

```json
{
  "detected_emergences": [
    {
      "name": "检测到的新角色名",
      "mention": "叙述原文中出现的片段",
      "feature_tags": ["特征1", "特征2"]
    }
  ],
  "readiness_results": [
    {
      "name": "待判定实体名称",
      "readiness": "READY|ACCUMULATING|VAGUE",
      "reason": "判定的中文理由",
      "profile": {"name": "...", "personality": "...", "role": "...", "appearance": "...", "speech_style": "..."}
    }
  ]
}
```

注意: readiness_results 中 profile 字段仅在 READY 时填写，ACCUMULATING/VAGUE 时 profile 为 null。
profile 遵循现有的 canon 角色 JSON 格式。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        canon_characters: dict = input_data.get("canon_characters", {}) or {}
        dynamic_npcs: dict = input_data.get("dynamic_npcs", {}) or {}
        pending_emergences: dict = input_data.get("pending_emergences", {}) or {}

        lines: list[str] = []

        # 扫描模式：检测新角色
        lines.append("## 任务1: 扫描叙事文本中的新角色")
        lines.append("---")
        lines.append(narrative_text)
        lines.append("---")
        lines.append("")

        lines.append("### 已有角色（请排除）")
        all_existing = set(canon_characters.keys()) | set(dynamic_npcs.keys())
        lines.append(", ".join(sorted(all_existing)) if all_existing else "(无)")
        lines.append("")

        # 判定模式：评估已积累的涌现实体
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
        return {"json_mode": True, "temperature": 0.3, "max_tokens": 1024}

