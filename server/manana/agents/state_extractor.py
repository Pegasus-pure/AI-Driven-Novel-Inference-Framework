"""MaNA v4 — StateExtractor (model_tier: light) (model_tier: light).

Contains: StateExtractorActionDirector, StateExtractor, PlanScorerAgent,
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




class StateExtractor(BaseAgent):
    """Layer 4a — State Extractor (model_tier: light).

    Extracts structured JSON state changes from narrative text + character outputs.
    Forces json_mode: True, outputting strict JSON format.
    """

    agent_name: str = "StateExtractor"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一个**结构化状态提取器**。你的任务是从叙事文本和角色输出中提取所有状态变更，输出严格的 JSON 格式。

## 提取规则

### 1. 声望变化 (reputation_changes)
从叙事中推断角色对玩家好感度的变化。基于角色的言行反应：
- 正面互动 → delta 为正值 (如 +0.1)
- 负面互动 → delta 为负值 (如 -0.1)
- delta 范围建议 [-0.3, +0.3]
- 必须提供具体的原因

### 2. 情绪变化 (mood_changes)
**重要**: 采用 delta 叠加模式。
- new_mood: 角色当前的情绪状态（如"愤怒"、"欣喜"、"忧虑"、"平静"）
- intensity: 情绪强度 0.0~1.0
- cause: 导致情绪变化的直接原因

### 3. 位置变化 (location_changes)
- 只有当角色在叙事中明确发生了位置移动时才记录
- **位置跳跃审计**: 必须对照 existing_state 中该角色的前一个位置。
  如果新旧位置差异过大且叙事中缺少过渡描写（如从"酒馆"瞬移到"皇宫"），
  则不应输出 location_change，改为在 narrative_summary 中标注"位置未明确说明过渡"。

### 4. 新知识 (new_knowledge)
- 角色在叙事中认识到的新事实/信息
- known_by: 知道此信息的角色 ID 列表

### 5. 新动态 NPC (new_dynamic_npcs)
- 叙事中首次出现的新角色

### 6. 玩家画像更新 (player_profile_updates)
- 正常为 null，每 3-5 拍可输出一次。

## 输出 JSON 格式

```json
{
  "reputation_changes": [
    {"char_id": "char_001", "delta": 0.1, "reason": "玩家帮助了该角色"}
  ],
  "mood_changes": [
    {"char_id": "char_001", "new_mood": "感激", "intensity": 0.6, "cause": "获得了意想不到的帮助"}
  ],
  "location_changes": [],
  "new_knowledge": [],
  "new_dynamic_npcs": [],
  "player_profile_updates": {},
  "narrative_summary": "1-2句话摘要",
  "scene_memory_entry": "[时间/地点] 关键事实"
}
```

## 重要原则

1. **只记录发生了变化的状态**: 没有变化就输出空数组
2. **基于文本证据**: 不要臆测没有在叙事中体现的变化
3. **delta 要谨慎**: 声望变化不应过大，单次 ±0.3 为上限
4. **new_knowledge 不重复**: 检查 existing_state 中已有的 knowledge_graph

## 扩展字段（每个节拍都必须输出）

### divergence_delta (float)
- 范围: -0.2~0.2
- 正值 = 叙事偏离 Canon，负值 = 回归 Canon
- 根据叙事与 Canon 的差异程度判定

### narrative_tension (float)
- 范围: 0.0~1.0
- 当前叙事的张力强度
- 0.0=平静日常, 0.5=中等紧张, 1.0=极度危急

### character_arc_progress (dict)
- 格式: {"char_id": 0.0~1.0}
- 每个出场角色的弧光完成度。

### new_seed_conflicts (list)
- 从本次叙事中新发现的冲突种子
- 每个元素: {"type": str, "description": str, "involved_characters": [...], "intensity": float}

### narrative_mode (string)
- 当前叙事模式: "exploration" | "dialogue" | "conflict" | "revelation"

### canon_adherence (float)
- 范围: 0.0~1.0
- 本次叙事与 Canon 设定的贴合度
- 1.0=完全符合 Canon, 0.0=完全偏离
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        character_outputs: list = input_data.get("character_outputs", []) or []
        existing_state: dict = input_data.get("existing_state", {}) or {}

        lines: list[str] = []

        lines.append("## 本次叙事文本")
        lines.append("---")
        lines.append(narrative_text)
        lines.append("---")
        lines.append("")

        if character_outputs:
            lines.append("## 角色原始输出（含潜台词和态度变化信号）")
            for co in character_outputs:
                co = co if isinstance(co, dict) else {}
                lines.append(f"### {co.get('character_id', '未知')}")
                dlgs = co.get("dialogue", [])
                if isinstance(dlgs, list):
                    for d in dlgs:
                        if isinstance(d, dict):
                            lines.append(f"  - 说: {d.get('text', str(d))}")
                stance = co.get("stance_change", None)
                if isinstance(stance, dict):
                    lines.append(f"态度变化信号: {stance.get('new_attitude', '')} → {stance.get('reason', '')}")
                arc = co.get("emotional_arc", "")
                if arc:
                    lines.append(f"情感弧线: {arc}")
                lines.append("")

        if existing_state:
            lines.append("## 已有状态（仅供参考，不要输出未变化的内容）")
            moods: dict = existing_state.get("character_moods", {}) or {}
            if moods:
                lines.append("当前角色情绪:")
                for cid, m in moods.items():
                    lines.append(f"  {cid}: {m}")
            locs: dict = existing_state.get("character_locations", {}) or {}
            if locs:
                lines.append("当前角色位置:")
                for cid, l in locs.items():
                    lines.append(f"  {cid}: {l}")
            rep: dict = existing_state.get("player_reputation", {}) or {}
            if rep:
                lines.append("当前玩家声望:")
                for cid, r in rep.items():
                    lines.append(f"  {cid}: {r}")
            lines.append("")

        lines.append("请提取所有状态变更，输出严格的 JSON 格式。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        self._log_info("→ 提取状态变更...")
        log_layer("L4a", f"StateExtractor 启动 — {len(input_data.get('character_outputs', []))} 角色输出")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.2, "max_tokens": 2048})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        self._ensure_defaults(data)

        validation = MananaSchema.validate_extractor_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证警告: {validation.get('errors', [])}")

        changes_summary = self._summarize_changes(data)
        self._log_info(f"→ {changes_summary}")
        log_layer("L4a", f"StateExtractor 完成 — {changes_summary}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}

    def _ensure_defaults(self, data: dict) -> None:
        defaults: dict[str, Any] = {
            "reputation_changes": [],
            "mood_changes": [],
            "location_changes": [],
            "new_knowledge": [],
            "new_dynamic_npcs": [],
            "player_profile_updates": {},
            "narrative_summary": "",
            "scene_memory_entry": "",
            # T03 扩展字段默认值
            "divergence_delta": 0.0,
            "narrative_tension": 0.5,
            "character_arc_progress": {},
            "new_seed_conflicts": [],
            "narrative_mode": "exploration",
            "canon_adherence": 1.0,
        }
        for key, default in defaults.items():
            if key not in data:
                data[key] = default
        if not isinstance(data.get("player_profile_updates"), dict):
            data["player_profile_updates"] = {}

    def _summarize_changes(self, data: dict) -> str:
        parts: list[str] = []
        rep = data.get("reputation_changes", []) or []
        if rep:
            parts.append(f"声望变更×{len(rep)}")
        mood = data.get("mood_changes", []) or []
        if mood:
            parts.append(f"情绪变更×{len(mood)}")
        loc = data.get("location_changes", []) or []
        if loc:
            parts.append(f"位置变更×{len(loc)}")
        know = data.get("new_knowledge", []) or []
        if know:
            parts.append(f"新知识×{len(know)}")
        npcs = data.get("new_dynamic_npcs", []) or []
        if npcs:
            parts.append(f"新NPC×{len(npcs)}")
        return "；".join(parts) if parts else "无状态变更"


# ============================================================
# v4: PlanScorerAgent (Best-of-3)
# ============================================================


