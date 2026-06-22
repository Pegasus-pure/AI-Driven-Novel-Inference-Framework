"""MaNA v4 — RoleReflector (model_tier: light) (model_tier: light).

Contains: RoleReflectorActionDirector, StateExtractor, PlanScorerAgent,
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




class RoleReflector(BaseAgent):
    """L2R3 — 角色过渡反思 (model_tier: light).

    逐角色审计 L2R2 生成的表演是否存在状态跳跃。
    支持三种判决：PASS / NEED_TRANSITION / NEED_REWRITE。
    """

    agent_name: str = "RoleReflector"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一位**角色表演审计师**。你的任务是审查每个角色的表演是否符合其上一拍的状态，是否存在跳跃。

## 检测维度

### 1. 服装不一致 (clothing_mismatch)
- 上一拍脱了外套/摘了配饰，这一拍又穿着，没有过渡说明
- 如:"上一拍已脱掉斗篷，这一拍却披着斗篷出现"

### 2. 位置跳跃 (location_jump)
- 角色位置突然变化，没有过渡或必要的时间间隔
- 如:"上一拍在酒馆后排，这一拍瞬间出现在门口"

### 3. 情绪断裂 (mood_break)
- 角色的情绪状态与前文不衔接，无合理过渡
- 如:"上一拍悲恸欲绝，这一拍突然兴高采烈"

### 4. 关系断裂 (relationship_break)
- 角色间的关系状态发生跳跃
- 如:"上一拍还在激烈争吵，这一拍就如老朋友般寒暄"

## 三种判决

### PASS（通过）
- 表演与历史状态一致，无跳跃

### NEED_TRANSITION（添加过渡）
- 有小跳跃（服装、微情绪），通过附加过渡描述/对白即可修复
- 不需要重新调用 LLM 生成完整表演

### NEED_REWRITE（打回重做）
- 有大跳跃（位置突变、关系逆转），需要打回 L2R2 重做

## 输出 JSON 格式

```json
{
  "results": [
    {
      "char_id": "string",
      "verdict": "PASS|NEED_TRANSITION|NEED_REWRITE",
      "issues": [
        {
          "type": "clothing_mismatch|location_jump|mood_break|relationship_break",
          "previous": "上一拍的状态",
          "current": "这一拍的状态",
          "gap": "具体差距描述"
        }
      ],
      "transition_dialogue": "过渡对白（NEED_TRANSITION 时填写）",
      "transition_action": "过渡动作描述（NEED_TRANSITION 时填写）",
      "rewrite_constraint": "重做约束（NEED_REWRITE 时填写）"
    }
  ]
}
```

## 重要原则

1. **过渡优于重做**: 小问题尽量用 NEED_TRANSITION 解决，NEED_REWRITE 是最后手段
2. **过渡对话要自然**: 如"他愣了一下，想起刚才已经把外套脱了，又随手披上"
3. **具体明确**: NEED_REWRITE 时必须给出明确的约束，指导 L2R2 重做方向
"""

    def build_user_prompt(self, input_data: dict) -> str:
        performances: list = input_data.get("character_performances", []) or []
        previous_states: dict = input_data.get("previous_states", {}) or {}
        beat_plan: dict = input_data.get("beat_plan", {}) or {}

        lines: list[str] = []

        lines.append("## 节拍上下文")
        lines.append(json.dumps(beat_plan, ensure_ascii=False, indent=2))
        lines.append("")

        if previous_states:
            lines.append("## 角色上一拍状态")
            for char_id, state in previous_states.items():
                state = state if isinstance(state, dict) else {}
                parts = [f"位置: {state.get('location', '?')}",
                         f"情绪: {state.get('mood', '?')}"]
                wearing = state.get("wearing", "")
                if wearing:
                    parts.append(f"衣着: {wearing}")
                holding = state.get("holding", "")
                if holding:
                    parts.append(f"持有: {holding}")
                rels = state.get("relationships", {}) or {}
                if rels:
                    rel_str = "; ".join(f"{k}={v}" for k, v in rels.items())
                    parts.append(f"关系: {rel_str}")
                lines.append(f"### {char_id}")
                lines.append(f"{' | '.join(parts)}")
            lines.append("")

        lines.append("## 当前角色表演")
        for p in performances:
            p = p if isinstance(p, dict) else {}
            lines.append(f"### {p.get('character_id', p.get('char_id', '?'))}")
            dlgs = p.get("dialogue", []) or []
            if dlgs:
                for d in dlgs:
                    d = d if isinstance(d, dict) else {}
                    lines.append(f"  说 [{d.get('tone', '')}]: {d.get('text', '')}")
            actions = p.get("actions", []) or []
            if actions:
                for a in actions:
                    a = a if isinstance(a, dict) else {}
                    lines.append(f"  动作: {a.get('description', '')}")
            mood = p.get("mood", p.get("emotional_arc", ""))
            if mood:
                lines.append(f"  情绪: {mood}")
            lines.append("")

        lines.append("请逐角色审计表演是否与上一拍状态一致。输出 JSON。")
        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_count = len(input_data.get("character_performances", []) or [])
        self._log_info(f"→ 反思 {char_count} 个角色的表演...")
        log_layer("L2R3", f"RoleReflector 启动 ({char_count} 角色)")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.3, "max_tokens": 2048})

        if not result.get("ok", False):
            return {"ok": False, "results": [], "raw": {},
                    "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "results": [], "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        results: list = data.get("results", []) or []

        pass_count = sum(1 for r in results if r.get("verdict") == "PASS")
        transition_count = sum(1 for r in results if r.get("verdict") == "NEED_TRANSITION")
        rewrite_count = sum(1 for r in results if r.get("verdict") == "NEED_REWRITE")

        if rewrite_count > 0:
            self._log_warn(f"⚠ 角色审计: {pass_count}通过/{transition_count}过渡/{rewrite_count}重做")
        else:
            self._log_info(f"→ 角色审计: {pass_count}通过/{transition_count}过渡/{rewrite_count}重做")
        log_layer("L2R3", f"RoleReflector 完成 — {pass_count}PASS/{transition_count}TRANS/{rewrite_count}REWR")

        return {"ok": True, "results": results, "raw": data}


# ============================================================
# L3b: CharacterManager (涌现建议 — 角色检测)
# ============================================================


