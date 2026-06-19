# MaNA v4 增强方案 PRD

> **产品经理**: 许清楚 | **日期**: 2026-06-19 | **状态**: 已确认

---

## 1. 产品目标

### 1.1 核心目标
提升 MaNA v4 叙事引擎的故事真实性和连贯性，解决当前三个核心问题：

1. **幻觉即错误**：LLM 产生的幻觉角色/地点被 Auditor 当作错误抹除，浪费了创意的可能性
2. **叙事断档**：剧本不记住上一拍的历史上下文，导致合理推演断裂，玩家要求与历史逻辑冲突时无法拒绝
3. **角色跳跃**：角色表演出现状态矛盾（如服装、位置突然变化），缺乏过渡描述

### 1.2 设计理念
- **拥抱幻觉**：将随机幻觉转化为"世界自然涌现"，经过多次确认后正式化
- **延续优先**：历史合理推演的优先级高于玩家即时要求
- **过渡真实**：状态变化需要过渡，而非跳跃

---

## 2. 用户故事

### 改动一：涌现建议
- **作为玩家**，我希望叙事中多次提到的神秘人物/地点最终正式登场，感觉是世界的自然铺垫而非随机错误
- **作为玩家**，我能在角色栏/地点栏看到经过"酝酿"后正式出现的新实体

### 改动二：连续叙事
- **作为玩家**，我希望我的行为决策影响世界时遵循历史和逻辑，即使我的输入不合理
- **作为玩家**，当我提出与当前局势冲突的要求时，系统能给出合乎逻辑的回应而非直接执行

### 改动三：过渡反思
- **作为玩家**，我不希望看到角色在尴尬的"上一秒脱衣，下一秒穿衣"式跳跃
- **作为玩家**，我希望所有状态变化都有合理的过渡描述

---

## 3. 需求池

### P0（必须实现）

| ID | 需求 | 改动归属 | 说明 |
|----|------|---------|------|
| P0-1 | CharacterManager Agent | 改动一 | 扫描叙事文本检测新角色，暂存 pending_emergences |
| P0-2 | LocationManager Agent | 改动一 | 扫描叙事文本检测新地点，暂存 pending_emergences |
| P0-3 | ContinuityChecker Agent | 改动二 | 审计 L1 剧本合规性，支持三种判决 |
| P0-4 | RoleReflector Agent | 改动三 | 逐角色审计表演状态跳跃，生成过渡 |
| P0-5 | pending_emergences 数据结构 | 改动一 | 在 WorldState 中新增建议队列管理 |

### P1（重要）

| ID | 需求 | 改动归属 | 说明 |
|----|------|---------|------|
| P1-1 | LLM 判定+生成合并 | 改动一 | 一次调用完成 readiness 判定+JSON 档案生成 |
| P1-2 | 语义合并机制 | 改动一 | 相似实体合并（特征向量/LLM 提取） |
| P1-3 | Auditor 交互 | 改动一 | Auditor 感知实体状态，抑制对应的误报 |
| P1-4 | L1→ContinuityChecker 反馈回路 | 改动二 | 打回重做机制 |
| P1-5 | L2R2→RoleReflector 反馈回路 | 改动三 | 重做/附加过渡机制 |
| P1-6 | 配置参数新增 | 全部 | config.yaml 新增 emergence/continuity/reflection 配置段 |

### P2（锦上添花）

| ID | 需求 | 改动归属 | 说明 |
|----|------|---------|------|
| P2-1 | 采纳实体注入 ContextBuilder | 改动一 | 下一拍自然出现 |
| P2-2 | 前端不显示 pending 实体 | 改动一 | 仅内部保存数据 |
| P2-3 | max_rewrite 上限保护 | 改动二 | 避免无限重做 |
| P2-4 | 多维度跳跃检测可配置 | 改动三 | 服装/位置/情绪/关系可独立开关 |

---

## 4. 功能描述

### 4.1 改动一：涌现建议系统

**新增 Agent**：
- `CharacterManager` — 检测叙事中不在 Canon 的新角色名
- `LocationManager` — 检测叙事中不在 Canon 的新地名

**机制流程**：

```
每拍 narrative_text
  → CharMgr/LocMgr 扫描
  → 发现新实体 → 存入 pending_emergences（内部暂存，不显示在 UI）
  → 下次类似实体 → 语义合并，追加 mention_samples, hit\_count++
  → 条件触发 LLM（light tier）做一次判定：
     输入：pending entity 的累计文本
     输出：{ readiness: "READY|ACCUMULATING|VAGUE", profile?: {...} }
  → READY → 生成完整 JSON 档案（沿用 Canon 格式）
  → 移入 dynamic_npcs / dynamic_locations
  → 下一拍 ContextBuilder 自然包含

合并策略：特征相似 > 阈值（可配置）→ 合并为同一实体，hit 累加
采纳阈值：hit_count ≥ threshold（默认 3，可配置）
```

### 4.2 改动二：连续叙事审计（ContinuityChecker — L1b）

**位置**：L1 Director → **L1b ContinuityChecker** → L2R1

**职责**：审计 Director 的 plan 是否与历史合理推演一致

**输入**：
```json
{
  "player_action": "玩家输入",
  "history_summary": "历史叙事摘要",
  "character_states": { "关键角色当前状态" },
  "beat_plan": "L1 Director 的编排计划",
  "narrative_threads": ["活跃线索"]
}
```

**输出**：
```json
{
  "verdict": "APPROVED | REJECTED | NEEDS_TRANSITION",
  "reason": "判决原因",
  "conflict_details": [{ "expected": "...", "but_plan_says": "..." }]
}
```

**流程**：
- APPROVED → 直接到 L2R1
- REJECTED → plan + rejection → L1 重做（上限 2 次）
- NEEDS_TRANSITION → 注入过渡约束

### 4.3 改动三：角色过渡反思（RoleReflector — L2R3）

**位置**：L2R2 → **L2R3 RoleReflector** → L3

**职责**：逐角色审计表演动作是否存在跳跃

**输入**：
```json
{
  "character_performances": [{ "char_id", "dialogue", "action", "mood", "target" }],
  "previous_states": { "char_id": { "location", "wearing", "mood", "relationships" } },
  "beat_plan": "编排上下文"
}
```

**输出**（逐角色）：
```json
{
  "verdict": "PASS | NEED_TRANSITION | NEED_REWRITE",
  "issues": [{ "type": "clothing_mismatch|location_jump|mood_break|relationship_break" }],
  "transition_dialogue": "过渡对白",
  "transition_action": "过渡动作"
}
```

---

## 5. 验收标准

| # | 验收条件 | 关联需求 |
|---|---------|---------|
| 1 | 新角色在叙事中出现 ≥3 次后，能在 dynamic_npcs 中找到对应 JSON 档案 | P0-1, P0-5 |
| 2 | 新地点同理，在 dynamic_locations 中出现 | P0-2 |
| 3 | ContinuityChecker 能正确识别与历史冲突的 plan 并打回 | P0-3 |
| 4 | RoleReflector 能检测到服装/位置矛盾并生成过渡文本 | P0-4, P1-5 |
| 5 | 所有 Agent 可通过 config.yaml 开关控制 | P1-6 |
| 6 | 所有反馈回路有上限保护，不会无限循环 | P2-3 |

---

## 6. 待确认问题

- 无（全部已与架构师/用户讨论确认）

---

*PRD 编制: 许清楚 | 确认: 齐活林*
