"""MaNA v4 — SceneComposer (model_tier: strong)

Layer 3: Weaves the Director's plan + all Character Engine outputs into final narrative prose.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import _extract_brace_block, _try_parse_json


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
"""

        # ★ 灵魂附生模式：注入 POV 约束
        scene_ctx = getattr(self, "_last_scene_context", {}) or {}
        base_prompt += self._build_pov_prompt()

        # ── 元数据 JSON 模板（灵魂附生模式：soul_decision 替代 choices）──
        soul_decision_example = """    "authentic": [
      {"id": "auth_1", "text": "你的本我行动选项 1", "hint": "简要提示"},
      {"id": "auth_2", "text": "你的本我行动选项 2", "hint": "简要提示"}
    ],
    "conforming": [
      {"id": "conf_1", "text": "贴合角色的行动选项 1", "hint": "简要提示"},
      {"id": "conf_2", "text": "贴合角色的行动选项 2", "hint": "简要提示"}
    ]"""

        json_template = f"""
## 输出格式

你的响应分为两部分：

### 第一部分: 叙事散文（正文）
写出完整的叙事散文，4-8 段。对话使用【角色名】/引号格式。

### 第二部分: 元数据 JSON
在散文结束后，添加分隔符 `{self.JSON_SEPARATOR}`，然后输出一个 JSON 对象：

```json
{{
  "ending_hook": "结尾钩子——暗示下一步发展的悬念句",
  "action_hints": ["玩家可能的行动方向 1", "玩家可能的行动方向 2"],
  "music_mood": "场景情绪标签，如: 紧张、温馨、悲伤、神秘、欢快、庄严、平淡",
  "soul_decision": {{{{
{soul_decision_example}
  }}}}
}}
```

**soul_decision 说明**: 包含 authentic 和 conforming 两个数组，各提供 2-4 个具体行动选项。每个选项含 id（"auth_N" 或 "conf_N"）、text（选项文本）、hint（提示）。
"""
        base_prompt += f"""
**重要**: JSON 块必须是最后一个内容，位于 `{self.JSON_SEPARATOR}` 之后。叙事散文中不要包含任何 JSON 或代码块。

如果你在散文结束后没有添加分隔符，请在散文最后一行的末尾直接添加 `{self.JSON_SEPARATOR}` 然后紧跟 JSON 对象。
"""
        if optimization_hints:
            base_prompt += f"\n\n## 高质量叙事参考特征（由 PromptOptimizer 自动生成）\n{optimization_hints}\n"
        return base_prompt

    def build_user_prompt(self, input_data: dict) -> str:
        director: dict = input_data.get("director_output", {}) or {}
        character_outputs: list = input_data.get("character_outputs", []) or []
        scene_ctx: dict = input_data.get("scene_context_summary", {}) or {}

        # ★ 存储 scene_ctx 供 build_system_prompt 使用
        self._last_scene_context = scene_ctx

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

    # ────────────────────────────────────────────────
    # 灵魂附生 POV 约束
    # ────────────────────────────────────────────────

    @staticmethod
    def _build_pov_prompt() -> str:
        """构建第三人称有限视角约束 + 双灵魂叙事规则"""
        return """

## ════════════════════════════════════════
## 叙事视角约束（灵魂附生模式）
## ════════════════════════════════════════

本叙事以主角的第三人称有限视角展开。

### 规则
1. 【所见即所知】——只描述主角亲眼看到、亲耳听到、亲身感受到的内容。
2. 【内心世界】——主角的内心感受和情绪变化是叙事的核心。用第三人称文学化表达
   （"一股寒意从脊背升起"而非"他感到害怕"）。
3. 【不窥探他人内心】——不要写其他角色的内心想法，除非通过主角的外部观察和推测。
4. 【场景锚定】——场景描写以主角的位置和感知为锚点。
5. 【叙事张力来自有限信息】——利用主角不知道的信息创造悬念。

### 双灵魂叙事
主角体内寄宿着两个灵魂。叙事须体现这种内心的拉扯感：
- 用"他感到""内心有一个声音在说"来表达内心冲突
- 当两个灵魂矛盾时，用「内心深处，另一个声音在低语……」引出 canon_echo
- 不要写"玩家灵魂"或"原主灵魂"这样的概念——让叙事本身展现这种拉扯

### NPC 反应
- 如果剧情上下文中有角色认知冲突信息，在叙事中自然体现NPC的困惑反应
  （皱眉、停顿、欲言又止——不要过度解释，让行为说话）

"""

    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": False, "temperature": 0.9}

    def parse_output(self, raw_response: dict) -> dict:
        """覆盖父类 parse_output — SceneComposer 输出是叙事散文 + JSON，不是纯 JSON。

        先用自定义 _extract_ending_json 尝试提取 JSON，
        如果失败则返回最小 fallback（不阻断管线）。
        """
        content: str = raw_response.get("content", "") or ""
        if not content.strip():
            return {"ok": False, "data": {}, "error": "Empty response"}

        # 先尝试自定义提取
        meta = self._extract_ending_json(content)
        if meta:
            return {"ok": True, "data": meta, "error": ""}

        # 提取失败但有叙事正文 → 返回 fallback JSON（保留叙事正文）
        # 这是针对较小模型（如 qwen3.5:9b）不遵守输出格式的防护
        _log.warning(
            "SceneComposer JSON 提取失败（%d chars），使用 fallback 元数据", len(content)
        )
        return {
            "ok": True,
            "data": {
                "ending_hook": "",
                "action_hints": [],
                "music_mood": "平淡",
                "soul_decision": {
                    "authentic": [{"id": "auth_1", "text": "按自己的想法行动", "hint": "跟随直觉"}],
                    "conforming": [{"id": "conf_1", "text": "模仿原主的风格", "hint": "维持身份"}],
                },
            },
            "error": "",
        }

    def _extract_ending_json(self, text: str) -> dict:

        idx = text.find(self.JSON_SEPARATOR)
        if idx == -1:
            idx = text.find("\n\n\n{")
            if idx != -1:
                idx += 2
            else:
                result = self._try_extract_trailing_json(text)
                if result:
                    return result
                # 最后尝试：找代码块内的 JSON
                json_start = text.rfind("```json")
                if json_start != -1:
                    candidate = text[json_start + 7:]
                    end = candidate.find("```")
                    if end != -1:
                        candidate = candidate[:end]
                    block = _extract_brace_block(candidate.strip())
                    if block:
                        return _try_parse_json(block)
                return {}

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

        trailing_brace = text.rfind("{")
        if trailing_brace == -1:
            return {}
        candidate = text[trailing_brace:]
        block = _extract_brace_block(candidate)
        if block:
            return _try_parse_json(block)
        return {}
