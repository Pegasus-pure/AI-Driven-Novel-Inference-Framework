"""MaNA v4 — SceneComposer (model_tier: strong)

Layer 3: Weaves the Director's plan + all Character Engine outputs into final narrative prose.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import log_layer


_log = logging.getLogger("MaNA.Agent.Strong")


class SceneComposer(BaseAgent):
    """Layer 3 — Scene Composer (model_tier: strong).

    Weaves the Director's plan + all Character Engine outputs into final narrative prose.
    Output is plain literary prose followed by a ---JSON--- delimited metadata block.
    """

    JSON_SEPARATOR: str = "---JSON---"

    agent_name: str = "SceneComposer"
    model_tier: str = "strong"

    def build_system_prompt(self, optimization_hints: str = "") -> str:
        hints: str = optimization_hints or getattr(self, "_optimization_hints", "")
        base_prompt = f"""你是一位小说叙事大师。你的任务是根据导演计划和所有角色的输出，将场景编织为流畅自然的叙事散文。

## 叙事要求

1. **纯文学散文风格**: 用优美的中文写出 4-8 段叙事散文。像一本真正的文学小说那样写作——描写细腻、节奏有致、情感层次丰富。

2. **对话格式**: 所有对话必须使用以下格式：
   【角色名】
   "对话内容"

   每段对话独立成段，角色名放在【】中，对话内容放在双引号内。

3. **禁止 HTML 标记**: 输出必须是纯文本，不要使用任何 HTML 标签（如 <p>、<br>、<span> 等）。使用空行分隔段落。

4. **自然地整合**: 将导演的计划、各个角色的对话和行动自然地编织在一起。不要逐条罗列——让它们像小说一样流畅展开。

5. **环境描写**: 适当加入环境描写（光线、天气、气氛等），但**避免机械重复**——不要每一拍都从环境描写开头。最新叙事位于本次输入顶部，请自然接续，根据剧情动态选择从哪切入。

6. **心理描写**: 适度加入角色的内心感受和微表情，但不要过度解释。

7. **结尾钩子**: 在叙事末尾留下悬念或一个待解答的问题，激发玩家继续。

## 输出格式

你的响应分为两部分：

### 第一部分: 叙事散文（正文）
写出完整的叙事散文，4-8 段。对话使用【角色名】/引号格式。

### 第二部分: 元数据 JSON
在散文结束后，添加分隔符 `{self.JSON_SEPARATOR}`，然后输出一个 JSON 对象：

```json
{{
  "ending_hook": "结尾钩子——暗示下一步发展的悬念句",
  "action_hints": ["玩家可能的行动方向 1", "玩家可能的行动方向 2", "玩家可能的行动方向 3"],
  "music_mood": "场景情绪标签，如: 紧张、温馨、悲伤、神秘、欢快、庄严、平淡",
  "choices": [
    {{"id": "c1", "text": "仔细观察周围环境", "hint": "了解你身处何方", "next_scene_hint": "observe_surroundings"}},
    {{"id": "c2", "text": "检查自己的状态和记忆", "hint": "弄清楚你是谁", "next_scene_hint": "self_examination"}},
    {{"id": "c3", "text": "向前迈出一步探索", "hint": "主动探索未知世界", "next_scene_hint": "step_forward"}}
  ]
}}
```

## choices 字段说明
- choices 是玩家在本节拍叙事结束后可选择的行动选项
- choices 最少 2 个，最多 4 个
- 每个 choice 必须包含 id/text/hint/next_scene_hint 四个字段
- id 格式为 c1, c2, c3...
- choices 应当与当前场景和叙事内容紧密相关，是玩家自然可能采取的行动
- hint 是对该选项的简短提示（显示为次要文字）
- next_scene_hint 是给导演的提示，告诉导演玩家选此选项后应如何推进

**重要**: JSON 块必须是最后一个内容，位于 `{self.JSON_SEPARATOR}` 之后。叙事散文中不要包含任何 JSON 或代码块。
"""
        if optimization_hints:
            base_prompt += f"\n\n## 高质量叙事参考特征（由 PromptOptimizer 自动生成）\n{optimization_hints}\n"
        return base_prompt

    def build_user_prompt(self, input_data: dict) -> str:
        director: dict = input_data.get("director_output", {}) or {}
        character_outputs: list = input_data.get("character_outputs", []) or []
        scene_ctx: dict = input_data.get("scene_context_summary", {}) or {}

        lines: list[str] = []

        recent: str = str(input_data.get("recent_narrative", "") or "")
        if recent:
            lines.append("## 最近叙事（接续上文——从这里直接继续写下去）")
            lines.append(recent)
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append("## 场景信息")
        lines.append(f"当前时间: {scene_ctx.get('game_time', '未知')}")
        lines.append(f"地点: {scene_ctx.get('location_name', '未知')}")
        lines.append(f"氛围: {scene_ctx.get('location_atmosphere', '')}")
        lines.append("")

        style: dict = scene_ctx.get("writing_style", {}) or {}
        if style:
            lines.append(f"写作风格指引: 语气={style.get('tone', '中性')}, 节奏={style.get('pace', '适中')}, 对话风格={style.get('dialogue_style', '自然')}")
            lines.append("")

        lines.append(f"玩家行动: {scene_ctx.get('player_action', '(无)')}")
        lines.append("")

        lines.append("## 导演计划")
        lines.append(f"节拍摘要: {director.get('beat_summary', '')}")
        lines.append(f"叙事模式: {director.get('narrative_mode', '')}")
        lines.append(f"场景基调: {director.get('scene_tone', '')}")
        lines.append("")

        lines.append("## 角色输出")
        for co in character_outputs:
            co = co if isinstance(co, dict) else {}
            lines.append(f"### 角色: {co.get('character_id', '未知')}")

            dlgs = co.get("dialogue", [])
            if isinstance(dlgs, list):
                for d in dlgs:
                    if isinstance(d, dict):
                        lines.append(f"  - 说: {d.get('text', '')} [{d.get('tone', '')}]")
                    else:
                        lines.append(f"  - 说: {d}")
            elif isinstance(dlgs, str):
                lines.append(f"  - 说: {dlgs}")

            actions = co.get("actions", [])
            if isinstance(actions, list) and actions:
                action_strs = []
                for a in actions:
                    if isinstance(a, dict):
                        action_strs.append(a.get("description", str(a)))
                    else:
                        action_strs.append(str(a))
                lines.append(f"行动: {'；'.join(action_strs)}")

            arc = co.get("emotional_arc", "")
            if arc:
                lines.append(f"情感弧线: {arc}")

            stance = co.get("stance_change", None)
            if isinstance(stance, dict):
                lines.append(f"态度变化: {stance.get('new_attitude', '')} → 原因: {stance.get('reason', '')}")
            lines.append("")

        hints: list = input_data.get("refinement_hints", []) or []
        if hints:
            mode = input_data.get("mode", "refine")
            lines.append(f"## {'精炼' if mode == 'refine' else '重写'}提示")
            for hint in hints:
                if isinstance(hint, dict):
                    lines.append(f"- [{hint.get('severity', '')}] {hint.get('description', '')}: {hint.get('fix_suggestion', '')}")
            lines.append("")

        lines.append("---")
        lines.append("请根据以上所有信息，创作本场景的叙事散文。先看顶部的「最近叙事」并自然接续——不要机械地从环境描写开头。然后用 ---JSON--- 分隔，最后输出元数据 JSON。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        self._log_info("→ 编织叙事散文...")
        log_layer("L3", f"SceneComposer 启动 — {len(input_data.get('character_outputs', []))} 角色输出")

        result = await self._call_llm(sys, usr, {"json_mode": False, "temperature": 0.9})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        content: str = result.get("content", "")

        narrative_only = self._strip_json_suffix(content)
        json_data = self._extract_ending_json(content)

        if json_data:
            validation = MananaSchema.validate_composer_output(json_data)
            if not validation.get("valid", False):
                self._log_warn(f"元数据验证警告: {validation.get('errors', [])}")

        if not narrative_only.strip():
            narrative_only = content
            json_data = {"ending_hook": "", "action_hints": [], "music_mood": "", "choices": []}

        choices = json_data.get("choices", [])
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            from ..defaults import get_default_choices
            choices = get_default_choices(2)
        valid_choices = []
        for c in choices:
            if isinstance(c, dict) and all(k in c for k in ("id", "text", "hint", "next_scene_hint")):
                valid_choices.append(c)
        if len(valid_choices) < 2:
            from ..defaults import get_default_choices
            defaults = get_default_choices(2)
            while len(valid_choices) < 2:
                valid_choices.append(defaults[len(valid_choices)])
        json_data["choices"] = valid_choices[:4]

        self._log_info(f"→ 叙事散文 ({len(narrative_only)} 字符), 钩子: {json_data.get('ending_hook', '')}, choices: {len(json_data.get('choices', []))}")
        log_layer("L3", f"SceneComposer 完成 — {len(narrative_only)} 字符叙事")

        return {"ok": True, "content": narrative_only, "raw": json_data}

    def _extract_ending_json(self, text: str) -> dict:
        from ..utils import _extract_brace_block, _try_parse_json

        idx = text.find(self.JSON_SEPARATOR)
        if idx == -1:
            idx = text.find("\n\n\n{")
            if idx != -1:
                idx += 2
            else:
                return self._try_extract_trailing_json(text)

        if text.find(self.JSON_SEPARATOR) != -1:
            json_text = text[idx + len(self.JSON_SEPARATOR):].strip()
        else:
            json_text = text[idx + 1:].strip()

        if json_text.startswith("{"):
            block = _extract_brace_block(json_text)
            if block:
                json_text = block

        return _try_parse_json(json_text)

    def _strip_json_suffix(self, text: str) -> str:
        suffix_idx = text.find(self.JSON_SEPARATOR)
        if suffix_idx == -1:
            last_brace = text.rfind("\n{")
            if last_brace != -1:
                after = text[last_brace + 1:].strip()
                if after.startswith("{") and after.endswith("}"):
                    return text[:last_brace].strip()
            return text.strip()
        return text[:suffix_idx].strip()

    def _try_extract_trailing_json(self, text: str) -> dict:
        from ..utils import _extract_brace_block, _try_parse_json

        trailing_brace = text.rfind("{")
        if trailing_brace == -1:
            return {}
        candidate = text[trailing_brace:]
        block = _extract_brace_block(candidate)
        if block:
            return _try_parse_json(block)
        return {}
