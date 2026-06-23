"""MaNA v4 — ThreadManager (model_tier: medium) (model_tier: medium).

Contains: ThreadManagerMotivationEngine, DialogueWeaver, ConsistencyAuditor,
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




class ThreadManager(BaseAgent):
    """Layer 4b — Narrative Thread Manager (model_tier: medium).

    Manages narrative thread lifecycle: advancing, creating, closing, tension adjustment.
    """

    agent_name: str = "ThreadManager"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事线索管理者**。你的任务是分析当前叙事节拍，决定如何管理故事线索。

## 线索类型

- **main**: 主线——故事的核心驱动力
- **side**: 支线——辅助线索
- **identity_mystery**: 身份之谜【灵魂附生模式】——NPC 对主角身份的怀疑与认知冲突

## 输出 JSON 格式

```json
{
  "thread_advances": [
    {"thread_id": "thread_001", "intensity_delta": 0.15, "complexity_delta": 0.05}
  ],
  "new_threads": [
    {"title": "新的谜团", "type": "side", "question": "谁在深夜的图书馆里？"}
  ],
  "evolved_threads": ["thread_003"],
  "tension_adjustments": [
    {"thread_id": "thread_001", "new_tension": 0.7}
  ]
}
```

## 线索双维度模型

每条线索使用两个维度衡量（不再用单一 progress）：
- **intensity** (0.0~1.0): 紧迫/激烈程度，高 intensity 意味着线索接近爆发
- **complexity** (0.0~1.0): 复杂/深入程度，高 complexity 意味着线索盘根错节

thread_advances 中的 intensity_delta / complexity_delta 表示本拍的变化量。

## 线索永不枯竭

线索没有"关闭"（closed）状态。取而代之：
- 当线索的核心问题已被回答或方向已转化 → 标记为 evolved（已演化）
- evolved 线索从 active 移入 evolved 数组，但保留完整记录
- evolved 线索可能衍生出新的 active 线索。

## 决策原则

1. **一次只做有意义的变化**: 没有变化就是空数组
2. **演化要果断**: 如果线索问题已被回答，标记为 evolved 而非 closed
3. **新建要谨慎**: 新线索必须根植于当前叙事
4. **张力要有起伏**: 不要让所有线索都在高张力
5. **主线优先**: 优先推进和调节主线
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        beat_summary: str = str(input_data.get("beat_summary", "") or "")
        active_threads: list = input_data.get("active_threads", []) or []
        pool_config: dict = input_data.get("thread_pool_config", {}) or {}

        lines: list[str] = []

        lines.append("## 当前节拍")
        lines.append(f"节拍摘要: {beat_summary}")
        lines.append("")

        lines.append("## 叙事文本")
        _trunc_limit = 3000  # 截断长度，可通过 config.yaml truncation.thread_context 调整
        truncated = narrative_text[:_trunc_limit] + "\n...(后续内容已省略)" if len(narrative_text) > _trunc_limit else narrative_text
        lines.append(truncated)
        lines.append("")

        lines.append(f"## 当前活跃线索 ({len(active_threads)}条)")
        if not active_threads:
            lines.append("(暂无活跃线索)")
        else:
            for t in active_threads:
                t = t if isinstance(t, dict) else {}
                lines.append(f"### [{t.get('id', '?')}] {t.get('title', '无标题')}")
                lines.append(f"- 类型: {t.get('type', 'side')}")
                lines.append(f"- 强度: {t.get('intensity', 0.0) * 100:.0f}%")
                lines.append(f"- 复杂度: {t.get('complexity', 0.3) * 100:.0f}%")
                lines.append(f"- 张力: {t.get('tension', 0.5):.1f}")
                lines.append(f"- 优先级: {t.get('priority', 0.5):.1f}")
                question = str(t.get("question", "") or "")
                if question:
                    lines.append(f"- 核心问题: {question}")
                lines.append("")

        lines.append("## 线池限制")
        lines.append(f"最大活跃主线: {pool_config.get('max_active_main', 1)}")
        lines.append(f"最大活跃支线: {pool_config.get('max_active_side', 2)}")
        lines.append(f"最大子线索: {pool_config.get('max_child_threads', 5)}")
        lines.append("")

        lines.append("请根据当前叙事节拍，管理线索状态。输出 JSON 格式的变更方案。")

        return "\n".join(lines)


    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.4}

    def _ensure_defaults(self, data: dict) -> None:
        defaults: dict[str, Any] = {
            "thread_advances": [],
            "new_threads": [],
            "evolved_threads": [],
            "tension_adjustments": [],
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        # 兼容旧版 closed_threads
        if "closed_threads" in data and not data.get("evolved_threads"):
            data["evolved_threads"] = data.pop("closed_threads")

    def _summarize_thread_changes(self, data: dict) -> str:
        parts: list[str] = []
        for a in data.get("thread_advances", []) or []:
            a = a if isinstance(a, dict) else {}
            tid = a.get("thread_id", "?")
            idelta = float(a.get("intensity_delta", a.get("delta", 0.0)))
            cdelta = float(a.get("complexity_delta", 0.0))
            parts.append(f"推进[{tid}] 强度+{idelta * 100:.0f}% 复杂度+{cdelta * 100:.0f}%")
        for n in data.get("new_threads", []) or []:
            n = n if isinstance(n, dict) else {}
            parts.append(f"新建[{n.get('type', 'side')}] {n.get('title', '?')}")
        for e in data.get("evolved_threads", []) or []:
            parts.append(f"演化[{e}]")
        for t in data.get("tension_adjustments", []) or []:
            t = t if isinstance(t, dict) else {}
            parts.append(f"张力[{t.get('thread_id', '?')}] → {t.get('new_tension', 0.0):.1f}")
        return "；".join(parts) if parts else "无线索变更"


# ============================================================
# v4: PlanSynthesizerAgent (Multi-View)
# ============================================================


