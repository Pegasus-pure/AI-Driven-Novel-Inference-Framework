# Round — AI 驱动小说推演框架

<div align="center">

[![CN](https://img.shields.io/badge/简体中文-README-red)](README.md) [![EN](https://img.shields.io/badge/English-README-blue)](README_EN.md)

**通用 AI 小说推演框架 — 导入完结小说，AI 驱动动态叙事**

[![Godot](https://img.shields.io/badge/Godot-4.6-%23478cbf?style=flat&logo=godot-engine)](https://godotengine.org)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20%2F%20DeepSeek%20%2F%20OpenAI-orange)]()
[![MCP](https://img.shields.io/badge/MCP-38%20Tools-green)]()
[![MaNA](https://img.shields.io/badge/MaNA-v4-blue)]()

</div>

---

## 项目简介

**Round** 是一款基于 Godot 4.x 打造的 AI 驱动小说推演框架。

玩家可导入任意完结小说，系统通过 LLM 自动抽取世界观、角色与剧情脉络，玩家则以"穿越路人"身份沉浸式体验故事——既能重温原著经典桥段，也能通过选择偏离主线、探索未知支线。

项目受米哈游《Varsapura》（雨之城）启发，面向"重温者"与"发现者"双类受众。

### 核心体验

- **导入即玩**：放入完结小说文本，AI 自动解析世界观、角色、剧情
- **路人视角**：玩家扮演原著名不见经传的路人，体验"原著观察者"的独特视角
- **动态叙事**：MaNA v4 多 Agent 叙事引擎，支持 Best-of-3 采样、迭代精炼、多视角融合
- **偏离系统**：世界偏离度追踪玩家行为与原著的差距，5 级偏离度对应不同叙事策略
- **向量记忆**：基于 Ollama Embedding 的语义记忆检索，让叙事具备长期连贯性
- **终端风格 UI**：复古终端界面，沉浸式文字冒险体验

---

## 技术架构

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 游戏引擎 | Godot 4.6 | 终端风格 UI，场景系统 |
| 叙事引擎 | MaNA v4（多 Agent LLM 管线） | 5 层流水线 + v4 增强功能 |
| LLM 接入 | Provider 抽象层 | 统一 Ollama / DeepSeek / OpenAI 接口 |
| 向量记忆 | Ollama Embedding（qwen3-embedding:0.6b） | 语义存储与检索 |
| 通信协议 | MCP（Model Context Protocol） | Godot Bridge MCP，38 个工具 |
| 提示词工程 | 15 个专业 Prompt 文件 | 多 Agent 分离，JSON Schema 输出 |

---

## MaNA v4 架构

MaNA（Multi-Agent Narrative Architecture）是当前项目的核心叙事引擎。

### v4 相比 v3 的新增功能

> ⚠️ **实现状态说明**：部分 v4 功能代码已编写并接入管线，但因默认关闭尚未在实际小说导入场景中进行充分测试。Phase 1 导入管线的 5-Pass 流程和手动修正界面也尚未实现。

| 功能 | 代号 | 说明 | 默认状态 | 实现状态 |
|------|------|------|----------|----------|
| 迭代精炼循环 | `refinement` | Composer 输出 → Auditor 检查 → 不满意则重写 | ✅ 开启 | ⚠️ 已接入管线，未充分测试 |
| 多采样自洽 | `best_of_3` | Director 并行跑 3 次，PlanScorer 选最优 | ✅ 开启 | ⚠️ 已接入管线，未充分测试 |
| 微 Oracle | `micro_oracle` | 每拍结束后一句话质量反馈，注入下一拍 Director | ❌ 关闭 | ⚠️ 代码已实现并接入，默认关闭未测试 |
| 动态 Tier | `dynamic_tier` | 按场景复杂度自动调整 temperature / max_tokens | ✅ 开启 | ⚠️ 已接入管线，未充分测试 |
| 多视角合成 | `multi_view` | plot-driven + character-driven 双视角融合 | ✅ 开启 | ⚠️ 已接入管线，未充分测试 |
| 语义 Canon 选择 | `semantic_selection` | LLM 筛选与当前场景最相关的背景信息 | ❌ 关闭 | ⚠️ 代码已实现并接入，默认关闭未测试 |
| 角色防崩卡 | `anti_rules` | 反例规则约束角色行为，防止漂移 | ❌ 关闭 | ❌ 代码框架存在，未接入管线 |
| 向量记忆 | `vector_memory` | Ollama Embedding 语义检索历史场景 | ❌ 关闭 | ⚠️ 代码已实现并接入，默认关闭未测试 |

> v4 总开关：`manana_config.cfg` 中 `[v4] enabled=false` 时完全走 v3 兼容路径；各子功能可独立开关。

---

### 流水线总览

```
L0: ContextBuilder         → 构建场景上下文（角色/线索/位置/历史）
     ├─ [v4] CanonSelector    → 语义筛选最相关 Canon（可选）
     └─ [v4] VectorMemory    → 语义检索历史场景（可选）
L1: SceneDirector           → 节拍导演，决定本节拍走向
     ├─ [v4] Best-of-3      → 并行采样 3 次，Scorer 选最优（可选）
     └─ [v4] Multi-View     → plot + character 双视角融合（可选）
L2R1: MotivationEngine     → 动机分析（N 角色并行）
L2R2: DialogueWeaver       → 对话生成（N 角色并行）
      ActionDirector         → 动作编排（N 角色并行）
L3: SceneComposer          → 将各 Agent 输出编织成完整叙事文本
     └─ [v4] Refinement     → Auditor 检查 → 不满意则重写（可选）
L3b∥L4a: ConsistencyAuditor → 一致性审计（角色漂移/事实矛盾/规则违反/连续性断裂）
          StateExtractor      → 从叙事文本提取世界状态变更（并行）
L4b: ThreadManager         → 管理叙事线索（创建/推进/关闭）
L5: ReflectionOracle       → 每 5 节拍全局叙事健康评估
      [v4] MicroOracle      → 每拍一句话质量反馈（可选）
```

### 每节拍调用数

**v3 基线**：5 + 3N（N = 出场角色数），3 轮串行

**v4 开启后**：
- `best_of_3`：L1 调用次数 ×3（3 次并行采样）
- `multi_view`：L1 调用次数 ×2（plot + character 双视角）
- `refinement`：L3 可能触发 1-2 次重写循环
- 实际调用数动态变化，复杂场景下可达 v3 的 3-4 倍

---

### 三级模型分配

| Tier | 温度 | max_tokens | 超时 | 分配 Agent |
|------|------|------------|------|-------------|
| **Strong** | 0.5 | 4096 | 120s | Director / Composer / Oracle / PlanSynthesizer |
| **Medium** | 0.7 | 2048 | 120s | Motivation / DialogueWeaver / Auditor / ThreadManager |
| **Light** | 0.8 | 512 | 60s | ActionDirector / StateExtractor / PlanScorer / MicroOracle / CanonSelector |

> 当前模型：qwen3.5:9b（Ollama），所有 tier 同模型，通过 temperature / max_tokens 区分行为

---

### v4 关键设计

#### P0-1：迭代精炼循环（`refinement`）

```
Composer 输出
    ↓
ConsistencyAuditor 检查
    ├─ PASS         → 直接进入 L3b
    ├─ WARNING      → 最多 1 次微调（注入 refinement_hints）
    └─ FAIL         → 最多 2 次重写（注入 issues + fix_suggestion）
```

#### P0-2：多采样自洽（`best_of_3`）

```
Director × 3（并行，独立 Provider）
    ↓
PlanScorer 三维评分（thread_progress / character_naturalness / causal_link）
    ↓
总分最高者胜出（阈值 8/15，低于则全部重跑）
```

#### P1-1：微 Oracle（`micro_oracle`）

每拍结束后，用 light tier（temperature=0）对叙事质量做一句话评价，注入下一拍 Director 的 prompt，形成迭代改进闭环。

#### P1-2：动态 Tier 升级（`dynamic_tier`）

根据场景复杂度（角色数、线索数、交互对数）自动调整：
- 复杂度 < 0.3 → 部分 Agent 降级到 medium/light
- 复杂度 > 0.5 → Director/Composer 升级到更低 temperature（更 deterministic）

#### P1-3：多视角合成（`multi_view`）

```
Director(plot-driven)  ──→ PlanSynthesizer ──→ 融合方案
Director(character-driven) ──→            ──→ 注入 L2R1/L2R2
```

#### P2-1：语义 Canon 选择（`semantic_selection`）

用 CanonSelector（light tier）从候选 Canon 中选出 Top-K 最相关项，控制注入上下文的 token 预算（默认 1200 tokens）。

#### 向量记忆系统（`vector_memory`）

基于 Ollama `/api/embed` 接口 + cosine similarity：
- 每拍将叙事摘要存入向量库（MD5 去重缓存）
- 下一拍用当前上下文 embed 检索最相关的历史场景（top_k=3）
- 注入 ContextBuilder，增强长期连贯性

---

### 文件结构

```
Round/
├── src/
│   ├── llm/
│   │   ├── manana/          # MaNA v4 叙事引擎（22 文件）
│   │   │   ├── manana_pipeline.gd          # 五层编排器（核心调度）
│   │   │   ├── manana_config.gd           # v4 配置读取
│   │   │   ├── manana_schema.gd           # JSON Schema 定义
│   │   │   ├── manana_logger.gd           # Agent 调用日志
│   │   │   ├── base_agent.gd              # Agent 基类
│   │   │   ├── context_builder.gd         # L0 上下文构建
│   │   │   ├── scene_director.gd          # L1 节拍导演
│   │   │   ├── motivation_engine.gd       # L2R1 动机分析
│   │   │   ├── dialogue_weaver.gd        # L2R2 对话生成
│   │   │   ├── action_director.gd        # L2R2 动作编排
│   │   │   ├── scene_composer.gd         # L3 叙事编织
│   │   │   ├── consistency_auditor.gd    # L3b 一致性审计
│   │   │   ├── state_extractor.gd        # L4a 状态提取
│   │   │   ├── thread_manager.gd         # L4b 线索管理
│   │   │   ├── reflection_oracle.gd      # L5 反思神谕
│   │   │   ├── interaction_pair.gd       # 交互对数据结构
│   │   │   │
│   │   │   │   # --- v4 新增 ---
│   │   │   ├── vector_memory.gd          # 向量记忆系统
│   │   │   ├── canon_selector.gd        # 语义 Canon 选择
│   │   │   ├── plan_scorer.gd           # Best-of-3 评分器
│   │   │   ├── plan_synthesizer.gd      # 多视角融合器
│   │   │   └── micro_oracle.gd         # 每拍质量反馈
│   │   │
│   │   └── providers/       # LLM Provider 抽象层（5 文件）
│   │       ├── base_provider.gd
│   │       ├── ollama_provider.gd
│   │       ├── deepseek_provider.gd
│   │       ├── openai_provider.gd
│   │       └── provider_factory.gd
│   │
│   ├── autoload/           # Godot Autoload 单例（6 文件）
│   │   ├── world_state.gd
│   │   ├── event_bus.gd
│   │   ├── provider_registry.gd
│   │   ├── canon_loader.gd
│   │   ├── novel_scanner.gd
│   │   └── canon_extractor.gd
│   └── ui/                 # 终端风格 UI 脚本
│
├── prompts/                 # 提示词工程（15 文件）
│   ├── director.md          # L1 节拍导演（通用）
│   ├── director_plot.md     # L1 剧情视角（v4 multi_view）
│   ├── director_char.md    # L1 角色视角（v4 multi_view）
│   ├── motivation.md       # L2R1 动机分析
│   ├── dialogue_weaver.md # L2R2 对话生成
│   ├── action_director.md  # L2R2 动作编排
│   ├── composer.md         # L3 叙事编织
│   ├── auditor.md          # L3b 一致性审计
│   ├── state_extractor.md  # L4a 状态提取
│   ├── thread_manager.md   # L4b 线索管理
│   ├── oracle.md           # L5 反思神谕
│   ├── canon_selector.md   # v4 语义 Canon 选择
│   ├── scorer.md          # v4 Best-of-3 评分
│   �   └── synthesizer.md    # v4 多视角融合
│   └── micro_oracle.md    # v4 每拍质量反馈
│
├── scenes/                  # Godot 场景文件
├── novel/                   # 测试小说文本
├── addons/
│   └── godot_bridge_mcp/   # Godot Bridge MCP Server
├── manana_config.cfg        # MaNA v4 配置文件
└── project.godot            # Godot 项目配置
```

---

## 使用的模型

### 当前配置

| Tier | 模型 | 温度 | max_tokens | 超时 | 用途 |
|------|------|------|------------|------|------|
| Strong | qwen3.5:9b（Ollama） | 0.5 | 4096 | 120s | Director / Composer / Oracle / PlanSynthesizer |
| Medium | qwen3.5:9b（Ollama） | 0.7 | 2048 | 120s | Motivation / Dialogue / Auditor / Thread |
| Light | qwen3.5:9b（Ollama） | 0.8 | 512 | 60s | Action / StateExtractor / Scorer / MicroOracle |

> 端点：`<Ollama 端点，例如 http://localhost:11434/api/chat>`
> 嵌入模型：`qwen3-embedding:0.6b`（向量记忆系统用，可选）

### 预配置 Provider

- **Ollama**：当前激活，qwen3.5:9b 全 tier
- **DeepSeek API**：已预配，API Key 待填
- **OpenAI API**：已预配，API Key 待填

### 踩坑记录

**qwen3.5:9b 思考模式陷阱**：
- 症状：提示 "400 input length too long"（实际 prompt 仅 ~600-1000 字）
- 根因：模型默认开启思考模式，思考消耗全部 max_tokens，content 为空
- 修复：`reasoning_effort="none"` 或增大 max_tokens 至 2048

---

## MCP 设计

### Godot Bridge MCP

Round 项目集成了 **Godot Bridge MCP**，这是一个基于 Model Context Protocol（MCP）的插件，通过 WebSocket 将 AI 客户端与 Godot 4 编辑器连接起来。

#### 架构设计

```
AI Client (OpenCode / WorkBuddy)
        ↓ MCP Protocol (stdio)
Python MCP Server (FastMCP)
        ↓ WebSocket (port 4099)
Godot Editor (GodotBridgeWebSocket.gd)
```

**双通道设计**：
- **WebSocket 通道**：实时双向通信，低延迟（port 4099）
- **File-only 降级**：WebSocket 不可用时的文件读写降级方案

#### 工具清单（38 个）

| 类别 | 工具数 | 说明 |
|------|--------|------|
| 场景管理 | 6 | get_scene_tree / add_node / delete_node / create_scene / save_scene / create_scene_from_script |
| 节点管理 | 4 | get_node_properties / set_node_property / get_selected_nodes / list_node_types |
| 脚本管理 | 3 | execute_script / attach_script / get_script_info |
| 资源管理 | 2 | list_assets / get_editor_info |
| Round 专属 | 10 | list_canons / read_canon / list_novels / read_debug_json / read_save 等 |
| Resources | 5 | 暴露 Godot 项目状态给 MCP 客户端 |

#### 安全设计

23 个工具带有安全标签：
- `[READ-ONLY]`：只读操作，不会修改项目
- `[EDITOR]`：会修改场景或脚本
- `[DESTRUCTIVE]`：危险操作，需用户确认

#### 技术实现

- **语言**：TypeScript（Node 22.22.2）+ Python（FastMCP）
- **通信**：WebSocket（websockets 库）
- **协议**：MCP（Model Context Protocol）stdout/stdin
- **Godot 插件**：GodotBridgeWebSocket.gd（WebSocket 服务端）

---

## 提示词工程

Round 项目的提示词工程是一个持续迭代的过程，由 **WorkBuddy（AI 助手）** 完成所有提示词的编写、测试与优化，项目作者提供思路与反馈。

### Prompt 文件（15 个）

| 文件 | Agent | 职责 |
|------|-------|------|
| `director.md` | Scene Director | 节拍导演，决定下一个叙事节拍的走向（通用） |
| `director_plot.md` | Scene Director（剧情视角） | v4 multi_view：剧情驱动的节拍方案 |
| `director_char.md` | Scene Director（角色视角） | v4 multi_view：角色驱动的节拍方案 |
| `motivation.md` | Motivation Engine | 分析角色内心世界、动机、对玩家的态度 |
| `dialogue_weaver.md` | Dialogue Weaver | 生成角色对话，保持角色一致性 |
| `action_director.md` | Action Director | 生成角色动作和场景描述 |
| `composer.md` | Scene Composer | 将各 Agent 输出编织成完整叙事文本 |
| `auditor.md` | Consistency Auditor | 检查叙事一致性（角色漂移/事实矛盾/规则违反/连续性断裂） |
| `state_extractor.md` | State Extractor | 从叙事文本中提取世界状态变更 |
| `thread_manager.md` | Thread Manager | 管理叙事线索（创建/推进/关闭） |
| `oracle.md` | Reflection Oracle | 每 5 节拍进行一次全局叙事健康评估 |
| `canon_selector.md` | Canon Selector | v4：语义筛选最相关的背景信息 |
| `scorer.md` | Plan Scorer | v4 Best-of-3：对 Director 输出做三维评分 |
| `synthesizer.md` | Plan Synthesizer | v4 multi_view：融合双视角节拍方案 |
| `micro_oracle.md` | Micro Oracle | v4：每拍一句话质量反馈 |

### 提示词优化历程

#### Phase 1：Prompt 瘦身（2026-06-16）

- **System Prompt**：1800 → 600 字（删除冗长示例、合并重复规则）
- **角色上下文**：7 字段 → 4 字段（性格/说话风格/动机/态度），2000 → 1200 字
- **叙事历史**：3 条 → 2 条
- **预估请求体**：~8000 → ~5600 字节，减少 ~30%

#### Phase 2：JSON Schema 设计

早期版本使用 HTML 注释标记（如 `<!-- beat_id: xxx -->`）来结构化输出，存在问题：
- 解析不稳定，容易因 LLM 输出格式偏差而失败
- 无法利用 JSON 的结构化验证能力

**解决方案**：全新设计 JSON Schema，每个 Agent 输出严格的 JSON 对象。

#### Phase 3：多 Agent 提示词分离（v3）

将单体 LLM 调用拆分为多个专业 Agent，每个 Agent 有独立的：
- **角色定义**：明确该 Agent 的职责边界
- **输入上下文**：只传入相关上下文，减少 token 消耗
- **输出格式**：针对该 Agent 任务设计的 JSON Schema
- **质量标准**：针对性的评估标准

#### Phase 4：v4 多视角与自洽（2026-06-17~18）

- **Best-of-3**：新增 `scorer.md`（三维评分 prompt）+ `synthesizer.md`（融合 prompt）
- **Multi-View**：新增 `director_plot.md` + `director_char.md`（双视角 Director prompt）
- **Micro-Oracle**：新增 `micro_oracle.md`（一句话质量反馈 prompt）
- **Canon Selector**：新增 `canon_selector.md`（语义筛选 prompt）

#### Phase 5：Anti-Rules 防崩卡（v4 设计中）

为防止角色行为漂移，为每个角色定义 **Anti-Rules**（反例规则）：
- 明确列出该角色**不应该**做什么
- 在 Motivation Engine 的 prompt 中注入 `anti_rules` 字段
- Auditor 检查时会参考这些规则

---

## 世界偏离度系统

Round 项目实现了**世界偏离度**机制，追踪玩家行为与原著的差距：

### 计算公式

```
偏离度 = 已关闭线索数 × 0.08 + 活跃线索平均进度 × 0.1 + 声誉离散度(abs spread) × 0.15
```

### 5 级偏离度

| 级别 | 描述 | 叙事策略 |
|------|------|----------|
| 0 | 紧密沿原著 | 忠实原著，小改动 |
| 1 | 局部微小偏离 | 允许局部变化，保持主线 |
| 2 | 显著偏离 | 大胆创新，但保持角色一致性 |
| 3 | 大幅偏离 | 开放叙事，角色可能做出意外行为 |
| 4 | 完全脱离 | 完全自由叙事，原著仅作为背景 |

### 触发时机

- `adjust_player_reputation()` 后自动重算
- `_close_thread()` 后自动重算

---

## 开发历程

Round 项目由 **WorkBuddy（AI 助手）** 完成，项目作者仅负责提供思路和想法。

### 开发阶段

| Phase | 时间 | 内容 | 状态 |
|-------|------|------|------|
| Phase 0 | 06-15 | 基础框架（Godot 骨架、终端 UI、Autoload） | ✅ 完成 |
| Phase 1 | 06-15~16 | 导入管道（Novel Scanner、Canon Extractor） | ⚠️ 部分完成 |
| Phase 2 | 06-15~17 | 叙事引擎（MaNA v0.1 → v3） | ✅ 完成 |
| Phase 3 | 06-17~18 | 完整体验（F1-F5 面板、存档系统、结局系统） | ✅ 完成 |
| **Phase 4** | **06-18** | **MaNA v4（8 项增强功能）** | **⚠️ 代码完成，未充分测试** |
| Phase 5 | 待定 | 打磨（多种结局、关系图谱可视化、导入引导） | ❌ 未开始 |

### 关键里程碑

- **06-15**：项目启动，完成 Phase 0 + Phase 1 部分 + MaNA v0.1
- **06-16**：Prompt 瘦身，修复 qwen3.5:9b 思考模式陷阱
- **06-17**：MaNA v3 重构，5 层多 Agent 叙事管线
- **06-18**：MaNA v4 实现，8 项增强功能（refinement / best_of_3 / dynamic_tier / multi_view 等）

---

## 测试数据

- **测试小说**：《成為我筆下小說的路人甲》、《魔王去上學》
- **测试 Canon**：`novel/canon.json`
- **测试日志**：`debug/agent_traces/` 中有 12 组 v0.1 响应日志 + 完整 MaNA v4 trace

---

## ⚠️ 当前限制与未实现功能

### Phase 1 导入管管（部分完成）

- ❌ **5-Pass 导入流程**（Pass A-E）未实现，当前仅支持单次 Canon 提取
- ❌ **手动修正界面**未实现，导入结果无法在游戏内手动编辑

### v4 功能状态

- ⚠️ 大部分 v4 功能代码已实现并接入管线，但因默认关闭（`enabled=false` 或各子功能独立开关），**尚未在实际小说导入场景中进行充分测试**
- ❌ `anti_rules`（角色防崩卡）：代码框架存在（`prompts/anti_rules.md` 尚未创建），未接入管线

### Phase 3 未完成部分

- ❌ **多种结局条件细化**：当前仅基于偏离度触发结局，条件较粗糙
- ❌ **角色关系图谱可视化**：当前为文字版，可视化未实现
- ❌ **小说导入引导流程**：首次进入游戏的引导 UI 未实现

### Phase 5 未开始

- ❌ 打磨阶段所有功能均未开始

---

## 如何运行

### 前置条件

1. **Godot 4.6**：[下载地址](https://godotengine.org/download)
2. **Ollama**：[下载地址](https://ollama.com)，并拉取模型：
   ```bash
   ollama pull qwen3.5:9b
   # 向量记忆可选：
   ollama pull qwen3-embedding:0.6b
   ```
3. **（可选）DeepSeek / OpenAI API Key**：编辑 `manana_config.cfg`

### 运行步骤

1. 打开 Godot 4.6，导入 `Round` 项目
2. 运行 `scenes/main.tscn`
3. 在终端 UI 中输入小说文本或选择测试小说
4. 系统自动解析并启动叙事引擎

---

## 配置说明

### MaNA v4 配置（`manana_config.cfg`）

```ini
[v4]
# v4 总开关：false = 完全走 v3 路径
enabled=false

[refinement]
# 迭代精炼循环
enabled=true

[best_of_3]
# 多采样自洽
enabled=true
sample_count=3
scorer_min_total=8

[multi_view]
# 多视角合成
enabled=true

[dynamic_tier]
# 动态 Tier 升级
enabled=true

[memory]
# 向量记忆
enable_vector_memory=false
embed_model="qwen3-embedding:0.6b"
vector_top_k=3
```

> 开启 `enabled=true` 后，各子功能按上方开关独立生效。

---

## 贡献者

| 角色 | 名称 | 说明 |
|------|------|------|
| 创意提供 | 项目作者 | 提供项目思路、想法、需求、反馈 |
| AI 开发 | WorkBuddy | 完成所有代码、提示词、文档、架构设计 |
| 测试 | 项目作者 + WorkBuddy | 多轮 QA 测试，Bug 修复 |

### 关于"由 WorkBuddy 完成"

本项目从架构设计、代码实现、提示词编写到文档生成，全部由 **WorkBuddy（AI 助手）** 在项目作者的思路指导下完成。项目作者负责：
- 提供项目创意和核心想法
- 决策技术方向和功能优先级
- 测试反馈和 Bug 报告

WorkBuddy 负责：
- 所有 GDScript 代码编写
- MaNA 多 Agent 架构设计
- 15 个提示词文件的编写与优化
- Godot Bridge MCP 集成
- 本文档及所有技术文档的撰写

---

## 致谢

- **米哈游《Varsapura》（雨之城）**：项目灵感来源
- **Ollama**：本地 LLM 部署方案
- **Godot Engine**：开源游戏引擎
- **FastMCP**：MCP Server 框架

---

<div align="center">

**Round — 让小说世界触手可及**

</div>
