"""MaNA v4 — ReflectionOracle (model_tier: strong)

Layer 5: High-level narrative assessment triggered every N beats.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import log_layer


_log = logging.getLogger("MaNA.Agent.Strong")


class ReflectionOracle(BaseAgent):
    """Layer 5 — Reflection Oracle (model_tier: strong, low-frequency).

    High-level narrative assessment triggered every 5 beats or on scene transitions.
    Evaluates pacing, character arcs, thread health, and narrative opportunities.
    """

    agent_name: str = "ReflectionOracle"
    model_tier: str = "strong"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事反思神谕**（Narrative Reflection Oracle）。

你的视角高于场景导演和编剧——你从宏观层面审视整部小说的叙事健康度。

## 评估维度

### 1. 节奏评估 (pacing_assessment)
- too_fast / balanced / too_slow

### 2. 角色观察 (character_observations)
对每个活跃角色：arc_progress, hidden_opportunity

### 3. 线索健康 (thread_health)
staleness: fresh / stale / stuck + suggestion

### 4. 叙事机会 (narrative_opportunities)
从全局视角发现的潜在叙事方向

### 5. 基调建议 (tone_recommendation)
下一场景的情绪/氛围建议

## 输出 JSON 格式

```json
{
  "pacing_assessment": {
    "rating": "balanced",
    "suggestion": "下一场景可以适当加速"
  },
  "character_observations": [{"char_id": "char_001", "arc_progress": "描述", "hidden_opportunity": "描述"}],
  "thread_health": [{"thread_id": "thread_001", "staleness": "fresh", "suggestion": "继续推进"}],
  "narrative_opportunities": ["机会1", "机会2"],
  "tone_recommendation": "建议下一场景使用悬疑基调"
}
```

## 评估原则

1. **建设性**: 发现问题时必须给出具体可行的建议
2. **全局视角**: 审视整体趋势，不是单个节拍
3. **尊重创作者**: 建议是参考性的
4. **数据驱动**: 基于实际的角色发展和线索进度
5. **鼓励创新**: 积极发现被忽略的叙事可能性
"""

    def build_user_prompt(self, input_data: dict) -> str:
        recent_beats: list = input_data.get("recent_beats_summary", []) or []
        threads_summary: str = str(input_data.get("active_threads_summary", "") or "")
        character_arcs: list = input_data.get("character_arcs", []) or []
        divergence: float = float(input_data.get("divergence_trend", 0.0))
        player: dict = input_data.get("player_profile", {}) or {}

        lines: list[str] = []

        lines.append(f"## 最近节拍 ({len(recent_beats)}个)")
        for i, beat in enumerate(recent_beats):
            lines.append(f"### 节拍 {i + 1}")
            lines.append(str(beat))
            lines.append("")

        if character_arcs:
            lines.append("## 角色弧线追踪")
            for arc in character_arcs:
                arc = arc if isinstance(arc, dict) else {}
                lines.append(f"### {arc.get('name', '??')} ({arc.get('char_id', '??')})")
                mood_prog: list = arc.get("mood_progression", []) or []
                lines.append(f"情绪轨迹: {' → '.join(mood_prog)}")
                actions: list = arc.get("key_actions", []) or []
                if actions:
                    lines.append(f"关键行动: {'；'.join(actions)}")
                shift = str(arc.get("stance_shift", "") or "")
                if shift:
                    lines.append(f"态度转变: {shift}")
                lines.append("")

        lines.append("## 线索状态")
        lines.append(threads_summary)
        lines.append("")

        lines.append("## 世界偏离度趋势")
        lines.append(f"当前偏离度: {divergence:.2f}")
        lines.append("")

        if player:
            lines.append("## 玩家画像")
            for key, value in player.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        lines.append("---")
        lines.append("请从宏观层面评估以上叙事，给出你的神谕报告 JSON。")

        return "\n".join(lines)


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.9, "max_tokens": 2048}

    def _ensure_defaults(self, data: dict) -> None:
        defaults: dict[str, Any] = {
            "pacing_assessment": {"rating": "balanced", "suggestion": ""},
            "character_observations": [],
            "thread_health": [],
            "narrative_opportunities": [],
            "tone_recommendation": "",
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
