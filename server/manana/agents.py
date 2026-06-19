"""MaNA v4 Agent Implementations.

  L0: ContextBuilder
  L1: SceneDirector + v4 PlanScorer + v4 PlanSynthesizer
  L1b: ContinuityChecker
  L2R1: MotivationEngine
  L2R2: DialogueWeaver + ActionDirector
  L2R3: RoleReflector
  L3: SceneComposer
  L3b: ConsistencyAuditor
  L3b∥: CharacterManager + LocationManager
  L4a: StateExtractor
  L4b: ThreadManager
  L5: ReflectionOracle
  v4: MicroOracleAgent
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .base_agent import BaseAgent
from .schema import MananaSchema
from .utils import log_layer


_log = logging.getLogger("MaNA.Agent")

# ============================================================
# L1: SceneDirector
# ============================================================


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
- **featured_characters**: 所有在本节拍中出场的角色 char_id 列表
- **interaction_pairs**: 角色之间的交互对。两个角色对话/互动为一对。玩家总是隐式在场，不需要放入 pair
- **unpaired_characters**: 出场但不参与交互对的独立角色
- **scene_tone**: 场景整体氛围
- **priority_thread_ids**: 本节拍应推进的叙事线索 ID 列表
- **required_canon**: 需要完整 personality 信息的角色 char_id 列表

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

        # Basic info
        lines.append(f"游戏时间: {scene_context.get('game_time', '未知')}")
        lines.append(f"世界偏离度: {scene_context.get('divergence', 0.0):.2f}")
        lines.append("")

        # Location
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

        # Player
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

        # Characters
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

        # Active threads
        threads: list = scene_context.get("active_threads", []) or []
        lines.append(f"### 活跃叙事线索 ({len(threads)}条)")
        for t in threads:
            t = t if isinstance(t, dict) else {}
            lines.append(f"- [{t.get('id', '?')}] {t.get('title', '?')} (强度: {t.get('intensity', 0.0) * 100:.0f}%, 张力: {t.get('tension', 0.3):.1f})")
        lines.append("")

        # Available conflicts (T02: 冲突种子注入)
        conflicts: list = scene_context.get("available_conflicts", []) or []
        if conflicts:
            lines.append("### 可用叙事冲突模板")
            for c in conflicts:
                c = c if isinstance(c, dict) else {}
                cid = c.get("id", "?")
                ctype = c.get("type", "?")
                desc = c.get("description", "")
                chars = c.get("involved_characters", []) or []
                variants = c.get("variants", []) or []
                lines.append(f"- [{cid}] 类型: {ctype}")
                lines.append(f"  描述: {desc}")
                if chars:
                    lines.append(f"  涉及角色: {', '.join(chars)}")
                if variants:
                    lines.append(f"  可能变体: {'; '.join(variants)}")
            lines.append("")

        # Mode rotation hint (T04)
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

        # Recent history
        history: list = scene_context.get("recent_history", []) or []
        if history:
            lines.append("### 最近叙事事件")
            for evt in history:
                evt = evt if isinstance(evt, dict) else {}
                lines.append(f"- [{evt.get('time', '')}] {evt.get('summary', '')}")
            lines.append("")

        # Memory
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

        # World rules
        rules: str = str(scene_context.get("relevant_world_rules", "") or "")
        if rules:
            lines.append("### 相关世界规则")
            lines.append(rules)
            lines.append("")

        # v4: Micro-Oracle feedback
        micro_fb = scene_context.get("micro_feedback", "")
        if micro_fb:
            lines.append("### 上拍质量反馈")
            lines.append(str(micro_fb))
            lines.append("")

        # 上拍结尾提示（上一拍的 ending_hook —— 本拍应自然接续此方向）
        prev_hook = str(scene_context.get("prev_ending_hook", "") or "")
        prev_hints = scene_context.get("prev_action_hints", []) or []
        if prev_hook:
            lines.append("### 上拍结尾提示")
            lines.append(f"结尾钩子: {prev_hook}")
            if prev_hints:
                lines.append(f"可能的前进方向: {'、'.join(prev_hints)}")
            lines.append("你的剧本应基于以上提示自然延续，不要偏离上一拍的结尾方向。")
            lines.append("")

        # Director memory（记忆系统注入 — 你的过往决策记录）
        director_mem = scene_context.get("director_memory", "")
        if director_mem:
            lines.append("### 你的过往决策记录")
            lines.append(director_mem)
            lines.append("")

        lines.append("请根据以上信息，输出你的导演计划 JSON。")
        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        ctx = input_data.get("scene_context", {}) or {}
        self._log_info("→ 调度节拍...")
        log_layer("L1", f"SceneDirector 启动 — 分析场景上下文 ({len(ctx.get('characters', []))} 角色, {len(ctx.get('active_threads', []))} 线索)")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.8})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        validation = MananaSchema.validate_director_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证失败: {validation.get('errors', [])}")

        self._log_info(f"→ 节拍: {data.get('beat_id', '?')}, 模式: {data.get('narrative_mode', '?')}, "
                       f"出场: {len(data.get('featured_characters', []))} 角色")
        log_layer("L1", f"SceneDirector 完成 — 节拍: {data.get('beat_id', '?')}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L2R1: MotivationEngine
# ============================================================


class MotivationEngine(BaseAgent):
    """Layer 2R1 — Motivation Engine (model_tier: medium).

    Independently analyzes each character's internal state, emotion, hidden intent,
    and subtext. Characters are fully isolated — no cross-character data leakage.
    """

    agent_name: str = "MotivationEngine"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一个互动叙事系统的**动机分析引擎**。

你的任务是：根据单个角色的性格、当前状态和所处场景，分析其内心世界。

## 关键原则

1. **角色隔离**: 你只知道这一个角色的信息。不要假设其他角色知道什么或怎么想。
2. **一致性**: 角色的内部状态必须与其性格特点和已知事实一致。
3. **叙事驱动**: 不要平淡——角色应该有明确的目标和情感取向，推动叙事发展。
4. **潜台词**: 角色的真实想法可能与外显情绪不同。subtext 和 hidden_intent 是角色的内心秘密，不对外暴露。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "internal_state": {
    "mood": "喜悦|愤怒|恐惧|悲伤|好奇|中性",
    "mood_intensity": 0.0,
    "dominant_emotion": "描述当前最强烈的情绪",
    "subtext": "角色的潜台词——表面之下真正的想法",
    "hidden_intent": "角色的隐藏意图——不为人知的真实目标",
    "immediate_goal": "角色在当前场景中的直接目标"
  },
  "stance_toward_player": {
    "attitude": "友善|中立|冷淡|敌视|戒备",
    "trust_level": 0.0,
    "wants_to": "主动交谈|保持距离|观察玩家|无视玩家|试探玩家|寻求帮助"
  }
}
```

## 字段说明

- **mood**: 角色当前基础情绪
- **mood_intensity**: 0.0-1.0，情绪强烈程度
- **dominant_emotion**: 用自然语言描述角色当下的主导情绪（如 "隐隐不安"、"满怀期待"）
- **subtext**: 角色的潜台词。外显情绪之下真正的内心活动。这不会被其他角色看到
- **hidden_intent**: 角色的隐藏意图。真正的目标是什么？这会驱动其行为但不直接暴露
- **immediate_goal**: 在当前场景/节拍中想达成什么
- **attitude**: 对玩家的外显态度
- **trust_level**: 0.0-1.0，对玩家的信任程度
- **wants_to**: 在本节拍中想和玩家产生怎样的互动

如果一个角色对玩家没有特别的感受（如路人级 NPC），stance 设为中立即可，不要编造。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        scene_summary: str = str(input_data.get("scene_summary", "") or "")
        player_action: str = str(input_data.get("player_action", "") or "")
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))

        lines: list[str] = []

        lines.append("## 场景上下文")
        lines.append(f"场景基调: {scene_tone}")
        if scene_summary:
            lines.append(f"节拍摘要: {scene_summary}")
        if player_action:
            lines.append(f"玩家行动: {player_action}")
        lines.append("")

        lines.append("## 角色信息")
        lines.append(f"角色 ID: {character.get('char_id', '?')}")
        lines.append(f"名字: {character.get('name', '?')}")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        role = str(character.get("role", "") or "")
        if role:
            lines.append(f"原著角色定位: {role}")

        cs: dict = character.get("current_state", {}) or {}
        lines.append(f"当前地点: {cs.get('location', '?')}")
        lines.append(f"当前情绪: {cs.get('mood', '中性')}")
        goal = cs.get("goal", "")
        if goal:
            lines.append(f"当前目标: {goal}")

        facts: list = character.get("known_facts", []) or []
        if facts:
            lines.append(f"已知事实: {'；'.join(facts)}")

        # 角色记忆（记忆系统注入 — 你之前经历过的事）
        char_mem = character.get("character_memory", "")
        if char_mem:
            lines.append(f"角色经历: {char_mem}")

        rel = str(character.get("relation_to_player", "") or "")
        if rel:
            lines.append(f"对玩家的态度: {rel}")

        anti_rules: list = character.get("anti_rules", []) or []
        if anti_rules:
            lines.append("")
            lines.append("## 行为禁区（绝对不能违反）")
            for rule in anti_rules:
                lines.append(f"- {rule}")

        lines.append("")
        lines.append("请分析此角色在本节拍中的内心状态。输出 JSON。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 分析 {char_name} ...")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.7})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))

        validation = MananaSchema.validate_motivation_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证失败: {validation.get('errors', [])}")

        mood = str((data.get("internal_state", {}) or {}).get("mood", "?"))
        self._log_info(f"→ {char_name}: 情绪={mood}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L2R2: DialogueWeaver
# ============================================================


class DialogueWeaver(BaseAgent):
    """Layer 2R2 — Dialogue Weaver (model_tier: medium).

    Generates dialogue content, tone, wording, and emotional arcs per character.
    Characters in interaction pairs receive counterpart motivation summaries
    (only emotional tone and visible goals, no hidden_intent).
    """

    agent_name: str = "DialogueWeaver"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一个互动叙事系统的**对话编织者 (Dialogue Weaver)**。

你的任务是：为一个角色生成在当前场景中的对话和情绪弧线。

## 关键原则

1. **角色一致性**: 对话必须符合角色的性格、身份和语言风格
2. **情绪流动**: 对话是动态的——情绪可能在对话过程中发生变化（emotional_arc）
3. **潜台词**: 角色说的和心里想的可能不一样。利用动机分析中的 subtext
4. **互动性**: 如果角色在对话中（有 counterpart），注意反应和互动
5. **玩家驱动**: 玩家的行动是触发因素。角色应对玩家的行为有语言上的回应

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "dialogue": [
    {
      "text": "角色说出的对白文本",
      "tone": "愤怒|平静|讽刺|热情|冷淡|紧张|温柔|戏谑|严肃|悲伤|好奇|威胁",
      "target": "char_id 或 player",
      "subtext": "这句话背后的真正含义"
    }
  ],
  "actions": [
    {
      "type": "gesture|movement|facial|interaction",
      "description": "动作描述",
      "target": "动作对象"
    }
  ],
  "emotional_arc": "情绪弧线描述——从对话开始时到结束时的情绪变化",
  "stance_change": {
    "new_attitude": "友善|中立|冷淡|敌视|戒备",
    "reason": "态度变化的原因"
  }
}
```

## 字段说明

- **dialogue**: 对话数组。每个元素是一条对白。可以有多条（角色可能说多句话、换语气）
- **dialogue[].text**: 角色说出的具体话语。用中文
- **dialogue[].tone**: 说这句话时的语气
- **dialogue[].target**: 说话对象。可以是其他角色 char_id 或 "player"
- **dialogue[].subtext**: 这句话的潜台词——角色真正的意思
- **actions**: 伴随对话的肢体动作。由 DialogueWeaver 生成基础版，ActionDirector 会细化
- **emotional_arc**: 情绪弧线，描述对话全程的情绪变化（如 "由警惕逐渐转为好奇"）
- **stance_change**: 可选。如果角色对玩家的态度在对话中发生变化则填写，无变化则为 null

## 注意事项

- 对话应当自然、有呼吸感——不要写成长篇大论
- 角色的性格要体现在措辞和语气中
- 如果有 interaction_context（对手机制），回应对方的话语和情绪
- 如果没有 interaction_context（独立角色），可以是自言自语、观察反应或环境互动
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        interaction: dict = input_data.get("interaction_context", {}) or {}
        beat_summary: str = str(input_data.get("beat_summary", "") or "")
        player_action: str = str(input_data.get("player_action", "") or "")
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))

        lines: list[str] = []

        lines.append("## 场景信息")
        lines.append(f"场景基调: {scene_tone}")
        if beat_summary:
            lines.append(f"节拍摘要: {beat_summary}")
        if player_action:
            lines.append(f"玩家行动: {player_action}")
        lines.append("")

        lines.append("## 当前角色")
        lines.append(f"角色 ID: {character.get('char_id', '')}")
        lines.append(f"名字: {character.get('name', '?')}")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        role = str(character.get("role", "") or "")
        if role:
            lines.append(f"原著定位: {role}")

        # Motivation output
        motivation: dict = character.get("motivation_output", {}) or {}
        if motivation:
            lines.append("")
            lines.append("### 动机分析")
            internal: dict = motivation.get("internal_state", {}) or {}
            lines.append(f"情绪: {internal.get('mood', '?')} (强度: {internal.get('mood_intensity', 0.5):.1f})")
            lines.append(f"主导情绪: {internal.get('dominant_emotion', '?')}")
            lines.append(f"潜台词: {internal.get('subtext', '(无)')}")
            lines.append(f"隐藏意图: {internal.get('hidden_intent', '(无)')}")
            lines.append(f"直接目标: {internal.get('immediate_goal', '(无)')}")

            stance: dict = motivation.get("stance_toward_player", {}) or {}
            if stance:
                lines.append(f"对玩家态度: {stance.get('attitude', '?')} (信任: {stance.get('trust_level', 0.5):.1f})")
                lines.append(f"想对玩家: {stance.get('wants_to', '?')}")

        lines.append("")

        # Interaction context
        if interaction:
            counterpart: dict = interaction.get("counterpart", {}) or {}
            if counterpart:
                lines.append("## 对话对象")
                lines.append(f"正在与 **{counterpart.get('name', '?')}** 对话")
                lines.append(f"对方情绪: {counterpart.get('emotional_tone', '?')}")
                lines.append(f"对方可见目标: {counterpart.get('visible_goal', '?')}")
                lines.append("")
                lines.append(f"请生成 {character.get('name', '?')} 对 {counterpart.get('name', '?')} 的回应对话。要体现角色的性格和真实意图。")
        else:
            lines.append("## 交互模式: 独立")
            lines.append("此角色当前不参与对话交互。可以是对环境的反应、自言自语、或对玩家行动的观察。")
            lines.append("")

        lines.append("输出 JSON。")

        anti_rules: list = character.get("anti_rules", []) or []
        if anti_rules:
            lines.append("")
            lines.append("## 行为禁区（绝对不能违反）")
            for rule in anti_rules:
                lines.append(f"- {rule}")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 编织 {char_name} 的对话...")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.85})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))

        validation = MananaSchema.validate_dialogue_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证失败: {validation.get('errors', [])}")

        dialogue_count = len(data.get("dialogue", []) or [])
        self._log_info(f"→ {char_name}: {dialogue_count} 条对话")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L2R2: ActionDirector
# ============================================================


class ActionDirector(BaseAgent):
    """Layer 2R2 — Action Director (model_tier: light).

    Generates physical gestures, expressions, and micro-expressions per character.
    Uses lightweight model + minimal prompt, outputting only action descriptions.
    """

    agent_name: str = "ActionDirector"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """你是一个动作指导。

只输出角色在当前场景中可能做出的肢体动作和表情变化。

## 输出 JSON 格式

```json
{
  "character_id": "string",
  "actions": [
    {
      "type": "gesture|movement|facial|interaction|posture",
      "description": "简短的动作描述",
      "target": "none|char_id|player|environment",
      "intensity": "subtle|moderate|dramatic"
    }
  ]
}
```

## 动作类型

- **gesture**: 手势/肢体动作（挥手、握拳、摆手）
- **movement**: 位置移动（走近、后退、转身）
- **facial**: 面部表情/微表情（皱眉、嘴角上扬、瞪大眼）
- **interaction**: 与物体/人的互动（推门、递东西、拍肩）
- **posture**: 身体姿态变化（挺直腰背、瘫坐、抱臂）

## 限制

- 只输出 JSON，不要对话，不要心理描写
- actions 数组 1-4 个元素即可
- 动作要符合角色的当前情绪和场景基调
"""

    def build_user_prompt(self, input_data: dict) -> str:
        character: dict = input_data.get("character", {}) or {}
        interaction: dict = input_data.get("interaction_context", {}) or {}
        scene_tone: str = str(input_data.get("scene_tone", "平淡"))
        player_action: str = str(input_data.get("player_action", "") or "")

        lines: list[str] = []

        lines.append(f"场景基调: {scene_tone}")
        lines.append("")

        lines.append("## 角色信息")
        lines.append(f"角色: {character.get('name', '?')} (id: {character.get('char_id', '?')})")

        personality = str(character.get("personality", "") or "")
        if personality:
            lines.append(f"性格: {personality}")

        motivation: dict = character.get("motivation_output", {}) or {}
        if motivation:
            internal: dict = motivation.get("internal_state", {}) or {}
            lines.append(f"情绪: {internal.get('mood', '中性')} (强度: {internal.get('mood_intensity', 0.5):.1f})")
            lines.append(f"直接目标: {internal.get('immediate_goal', '无')}")

        lines.append("")

        if interaction:
            counterpart: dict = interaction.get("counterpart", {}) or {}
            if counterpart:
                lines.append(f"正在与 {counterpart.get('name', '?')} 互动")
                lines.append(f"对方情绪: {counterpart.get('emotional_tone', '?')}")
                lines.append("")

        if player_action:
            lines.append(f"玩家刚刚: {player_action}")
            lines.append("")

        # 角色记忆（记忆系统注入）
        char_mem = character.get("character_memory", "")
        if char_mem:
            lines.append(f"角色经历: {char_mem}")
            lines.append("")

        lines.append("请只输出此角色的动作描述 JSON。不要对话。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        char_name = str((input_data.get("character", {}) or {}).get("name", "?"))
        self._log_info(f"→ 编排 {char_name} 的动作...")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.6, "max_tokens": 512})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        if not data.get("character_id"):
            data["character_id"] = str((input_data.get("character", {}) or {}).get("char_id", ""))

        action_count = len(data.get("actions", []) or [])
        self._log_info(f"→ {char_name}: {action_count} 个动作")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L3: SceneComposer
# ============================================================


class SceneComposer(BaseAgent):
    """Layer 3 — Scene Composer (model_tier: strong).

    Weaves the Director's plan + all Character Engine outputs into final narrative prose.
    Output is plain literary prose followed by a ---JSON--- delimited metadata block.
    """

    JSON_SEPARATOR: str = "---JSON---"

    agent_name: str = "SceneComposer"
    model_tier: str = "strong"

    def build_system_prompt(self) -> str:
        return f"""你是一位小说叙事大师。你的任务是根据导演计划和所有角色的输出，将场景编织为流畅自然的叙事散文。

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
    {{
      "id": "c1",
      "text": "仔细观察周围环境",
      "hint": "了解你身处何方",
      "next_scene_hint": "observe_surroundings"
    }},
    {{
      "id": "c2",
      "text": "检查自己的状态和记忆",
      "hint": "弄清楚你是谁",
      "next_scene_hint": "self_examination"
    }},
    {{
      "id": "c3",
      "text": "向前迈出一步探索",
      "hint": "主动探索未知世界",
      "next_scene_hint": "step_forward"
    }}
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

    def build_user_prompt(self, input_data: dict) -> str:
        director: dict = input_data.get("director_output", {}) or {}
        character_outputs: list = input_data.get("character_outputs", []) or []
        scene_ctx: dict = input_data.get("scene_context_summary", {}) or {}

        lines: list[str] = []

        # Recent narrative — 放在最前面，让 composer 先看到上一拍的结尾，自然接续
        recent: str = str(input_data.get("recent_narrative", "") or "")
        if recent:
            lines.append("## 最近叙事（接续上文——从这里直接继续写下去）")
            lines.append(recent)
            lines.append("")
            lines.append("---")
            lines.append("")

        # Scene context
        lines.append("## 场景信息")
        lines.append(f"当前时间: {scene_ctx.get('game_time', '未知')}")
        lines.append(f"地点: {scene_ctx.get('location_name', '未知')}")
        lines.append(f"氛围: {scene_ctx.get('location_atmosphere', '')}")
        lines.append("")

        # Writing style
        style: dict = scene_ctx.get("writing_style", {}) or {}
        if style:
            lines.append(f"写作风格指引: 语气={style.get('tone', '中性')}, 节奏={style.get('pace', '适中')}, 对话风格={style.get('dialogue_style', '自然')}")
            lines.append("")

        # Player action
        lines.append(f"玩家行动: {scene_ctx.get('player_action', '(无)')}")
        lines.append("")

        # Director plan
        lines.append("## 导演计划")
        lines.append(f"节拍摘要: {director.get('beat_summary', '')}")
        lines.append(f"叙事模式: {director.get('narrative_mode', '')}")
        lines.append(f"场景基调: {director.get('scene_tone', '')}")
        lines.append("")

        # Character outputs
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

        # Refinement hints
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

        content: str = result.get("content", "") or ""

        narrative_only = self._strip_json_suffix(content)
        json_data = self._extract_ending_json(content)

        if json_data:
            validation = MananaSchema.validate_composer_output(json_data)
            if not validation.get("valid", False):
                self._log_warn(f"元数据验证警告: {validation.get('errors', [])}")

        if not narrative_only.strip():
            narrative_only = content
            json_data = {"ending_hook": "", "action_hints": [], "music_mood": "", "choices": []}

        # ── 处理 choices：确保至少有 2 个兜底 ──
        choices = json_data.get("choices", [])
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            from .defaults import get_default_choices
            choices = get_default_choices(2)
        # 淘汰无效 choice（缺少必要字段）
        valid_choices = []
        for c in choices:
            if isinstance(c, dict) and all(k in c for k in ("id", "text", "hint", "next_scene_hint")):
                valid_choices.append(c)
        # 如果有效 choices 少于 2 个，从默认补齐
        if len(valid_choices) < 2:
            from .defaults import get_default_choices
            defaults = get_default_choices(2)
            while len(valid_choices) < 2:
                valid_choices.append(defaults[len(valid_choices)])
        json_data["choices"] = valid_choices[:4]  # 最多 4 个

        self._log_info(f"→ 叙事散文 ({len(narrative_only)} 字符), 钩子: {json_data.get('ending_hook', '')}, choices: {len(json_data.get('choices', []))}")
        log_layer("L3", f"SceneComposer 完成 — {len(narrative_only)} 字符叙事")

        return {"ok": True, "content": narrative_only, "raw": json_data}

    def _extract_ending_json(self, text: str) -> dict:
        """Extract the JSON block after ---JSON--- delimiter."""
        from .utils import _extract_brace_block, _try_parse_json

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
        """Remove ---JSON--- and everything after it."""
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
        """Fallback: try to extract the last JSON object from text end."""
        from .utils import _extract_brace_block, _try_parse_json

        trailing_brace = text.rfind("{")
        if trailing_brace == -1:
            return {}
        candidate = text[trailing_brace:]
        block = _extract_brace_block(candidate)
        if block:
            return _try_parse_json(block)
        return {}


# ============================================================
# L3b: ConsistencyAuditor
# ============================================================


class ConsistencyAuditor(BaseAgent):
    """Layer 3b — Consistency Auditor (model_tier: medium).

    Detects character drift, fact contradictions, rule violations,
    and continuity breaks in Composer-generated narrative text.
    """

    agent_name: str = "ConsistencyAuditor"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事一致性审计师**。你的任务是仔细审查一段叙事文本，检查其中是否存在以下四类问题：

## 检测标准

### 1. 角色漂移 (character_drift)
角色的言行与其设定性格、说话风格、核心恐惧不符。

### 2. 事实矛盾 (fact_contradiction)
叙事文本与已确立的事实冲突。

### 3. 规则违反 (rule_violation)
违反世界规则。

### 4. 连续性断裂 (continuity_break)
与上一段叙事的衔接出现问题。

## 判断标准

- **critical**: 严重破坏叙事可信度，必须修复
- **major**: 明显问题，建议修复
- **minor**: 小瑕疵，可忽略

## 输出 JSON 格式

```json
{
  "verdict": "PASS",
  "issues": [],
  "overall_quality": {
    "character_consistency": 0.85,
    "plot_coherence": 0.90,
    "world_fidelity": 0.95
  },
  "refinement_hints": []
}
```

- **verdict**: "PASS"（通过）、"WARNING"（有轻微问题，需要微调）、"FAIL"（严重问题，需要重写）
- **issues**: 发现的具体问题列表
- **overall_quality**: 各维度质量评分，0.0~1.0
- **refinement_hints**: 对 Composer 的精炼建议列表。每个建议包含：
  - description: 建议修改内容的描述
  - fix_suggestion: 具体的修改方案

如果发现问题，verdict 为 "FAIL" 或 "WARNING"，issues 数组填写具体问题。每个 issue 包含：
- type: "character_drift" | "fact_contradiction" | "rule_violation" | "continuity_break"
- severity: "critical" | "major" | "minor"
- description: 问题的中文描述
- location_hint: 叙事文本中大致位置指引
- fix_suggestion: 修复建议（供后续手动重写参考）

当 verdict 为 "WARNING" 或 "FAIL" 时，必须在 refinement_hints 中提供至少一条具体的修改建议。

## 重要原则

1. **宁可放过，不可误杀**: 当不确定时，倾向给 PASS。
2. **关注角色一致性**: 这是最重要的维度。
3. **不要吹毛求疵**: 文学性的模糊表达和合理的叙事留白不是问题。
"""

    def build_user_prompt(self, input_data: dict) -> str:
        narrative_text: str = str(input_data.get("narrative_text", "") or "")
        personas: dict = input_data.get("character_personas", {}) or {}
        world_rules: str = str(input_data.get("world_rules", "") or "")
        recent_facts: list = input_data.get("recent_facts", []) or []
        previous_narrative: str = str(input_data.get("previous_narrative", "") or "")

        lines: list[str] = []

        lines.append("## 角色设定（参考标准）")
        for char_id, p in personas.items():
            p = p if isinstance(p, dict) else {}
            lines.append(f"### {p.get('name', char_id)} ({char_id})")
            lines.append(f"核心性格: {'、'.join(p.get('core_traits', []) or [])}")
            speech = str(p.get("speech_style", "") or "")
            if speech:
                lines.append(f"说话风格: {speech}")
            fear = str(p.get("core_fear", "") or "")
            if fear:
                lines.append(f"核心恐惧: {fear}")
            facts: list = p.get("known_facts", []) or []
            if facts:
                lines.append(f"已知事实: {'；'.join(facts)}")
            lines.append("")

        if world_rules:
            lines.append("## 世界规则")
            lines.append(world_rules)
            lines.append("")

        if recent_facts:
            lines.append("## 最近已确立的事实")
            for f in recent_facts:
                lines.append(f"- {f}")
            lines.append("")

        if previous_narrative:
            lines.append("## 上段叙事（参考，检测连续性）")
            lines.append(previous_narrative)
            lines.append("")

        lines.append("## 待审计叙事文本")
        lines.append("---")
        lines.append(narrative_text)
        lines.append("---")
        lines.append("")

        lines.append("请审计以上叙事文本，输出 JSON 格式的审计结果。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        narrative_len = len(str(input_data.get("narrative_text", "") or ""))
        self._log_info("→ 审计叙事一致性...")
        log_layer("L3b", f"ConsistencyAuditor 启动 — 叙事长度 {narrative_len} 字符")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.3})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {},
                    "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}

        if "verdict" not in data:
            data["verdict"] = "PASS"
        if "issues" not in data:
            data["issues"] = []
        if "overall_quality" not in data:
            data["overall_quality"] = {"character_consistency": 0.5, "plot_coherence": 0.5, "world_fidelity": 0.5}
        if "refinement_hints" not in data:
            data["refinement_hints"] = []

        validation = MananaSchema.validate_auditor_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证警告: {validation.get('errors', [])}")

        verdict = str(data.get("verdict", "PASS"))
        issues: list = data.get("issues", []) or []

        if verdict in ("FAIL", "WARNING"):
            self._log_warn(f"⚠ 审计 {verdict} — 发现 {len(issues)} 个问题:")
            for issue in issues:
                issue = issue if isinstance(issue, dict) else {}
                sev = issue.get("severity", "major")
                itype = issue.get("type", "unknown")
                desc = issue.get("description", "(无描述)")
                loc = issue.get("location_hint", "")
                self._log_warn(f"  [{sev}] {itype}: {desc} (位置: {loc})")
            log_layer("L3b", f"ConsistencyAuditor {verdict} — {len(issues)} issues, "
                      f"{sum(1 for i in issues if isinstance(i, dict) and i.get('severity') == 'critical')} critical")
        else:
            self._log_info("→ 审计通过 ✓")
            quality: dict = data.get("overall_quality", {}) or {}
            log_layer("L3b", f"ConsistencyAuditor PASS — 角色一致: {quality.get('character_consistency', 0):.2f}, "
                      f"情节连贯: {quality.get('plot_coherence', 0):.2f}, 世界保真: {quality.get('world_fidelity', 0):.2f}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}


# ============================================================
# L4a: StateExtractor
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

### 4. 新知识 (new_knowledge)
- content: 角色在叙事中认识到的新事实/信息
- known_by: 知道此信息的角色 ID 列表

### 5. 新动态 NPC (new_dynamic_npcs)
- 叙事中首次出现的新角色

### 6. 玩家画像更新 (player_profile_updates)
- 正常为 null，每 3-5 拍可输出一次

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
- 每个出场角色的弧光完成度

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
# L4b: ThreadManager
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
- evolved 线索可能衍生出新的 active 线索

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

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        active_count = len(input_data.get("active_threads", []) or [])
        self._log_info(f"→ 管理叙事线索 ({active_count} 活跃)...")
        log_layer("L4b", f"ThreadManager 启动 — {active_count} 活跃线索")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.4})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        self._ensure_defaults(data)

        validation = MananaSchema.validate_thread_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证警告: {validation.get('errors', [])}")

        summary = self._summarize_thread_changes(data)
        self._log_info(f"→ {summary}")
        log_layer("L4b", f"ThreadManager 完成 — {summary}")

        return {"ok": True, "content": result.get("content", ""), "raw": data}

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
# L5: ReflectionOracle
# ============================================================


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

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        beat_count = len(input_data.get("recent_beats_summary", []) or [])
        self._log_info(f"→ 反思评估 ({beat_count} 节拍回顾)...")
        log_layer("L5", f"ReflectionOracle 启动 — {beat_count} 节拍回顾, 偏离度 {input_data.get('divergence_trend', 0.0):.2f}")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.9, "max_tokens": 3072})

        if not result.get("ok", False):
            return {"ok": False, "content": "", "raw": {}, "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "content": result.get("content", ""), "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        self._ensure_defaults(data)

        validation = MananaSchema.validate_oracle_output(data)
        if not validation.get("valid", False):
            self._log_warn(f"输出验证警告: {validation.get('errors', [])}")

        pacing: dict = data.get("pacing_assessment", {}) or {}
        observations: list = data.get("character_observations", []) or []
        thread_health: list = data.get("thread_health", []) or []
        opportunities: list = data.get("narrative_opportunities", []) or []

        self._log_info(f"→ 节奏: {pacing.get('rating', '?')}, 角色观察: {len(observations)}, "
                       f"线索诊断: {len(thread_health)}, 机会: {len(opportunities)}")
        log_layer("L5", f"ReflectionOracle 完成 — 节奏评级: {pacing.get('rating', '?')}, "
                  f"{len(opportunities)} 叙事机会")

        return {"ok": True, "content": result.get("content", ""), "raw": data}

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


# ============================================================
# v4: PlanScorerAgent (Best-of-3)
# ============================================================


class PlanScorerAgent(BaseAgent):
    """v4 P0-2 — Plan Scorer for Best-of-3 Director selection.

    model_tier: light, temperature: 0, max_tokens: 80, json_mode: true.
    """

    agent_name: str = "PlanScorer"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """评估以下节拍计划，输出方向建议 JSON:

{
  "system_health": "healthy|warning|critical",
  "suggestions": [
    {"aspect": "pacing|character|thread|tension",
     "direction": "加快节奏|聚焦某角色|推进某线索|放松",
     "reason": "详细说明"}
  ],
  "scores": {
    "thread_progress": int (1-5),
    "character_naturalness": int (1-5),
    "causal_link": int (1-5),
    "total": int (3-15)
  }
}

- system_health: 整体叙事健康度
  - healthy: 一切正常
  - warning: 可能出现问题，建议关注
  - critical: 需要立即调整
- suggestions: 方向建议列表（0~3条），包含具体方面、建议方向和理由
- scores: 内部参考评分，保留原有 three-dimension 评分体系
"""

    def build_user_prompt(self, input_data: dict) -> str:
        # PlanScorer receives the beat plan directly as input_data
        return "评估以下节拍计划：\n" + json.dumps(input_data, ensure_ascii=False, indent=2)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        result = await self._call_llm(sys, usr, {"temperature": 0.0, "max_tokens": 120, "json_mode": True})

        parsed = self._parse_json_response(result)
        if not parsed.get("ok", False):
            return {"ok": False, "error": str(parsed.get("error", "scorer parse failed")), "raw": input_data}

        data: dict = parsed.get("data", {}) or {}
        scores: dict = data.get("scores", {}) or {}
        return {
            "ok": True,
            "total": int(scores.get("total", data.get("total", 0))),
            "scores": {
                "thread_progress": int(scores.get("thread_progress", 0)),
                "character_naturalness": int(scores.get("character_naturalness", 0)),
                "causal_link": int(scores.get("causal_link", 0)),
            },
            "system_health": str(data.get("system_health", "healthy")),
            "suggestions": list(data.get("suggestions", []) or []),
            "raw": input_data,
        }


# ============================================================
# v4: PlanSynthesizerAgent (Multi-View)
# ============================================================


class PlanSynthesizerAgent(BaseAgent):
    """v4 P1-3 — Multi-View Synthesizer.

    Fuses plot-driven and character-driven beat plans into a single plan.
    model_tier: medium, temperature: 0.4, max_tokens: 1024, json_mode: true.
    """

    agent_name: str = "PlanSynthesizer"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """融合两个节拍方案为单一方案，输出标准 beat_plan JSON。

你是一个叙事计划合成器。你会收到两个视角的节拍方案：
1. 剧情驱动视角 (plot-driven) — 从剧情线索推进角度出发
2. 角色驱动视角 (character-driven) — 从角色发展和互动角度出发

你需要融合两个方案的优点，输出一个单一的、连贯的节拍计划 JSON。
输出格式与标准 SceneDirector 输出完全一致。"""

    def build_user_prompt(self, input_data: dict) -> str:
        plot_plan: dict = input_data.get("plot_plan", {}) or {}
        char_plan: dict = input_data.get("character_plan", {}) or {}
        scene_context: dict = input_data.get("scene_context", {}) or {}

        return (
            "场景上下文:\n" + json.dumps(scene_context, ensure_ascii=False, indent=2) +
            "\n\n剧情视角方案:\n" + json.dumps(plot_plan, ensure_ascii=False, indent=2) +
            "\n\n角色视角方案:\n" + json.dumps(char_plan, ensure_ascii=False, indent=2)
        )

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        result = await self._call_llm(sys, usr, {"temperature": 0.4, "max_tokens": 1024, "json_mode": True})

        parsed = self._parse_json_response(result)
        if not parsed.get("ok", False):
            # Degrade: pick non-empty plan
            char_plan = input_data.get("character_plan", {}) or {}
            plot_plan = input_data.get("plot_plan", {}) or {}
            fallback = char_plan if char_plan else plot_plan
            return {"ok": True, "raw": fallback}

        return {"ok": True, "raw": parsed.get("data", {}) or {}}


# ============================================================
# v4: MicroOracleAgent
# ============================================================


# ============================================================
# L1b: ContinuityChecker
# ============================================================


class ContinuityChecker(BaseAgent):
    """L1b — 连续叙事审计 (model_tier: medium).

    审计 L1 Director 的 beat plan 是否与历史合理推演一致。
    玩家要求的优先级低于合理性推演。
    """

    agent_name: str = "ContinuityChecker"
    model_tier: str = "medium"

    def build_system_prompt(self) -> str:
        return """你是一位**叙事连续性审计师**。你的任务是审查导演的节拍计划是否与历史合理推演一致。

## 审计原则

1. **历史优先**: 叙事必须延续上一拍的历史上下文，不能跳跃
2. **玩家权限低于逻辑**: 即使玩家提出了要求，如果与历史的合理推演冲突，系统有权拒绝
3. **合理性 > 趣味性**: 好故事首先是自洽的，然后才是有趣的

## 三种判决

### APPROVED（通过）
- 节拍计划与历史合理推演一致
- 角色行为符合其性格和状态
- 叙事方向合理延续

### REJECTED（打回）
- 节拍计划与历史严重冲突
- 角色行为完全违背其性格或前一拍的状态
- 玩家要求与合理推演矛盾且 plan 照单全收

### NEEDS_TRANSITION（需过渡）
- 节拍计划本身合理但有较大的方向变化
- 需要 L2 生成过渡内容来衔接

## 输出 JSON 格式

```json
{
  "verdict": "APPROVED|REJECTED|NEEDS_TRANSITION",
  "reason": "判决原因的中文描述",
  "conflict_details": [
    {
      "expected": "根据历史合理推演应发生什么",
      "but_plan_says": "计划中写了什么",
      "suggestion": "建议如何修正"
    }
  ]
}
```

## 重要原则

1. **宁放过不误杀**: 不确定时给 APPROVED
2. **具体可操作**: REJECTED 时必须给出明确的冲突原因和修正建议
3. **关注核心**: 重点关注角色行为一致性和情节连贯性
"""

    def build_user_prompt(self, input_data: dict) -> str:
        player_action: str = str(input_data.get("player_action", "") or "")
        history_summary: str = str(input_data.get("history_summary", "") or "")
        character_states: dict = input_data.get("character_states", {}) or {}
        beat_plan: dict = input_data.get("beat_plan", {}) or {}
        narrative_threads: list = input_data.get("narrative_threads", []) or []

        lines: list[str] = []

        lines.append("## 玩家行动")
        lines.append(player_action if player_action else "(无)")
        lines.append("")

        lines.append("## 历史叙事摘要")
        lines.append(history_summary if history_summary else "(无)")
        lines.append("")

        if character_states:
            lines.append("## 关键角色当前状态")
            for char_id, state in character_states.items():
                state = state if isinstance(state, dict) else {}
                parts = [f"位置: {state.get('location', '?')}",
                         f"情绪: {state.get('mood', '?')}"]
                wearing = state.get("wearing", "")
                if wearing:
                    parts.append(f"衣着: {wearing}")
                holding = state.get("holding", "")
                if holding:
                    parts.append(f"持有: {holding}")
                lines.append(f"- {char_id}: {', '.join(parts)}")
            lines.append("")

        if narrative_threads:
            lines.append("## 活跃叙事线索")
            for t in narrative_threads:
                t = t if isinstance(t, dict) else {}
                lines.append(f"- [{t.get('id', '?')}] {t.get('title', '?')}")
            lines.append("")

        lines.append("## 待审计的节拍计划")
        lines.append(json.dumps(beat_plan, ensure_ascii=False, indent=2))
        lines.append("")
        lines.append("请审计以上节拍计划是否与历史合理推演一致。输出 JSON。")

        return "\n".join(lines)

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        self._log_info("→ 审计剧本连续性...")
        log_layer("L1b", "ContinuityChecker 启动")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.3})

        if not result.get("ok", False):
            return {"ok": False, "verdict": "APPROVED", "raw": {},
                    "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "verdict": "APPROVED", "raw": {},
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        verdict = str(data.get("verdict", "APPROVED"))
        reason = str(data.get("reason", ""))
        conflicts = data.get("conflict_details", []) or []

        if verdict == "REJECTED":
            self._log_warn(f"⚠ 连续性审计 REJECTED: {reason}")
        elif verdict == "NEEDS_TRANSITION":
            self._log_info(f"→ 连续性审计 NEEDS_TRANSITION: {reason}")
        else:
            self._log_info("→ 连续性审计通过 ✓")
        log_layer("L1b", f"ContinuityChecker {verdict} — {len(conflicts)} 冲突点")

        return {"ok": True, "verdict": verdict, "reason": reason,
                "conflict_details": conflicts, "raw": data}


# ============================================================
# L2R3: RoleReflector
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

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        pending_count = len(input_data.get("pending_emergences", {}) or {})
        self._log_info(f"→ 扫描角色涌现 ({pending_count} 待判定)...")
        log_layer("L3b", "CharacterManager 启动")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.3, "max_tokens": 2048})

        if not result.get("ok", False):
            return {"ok": False, "detected_emergences": [], "readiness_results": [],
                    "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "detected_emergences": [], "readiness_results": [],
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        detected: list = data.get("detected_emergences", []) or []
        readiness: list = data.get("readiness_results", []) or []

        if detected:
            names = [d.get("name", "?") for d in detected]
            self._log_info(f"→ 发现新角色: {', '.join(names)}")
        if readiness:
            ready_names = [r.get("name", "?") for r in readiness if r.get("readiness") == "READY"]
            if ready_names:
                self._log_info(f"→ 准备就绪: {', '.join(ready_names)}")
        log_layer("L3b", f"CharacterManager 完成 — 检测{len(detected)}新, {len(readiness)}判定")

        return {"ok": True, "detected_emergences": detected,
                "readiness_results": readiness, "raw": data}


# ============================================================
# L3b: LocationManager (涌现建议 — 地点检测)
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

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        pending_count = len(input_data.get("pending_emergences", {}) or {})
        self._log_info(f"→ 扫描地点涌现 ({pending_count} 待判定)...")
        log_layer("L3b", "LocationManager 启动")

        result = await self._call_llm(sys, usr, {"json_mode": True, "temperature": 0.3, "max_tokens": 2048})

        if not result.get("ok", False):
            return {"ok": False, "detected_emergences": [], "readiness_results": [],
                    "error": result.get("error", "LLM call failed")}

        parsed = self._parse_json_response(result)
        if parsed.get("error", ""):
            return {"ok": False, "detected_emergences": [], "readiness_results": [],
                    "error": "JSON parse failed: " + str(parsed.get("error", ""))}

        data: dict = parsed.get("data", {}) or {}
        detected: list = data.get("detected_emergences", []) or []
        readiness: list = data.get("readiness_results", []) or []

        if detected:
            names = [d.get("name", "?") for d in detected]
            self._log_info(f"→ 发现新地点: {', '.join(names)}")
        if readiness:
            ready_names = [r.get("name", "?") for r in readiness if r.get("readiness") == "READY"]
            if ready_names:
                self._log_info(f"→ 准备就绪: {', '.join(ready_names)}")
        log_layer("L3b", f"LocationManager 完成 — 检测{len(detected)}新, {len(readiness)}判定")

        return {"ok": True, "detected_emergences": detected,
                "readiness_results": readiness, "raw": data}


# ============================================================
# v4: MicroOracleAgent
# ============================================================


class MicroOracleAgent(BaseAgent):
    """v4 P1-1 — Micro-Oracle quality feedback at end of each beat.

    model_tier: light, temperature: 0, max_tokens: 80, json_mode: true.
    """

    agent_name: str = "MicroOracle"
    model_tier: str = "light"

    def build_system_prompt(self) -> str:
        return """评估上一拍的叙事质量，输出方向建议 JSON:

{
  "system_health": "healthy|warning|critical",
  "suggestions": [
    {"aspect": "pacing|character|thread|tension|adherence",
     "direction": "加速|减速|聚焦|放松",
     "reason": "详细说明"}
  ],
  "one_line_feedback": "一句话反馈摘要"
}

- system_health: 叙事健康度
  - healthy: 一切正常
  - warning: 略微失衡，建议关注
  - critical: 需要立即调整方向
- suggestions: 具体方向建议（0~3条）
  - aspect: 关注的方面
  - direction: 建议方向
  - reason: 详细理由
- one_line_feedback: 简明反馈摘要，给下一拍的导演参考
"""

    def build_user_prompt(self, input_data: dict) -> str:
        return "上一拍摘要:\n" + str(input_data.get("narrative_summary", ""))

    async def run(self, input_data: dict) -> dict:
        sys = str(input_data.get("system_prompt", "") or "") or self.build_system_prompt()
        usr = self.build_user_prompt(input_data)

        result = await self._call_llm(sys, usr, {"temperature": 0.0, "max_tokens": 120, "json_mode": True})

        parsed = self._parse_json_response(result)
        if not parsed.get("ok", False):
            return {
                "has_issue": False,
                "one_line_feedback": "",
                "severity": "info",
                "system_health": "healthy",
                "suggestions": [],
            }

        data: dict = parsed.get("data", {}) or {}
        return {
            # 旧字段（向后兼容）
            "has_issue": bool(data.get("has_issue", data.get("system_health") == "critical")),
            "one_line_feedback": str(data.get("one_line_feedback", "")),
            "severity": str(data.get("severity",
                "alert" if data.get("system_health") == "critical"
                else "warning" if data.get("system_health") == "warning"
                else "info")),
            # 新字段
            "system_health": str(data.get("system_health", "healthy")),
            "suggestions": list(data.get("suggestions", []) or []),
        }
