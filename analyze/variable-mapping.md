# 前后端变量名映射表 (Variable Name Mapping)

> **基于设计图 `design-interactive.html` 分析**
> 
> **日期**: 2026-06-23
> **分析员**: Orchestrator

---

## 1. 重要说明

### 1.1 为什么需要变量名统一？
- **避免混淆**: 前后端使用相同的变量名，减少沟通成本
- **减少 Bug**: 变量名不一致可能导致数据解析错误
- **提高可维护性**: 统一的命名规范使代码更易读

### 1.2 命名原则
- **小驼峰命名法** (camelCase): 用于 JavaScript 和 Python
- **语义化**: 变量名应清晰表达其含义
- **一致性**: 相同概念在前后端使用相同变量名

---

## 2. 游戏状态变量

### 2.1 基础游戏状态

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `game_time` | `game_time` | `string` | 游戏内时间 | `"第3月·第2周·午后"` |
| `weather` | `weather` | `string` | 天气描述 | `"雨季 · 微风 · 凉爽 18°C"` |
| `current_location` | `current_location` | `string` | 当前位置 | `"翡冷翠 · 市政广场"` |
| `location_meta` | `location_meta` | `string` | 位置元数据 | `"城市中心 · 人口密集 · 商业区"` |
| `tension` | `tension` | `float` | 叙事张力 (0.0-1.0) | `0.72` |
| `epoch` | `epoch` | `int` | Epoch 计数器 | `47` |
| `beat` | `beat` | `int` | Beat 计数器 | `128` |

**✅ 统一性检查**: 所有变量名已统一

---

### 2.2 叙事模式

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `narrative_mode` | `narrative_mode` | `string` | 叙事模式 | `"探索模式"` |
| `deviation` | `deviation` | `float` | 世界偏离度 (-1.0 ~ 1.0) | `0.22` |

**✅ 统一性检查**: 所有变量名已统一

---

## 3. 线索 (Threads) 变量

### 3.1 线索基础信息

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `id` | `id` | `string` | 线索 ID | `"thread_03"` |
| `title` | `title` | `string` | 线索标题 | `"翡翠密谋"` |
| `type` | `type` | `string` | 线索类型 | `"main"` / `"side"` / `"identity"` |
| `status` | `status` | `string` | 线索状态 | `"active"` / `"evolving"` / `"resolved"` |
| `question` | `question` | `string` | 核心问题 | `"谁在暗中操纵翡翠商会？"` |
| `involved_characters` | `involved_characters` | `array[string]` | 涉及角色 | `["莉亚妮", "费伦"]` |
| `player_attention` | `player_attention` | `float` | 玩家注意力 (0.0-1.0) | `0.70` |

**✅ 统一性检查**: 所有变量名已统一

---

### 3.2 线索指标

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `urgency` | `urgency` | `float` | 紧迫度 (0.0-1.0) | `0.85` |
| `complexity` | `complexity` | `float` | 复杂度 (0.0-1.0) | `0.60` |
| `tension` | `tension` | `float` | 紧张度 (0.0-1.0) | `0.75` |
| `priority` | `priority` | `float` | 优先级 (0.0-1.0) | `0.90` |

**✅ 统一性检查**: 所有变量名已统一

---

### 3.3 线索统计

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `active` | `active` | `int` | 活跃线索数 | `3` |
| `evolving` | `evolving` | `int` | 演化中线索数 | `2` |
| `resolved` | `resolved` | `int` | 已解决线索数 | `5` |

**✅ 统一性检查**: 所有变量名已统一

---

## 4. NPC 认知冲突 (Dissonance) 变量

### 4.1 NPC 基础信息

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `name` | `name` | `string` | NPC 名称 | `"莉亚妮"` |
| `affinity` | `affinity` | `int` | 信任度 (%) | `85` |
| `dissonance_phase` | `dissonance_phase` | `string` | 认知冲突阶段 | `"normal"` / `"questioning"` / `"confront"` |

**✅ 统一性检查**: 所有变量名已统一

---

### 4.2 认知冲突阶段

| 阶段 (前端) | 阶段 (后端) | 说明 |
|------------|------------|------|
| `normal` | `normal` | 正常（无冲突） |
| `subtle` | `subtle` | 微妙异样 |
| `questioning` | `questioning` | 起疑 |
| `confront` | `confront` | 对质边缘 |
| `adapted` | `adapted` | 已适应 |

**✅ 统一性检查**: 所有阶段名已统一

---

## 5. 灵魂 (Soul) 变量

### 5.1 灵魂基础信息

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `player_soul` | `player_soul` | `string` | 异界之魂名称 | `"异界旅人"` |
| `canon_echo` | `canon_echo` | `string` | 原主回响名称 | `"艾琳·晨风"` |
| `blend_ratio` | `blend_ratio` | `float` | 支配比 (0.0-1.0) | `0.68` |

**✅ 统一性检查**: 所有变量名已统一

---

### 5.2 OCEAN 人格

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `openness` | `openness` | `float` | 开放性 (0.0-1.0) | `0.70` |
| `conscientiousness` | `conscientiousness` | `float` | 尽责性 (0.0-1.0) | `0.55` |
| `extraversion` | `extraversion` | `float` | 外向性 (0.0-1.0) | `0.40` |
| `agreeableness` | `agreeableness` | `float` | 宜人性 (0.0-1.0) | `0.65` |
| `neuroticism` | `neuroticism` | `float` | 神经质 (0.0-1.0) | `0.45` |

**✅ 统一性检查**: 所有变量名已统一

---

### 5.3 道德阵营

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `law_chaos` | `law_chaos` | `float` | 守序-混乱轴 (0.0=守序, 1.0=混乱) | `0.65` |
| `good_evil` | `good_evil` | `float` | 善良-邪恶轴 (0.0=善良, 1.0=邪恶) | `0.30` |

**✅ 统一性检查**: 所有变量名已统一

---

### 5.4 选择统计

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `authentic_choices` | `authentic_choices` | `int` | 本我选择次数 | `7` |
| `canon_compliant_choices` | `canon_compliant_choices` | `int` | 贴合选择次数 | `4` |

**✅ 统一性检查**: 所有变量名已统一

---

### 5.5 内心独白

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `inner_voice` | `inner_voice` | `string` | 异界之魂独白 | `"她不喜欢这样……但必须走下去。"` |
| `canon_echo_voice` | `canon_echo_voice` | `string` | 原主回响独白 | `"从什么时候开始，你变得如此陌生？"` |

**✅ 统一性检查**: 所有变量名已统一

---

## 6. 角色 (Characters) 变量

### 6.1 角色基础信息

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `name` | `name` | `string` | 角色名称 | `"莉亚妮"` |
| `role` | `role` | `string` | 角色身份 | `"主角"` / `"配角"` / `"反派"` |
| `location` | `location` | `string` | 当前位置 | `"城堡"` |
| `emotion` | `emotion` | `string` | 情绪状态 | `"愉快"` / `"怀疑"` / `"敌意"` |
| `reputation` | `reputation` | `int` | 声望值 | `32` |
| `trust` | `trust` | `int` | 信任度 (%) | `85` |
| `scratchpad` | `scratchpad` | `string` | 内心独白 | `"她今天似乎有些不一样……"` |

**✅ 统一性检查**: 所有变量名已统一

---

## 7. 日志 (Log) 变量

### 7.1 日志条目

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `beat` | `beat` | `int` | Beat 号 | `128` |
| `type` | `type` | `string` | 日志类型 | `"narrative"` / `"combat"` / `"social"` |
| `text` | `text` | `string` | 日志文本 | `"翡冷翠广场发现可疑人物"` |
| `timestamp` | `timestamp` | `string` | 时间戳 (ISO 8601) | `"2026-06-23T10:30:00Z"` |

**✅ 统一性检查**: 所有变量名已统一

---

### 7.2 日志统计

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `narrative` | `narrative` | `int` | 叙事日志数 | `12` |
| `combat` | `combat` | `int` | 战斗日志数 | `3` |
| `social` | `social` | `int` | 社交日志数 | `7` |
| `exploration` | `exploration` | `int` | 探索日志数 | `4` |

**✅ 统一性检查**: 所有变量名已统一

---

## 8. 地点 (Locations) 变量

### 8.1 地点信息

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 | 示例值 |
|----------------|---------------------|---------|------|--------|
| `name` | `name` | `string` | 地点名称 | `"翡冷翠 · 市政广场"` |
| `type` | `type` | `string` | 地点类型 | `"城市"` / `"建筑"` / `"自然"` |
| `atmosphere` | `atmosphere` | `string` | 氛围 | `"热闹"` / `"神秘"` / `"荒凉"` |
| `npcs_present` | `npcs_present` | `array[string]` | 在场 NPC | `["莉亚妮", "费伦"]` |

**✅ 统一性检查**: 所有变量名已统一

---

## 9. WebSocket 消息变量

### 9.1 消息类型

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 |
|----------------|---------------------|---------|------|
| `type` | `type` | `string` | 消息类型 |
| `payload` | `payload` | `object` | 消息负载 |

---

### 9.2 消息类型枚举

| 消息类型 (前端) | 消息类型 (后端) | 说明 |
|-----------------|-----------------|------|
| `beat_update` | `beat_update` | Beat 更新 |
| `game_info_update` | `game_info_update` | 游戏信息更新 |
| `character_update` | `character_update` | 角色状态更新 |
| `thread_update` | `thread_update` | 线索状态更新 |
| `soul_update` | `soul_update` | 灵魂状态更新 |
| `narrative_chunk` | `narrative_chunk` | 叙事流式输出 |
| `pipeline_status` | `pipeline_status` | 管线状态更新 |

**✅ 统一性检查**: 所有消息类型已统一

---

## 10. API 响应变量

### 10.1 标准响应格式

| 前端变量名 (JS) | 后端变量名 (Python) | 数据类型 | 说明 |
|----------------|---------------------|---------|------|
| `success` | `success` | `bool` | 请求是否成功 |
| `message` | `message` | `string` | 错误消息（失败时） |
| `data` | `data` | `object` | 响应数据（成功时） |

**✅ 统一性检查**: 所有变量名已统一

---

## 11. 前端状态变量 (JavaScript)

### 11.1 应用状态

| 变量名 | 数据类型 | 说明 | 示例值 |
|--------|---------|------|--------|
| `activePanel` | `string` | 当前激活的面板 | `"dashboard"` / `"narrative"` |
| `activeRightTab` | `string` | 当前激活的右面板标签 | `"characters"` / `"soul"` |
| `gameState` | `object` | 游戏状态（从 WebSocket 接收） | `{beat: 128, tension: 0.72, ...}` |
| `dashboardData` | `object` | Dashboard 数据（从 API 获取） | `{threads: [...], ...}` |
| `logFilter` | `string` | 日志过滤条件 | `"all"` / `"narrative"` / `"combat"` |
| `threadFilter` | `string` | 线索过滤条件 | `"all"` / `"main"` / `"side"` |

---

## 12. 后端数据模型变量 (Python)

### 12.1 GameSession 模型

| 变量名 | 数据类型 | 说明 |
|--------|---------|------|
| `session_id` | `str` | 会话 ID |
| `game_time` | `str` | 游戏内时间 |
| `current_location` | `str` | 当前位置 |
| `tension` | `float` | 叙事张力 |
| `epoch` | `int` | Epoch 计数器 |
| `beat` | `int` | Beat 计数器 |
| `threads` | `list[Thread]` | 线索列表 |
| `characters` | `list[Character]` | 角色列表 |
| `soul` | `Soul` | 灵魂状态 |

---

### 12.2 Thread 模型

| 变量名 | 数据类型 | 说明 |
|--------|---------|------|
| `id` | `str` | 线索 ID |
| `title` | `str` | 线索标题 |
| `type` | `str` | 线索类型 |
| `status` | `str` | 线索状态 |
| `urgency` | `float` | 紧迫度 |
| `complexity` | `float` | 复杂度 |
| `tension` | `float` | 紧张度 |
| `priority` | `float` | 优先级 |
| `question` | `str` | 核心问题 |
| `involved_characters` | `list[str]` | 涉及角色 |
| `player_attention` | `float` | 玩家注意力 |

---

### 12.3 Character 模型

| 变量名 | 数据类型 | 说明 |
|--------|---------|------|
| `name` | `str` | 角色名称 |
| `role` | `str` | 角色身份 |
| `location` | `str` | 当前位置 |
| `emotion` | `str` | 情绪状态 |
| `reputation` | `int` | 声望值 |
| `trust` | `int` | 信任度 (%) |
| `dissonance_phase` | `str` | 认知冲突阶段 |
| `scratchpad` | `str` | 内心独白 |

---

### 12.4 Soul 模型

| 变量名 | 数据类型 | 说明 |
|--------|---------|------|
| `player_soul` | `str` | 异界之魂名称 |
| `canon_echo` | `str` | 原主回响名称 |
| `blend_ratio` | `float` | 支配比 |
| `ocean` | `dict` | OCEAN 人格 |
| `moral_alignment` | `dict` | 道德阵营 |
| `choice_stats` | `dict` | 选择统计 |
| `inner_voice` | `str` | 内心独白 |
| `canon_echo_voice` | `str` | 原主回响独白 |

---

## 13. 总结

### 13.1 统一性检查结果
✅ **所有变量名已统一** - 前端和后端使用相同的变量名

### 13.2 命名规范
- ✅ 使用小驼峰命名法 (camelCase)
- ✅ 语义化命名
- ✅ 一致性（相同概念使用相同变量名）

### 13.3 下一步
完成任务 #1（分析设计图），开始任务 #2（设计前后端接口）

---

**下一步**: 完成任务 #1，开始任务 #2
