"""MaNA v4 — SceneDirector (model_tier: strong)

Layer 1: Decides beat plan, interaction pairs, featured characters, and scene tone.
"""

from __future__ import annotations

import logging
from typing import Any

from ..base_agent import BaseAgent
from ..schema import MananaSchema
from ..utils import log_layer


_log = logging.getLogger("MaNA.Agent.Strong")


class SceneDirector(BaseAgent):
    """Layer 1 — Scene Director (导演层).

    Decides beat plan, interaction pairs, featured characters, and scene tone.
    The central narrative decision-making hub of the MaNA pipeline.
    """

    agent_name: str = "SceneDirector"
    model_tier: str = "strong"

    def build_system_prompt(self) -> str:
        return """你是一个互动叙事系统的**场景导演**。

你的任务是：根据当前世界状态和玩家的行动，决定下一个叙事节拍的走向。

你拥有绝对的叙事调度权——选择哪些角色出场、谁和谁产生交互、场景的基调是什么。

## 输出 JSON 格式

必须输出一个严格的 JSON 对象，包含以下字段：

```json
{
  "beat_id": "当前节拍唯一标识(字符串)",
  "narrative_mode": "exploration|dialogue|conflict|revelation|daily_life 五选一",
  "beat_summary": "1-2 句话描述本节拍将发生什么",
  "featured_characters": ["char_id_1", "char_id_2"],
  "interaction_pairs": [
    {
      "pair_id": "pair_01",
      "char_ids": ["char_a", "char_b"],
      "pair_type": "dialogue|action|both"
    }
  ],
  "unpaired_characters": ["char_id"],
  "scene_tone": "紧张|友好|暧昧|悲伤|欢快|神秘|庄严|恐惧|平淡",
  "priority_thread_ids": ["thread_id"],
  "required_canon": ["char_id"]
}
```

## 字段说明

- **beat_id**: 当前节拍 ID，建议格式 "beat_场景_序号"
- **narrative_mode**: 
  - exploration: 探索环境、收集信息
  - dialogue: 对话为主、角色交流
  - conflict: 冲突/对抗/紧张局面
  - revelation: 揭示/发现/真相揭露
  - daily_life: 日常生活（低张力过渡模式，用于角色塑造和情感沉淀）
- **beat_summary**: 简练概括本节拍的核心叙事事件
- **featured_characters**: 所有在本节拍中出场的角色 char_id 列表，优先同地点角色，**每拍选 1-4 个**（随机变化，避免每拍出场人数固定）
- **interaction_pairs**: 角色之间的交互对。两个角色对话/互动为一对。玩家总是隐式在场，不需要放入 pair
- **unpaired_characters**: 出场但不参与交互对的独立角色
- **scene_tone**: 场景整体氛围
- **priority_thread_ids**: 本节拍应推进的叙事线索 ID 列表
- **required_canon**: 需要完整 personality 信息的角色 char_id 列表

## 角色选择与场景切换

- **同地点优先**: 主要从当前场景的角色中选择 featured_characters
- **跨地点切镜**: 角色列表中标记为 cross_location 的是其他地点的角色。如果选中他们，意味着叙事镜头切换到该地点——可能那里正在发生更重要的事件，或需要并行叙事
- **并行叙事**: 可以使用 daily_life 或 conflict 模式切入其他地点，短暂展示后切回主线

## 模式说明

### exploration
探索环境、收集信息。适合进入新场景时的初始阶段。
### dialogue
对话为主，角色交流。适合推进角色关系和获取情报。
### conflict
冲突/对抗/紧张局面。适合高潮和紧张时刻。
### revelation
揭示/发现/真相揭露。适合关键信息的揭露时刻。
### daily_life
日常生活。低张力过渡模式，用于角色塑造和情感沉淀。
- 角色展示日常习惯、互动、细微情感变化
- 适合：角色间小型互动、环境细节发现、玩家融入世界的喘息时刻

## 导演原则

1. 每次节拍推进 1-2 个线索，不要试图一次性推进所有线索
2. 交互对最多 2 组（4 个角色），避免场景过于拥挤
3. 根据世界偏离度调整叙事策略——偏离度低时忠实原著，偏离度高时大胆创新
4. 优先选择与玩家当前行动相关的角色出场
5. 场景基调应与当前情绪和位置氛围一致
"""

    def build_user_prompt(self, input_data: dict) -> str:
        scene_context: dict = input_data.get("scene_context", {}) or {}
        lines: list[str] = []

        lines.append("## 当前世界状态")
        lines.append("")

        lines.append(f"游戏时间: {scene_context.get('game_time', '未知')}")
        lines.append(f"世界偏离度: {scene_context.get('divergence', 0.0):.2f}")
        lines.append("")

        location: dict = scene_context.get("location", {}) or {}
        lines.append("### 当前地点")
        lines.append(f"名称: {location.get('name', '未知')}")
        desc = location.get("description", "")
        if desc:
            lines.append(f"描述: {desc}")
        atm = location.get("atmosphere", "")
        if atm:
            lines.append(f"氛围: {atm}")
        lines.append("")

        player: dict = scene_context.get("player", {}) or {}
        lines.append("### 玩家")
        lines.append(f"玩家行动: {player.get('action', '(无)')}")
        profile: dict = player.get("profile", {}) or {}
        traits: list = profile.get("traits", []) or []
        lines.append(f"已发现性格: {'、'.join(traits) if traits else '未知'}")
        lines.append(f"当前动机: {profile.get('motivation', '未知')}")
        lines.append(f"行为倾向: {profile.get('tendency', '中立')}")
        rep: dict = player.get("reputation", {}) or {}
        if rep:
            lines.append("对各角色态度:")
            for char_id, attitude in rep.items():
                lines.append(f"  {char_id}: {attitude}")
        lines.append("")

        characters: list = scene_context.get("characters", []) or []
        lines.append(f"### 当前场景角色 ({len(characters)}人)")
        for c in characters:
            c = c if isinstance(c, dict) else {}
            lines.append(f"- {c.get('name', '??')} (id: {c.get('char_id', '??')})")
            cs: dict = c.get("current_state", {}) or {}
            lines.append(f"  地点: {cs.get('location', '?')} | 情绪: {cs.get('mood', '中性')} | 目标: {cs.get('goal', '无')}")
            rel = c.get("relation_to_player", "")
            if rel:
                lines.append(f"  对玩家: {rel}")
            pers = c.get("personality", "")
            if pers:
                lines.append(f"  性格: {pers}")
            facts: list = c.get("known_facts", []) or []
            if facts:
                lines.append(f"  已知事实: {'；'.join(facts)}")
        lines.append("")

        threads: list = scene_context.get("active_threads", []) or []
        lines.append(f"### 活跃叙事线索 ({len(threads)}条)")
        for t in threads:
            t = t if isinstance(t, dict) else {}
            lines.append(f"- [{t.get('id', '?')}] {t.get('title', '?')} (强度: {t.get('intensity', 0.0) * 100:.0f}%, 张力: {t.get('tension', 0.3):.1f})")
        lines.append("")

        conflicts: list = scene_context.get("available_conflicts", []) or []
        if conflicts:
            lines.append("### 可用叙事冲突模板")
            for c in conflicts:
                c = c if isinstance(c, dict) else {}
                cid = c.get("id", "?")
                ctype = c.get("type", "?")
                desc_ = c.get("description", "")
                chars = c.get("involved_characters", []) or []
                variants = c.get("variants", []) or []
                lines.append(f"- [{cid}] 类型: {ctype}")
                lines.append(f"  描述: {desc_}")
                if chars:
                    lines.append(f"  涉及角色: {', '.join(chars)}")
                if variants:
                    lines.append(f"  可能变体: {'; '.join(variants)}")
            lines.append("")

        current_mode = scene_context.get("narrative_mode", "")
        mode_duration = scene_context.get("mode_duration", 0)
        suggested_next = scene_context.get("suggested_next_modes", [])
        if current_mode or mode_duration > 0:
            lines.append("### 叙事模式轮换提示")
            if current_mode:
                lines.append(f"当前叙事模式: {current_mode}（已持续 {mode_duration} 拍）")
            if suggested_next:
                lines.append(f"建议可考虑的下一个模式: {'、'.join(suggested_next)}")
            lines.append("可以考虑切换模式以丰富叙事节奏。")
            lines.append("")

        history: list = scene_context.get("recent_history", []) or []
        if history:
            lines.append("### 最近叙事事件")
            for evt in history:
                evt = evt if isinstance(evt, dict) else {}
                lines.append(f"- [{evt.get('time', '')}] {evt.get('summary', '')}")
            lines.append("")

        scene_mem: list = scene_context.get("scene_memory", []) or []
        long_mem: list = scene_context.get("long_term_memory", []) or []
        if scene_mem:
            lines.append("### 场景记忆")
            for m in scene_mem:
                lines.append(f"- {m}")
            lines.append("")
        if long_mem:
            lines.append("### 长期记忆")
            for m in long_mem:
                lines.append(f"- {m}")
            lines.append("")

        rules: str = str(scene_context.get("relevant_world_rules", "") or "")
        if rules:
            lines.append("### 相关世界规则")
            lines.append(rules)
            lines.append("")

        micro_fb = scene_context.get("micro_feedback", "")
        if micro_fb:
            lines.append("### 上拍质量反馈")
            lines.append(str(micro_fb))
            lines.append("")

        prev_hook = str(scene_context.get("prev_ending_hook", "") or "")
        prev_hints = scene_context.get("prev_action_hints", []) or []
        if prev_hook:
            lines.append("### 上拍结尾提示")
            lines.append(f"结尾钩子: {prev_hook}")
            if prev_hints:
                lines.append(f"可能的前进方向: {'、'.join(prev_hints)}")
            lines.append("你的剧本应基于以上提示自然延续，不要偏离上一拍的结尾方向。")
            lines.append("")

        director_mem = scene_context.get("director_memory", "")
        if director_mem:
            lines.append("### 你的过往决策记录")
            lines.append(director_mem)
            lines.append("")

        lines.append("请根据以上信息，输出你的导演计划 JSON。")
        return "\n".join(lines)

    def _get_llm_options(self, input_data: dict) -> dict:
        return {"json_mode": True, "temperature": 0.8}

