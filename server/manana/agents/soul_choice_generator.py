"""MaNA v4 — SoulChoiceGenerator (model_tier: light).

Generates context-aware authentic/conforming action choices
based on the current narrative and scene context.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..base_agent import BaseAgent

_log = logging.getLogger("MaNA.Agent.Light")


class SoulChoiceGenerator(BaseAgent):
    """Post-Composer agent — generates soul-aware action choices.

    Uses light-tier model for fast, contextual choice generation.
    """

    agent_name: str = "SoulChoiceGenerator"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一个角色行动选项生成器。

根据当前叙事内容，生成两组主角行动选项：
1. **本我行动 (authentic)**：按主角真实性格做出的选择
2. **贴合行动 (conforming)**：模仿被附身角色原有性格的选择

## 输出 JSON 格式

```json
{
  "authentic": [
    {"text": "具体行动描述", "hint": "为什么这是本我选择", "next_scene_hint": "下一场景提示"},
    {"text": "具体行动描述", "hint": "为什么这是本我选择", "next_scene_hint": "下一场景提示"}
  ],
  "conforming": [
    {"text": "具体行动描述", "hint": "为什么这是贴合选择", "next_scene_hint": "下一场景提示"},
    {"text": "具体行动描述", "hint": "为什么这是贴合选择", "next_scene_hint": "下一场景提示"}
  ]
}
```

## 规则

- 每组 2-3 个选项
- 选项文本 8-20 字，简洁有力
- hint 说明选择动机（5-10 字）
- next_scene_hint 提示下一场景方向（5-10 字）
- 行动必须与当前叙事场景紧密相关
- authentic 选项应体现主角真我性格
- conforming 选项应体现被附身角色的原有习惯
- 只输出 JSON，不要其他内容"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative = str(input_data.get("narrative_text", ""))
        protagonist = str(input_data.get("protagonist_name", "主角"))
        pp = input_data.get("protagonist_personality", "")
        if isinstance(pp, dict):
            traits = pp.get("traits", [])
            proto_personality = "、".join(str(t) for t in traits) if traits else ""
        else:
            proto_personality = str(pp) if pp else ""
        scene = str(input_data.get("scene_summary", ""))
        action_hints = input_data.get("action_hints", []) or []
        if isinstance(action_hints, list):
            hints_text = "、".join(str(h) for h in action_hints[:3])
        else:
            hints_text = str(action_hints)

        return f"""当前叙事内容：
{narrative[:800]}

主角：{protagonist}
主角（被附身角色）原有性格：{proto_personality or "未知"}
当前场景摘要：{scene}
叙事提示：{hints_text}

请根据以上信息生成本我和贴合两组行动选项。"""

    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.6, "max_tokens": 512}

    def _pre_llm_hook(self, input_data: dict) -> None:
        self._log_info("→ 生成灵魂选择 (authentic / conforming)...")
