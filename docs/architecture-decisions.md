# Rain Web 架构决策记录 (ADR)

> 最后更新：2026-06-23 00:02
> 维护规则：每次架构级改动必须同步更新此文档。

---

## 一、技术栈

| 层 | 技术 | 选型理由 |
|---|------|---------|
| 后端框架 | FastAPI (Python) | 原生 async/await，WebSocket 一等支持 |
| LLM 调用 | DeepSeek API + Ollama（双后端） | 云端 + 本地混合，成本/延迟可调 |
| 前端 | 纯 JS ES Module（无框架） | 零构建工具，直接浏览器加载，开发快 |
| 前端状态 | AppState 单例 + EventBus | 松耦合模块通信，无第三方依赖 |
| 前端 FSM | UnifiedFSM（自研） | 三阶段状态机：novel_select / narrative / error |
| 配置 | YAML (`config.yaml`) | 人类可读，50+ 配置项集中管理 |
| 存档 | JSON 文件（3 槽位） | 简单可靠，人类可调试 |
| 管线引擎 | MaNA v4（自研多智能体） | 15 Agent 分层协作，LLM 调用 5~20+ 次/拍 |

---

## 二、核心架构决策

### ADR-001：单例 App 模式 + EventBus

**决策**：前端采用 `App.state`（全局状态容器）+ `App.bus`（事件总线），模块通过 `App.on()` / `App.emit()` 松耦合通信。

**理由**：
- 无框架依赖，浏览器原生加载
- 各 UI 面板（叙事、角色、存档等）独立开发，互不直连
- 状态统一管理，避免 props drilling

**约束**：
- 禁止模块间直接调用，必须通过事件总线
- 所有状态变更最终反映到 `App.state`

### ADR-002：三层 FSM 状态机

**决策**：前端状态机分为 `novel_select` → `narrative` → `error` 三阶段，所有状态转换必须通过 `App.setPhase()`。

**理由**：
- 游戏流程有明确的阶段边界（选书 → 游玩 → 异常）
- FSM 提供状态转换合法性校验，防止非法跳转
- `setPhase()` 双写同步 `App.state.gamePhase` + `App.fsm`

**约束**：
- 禁止直接修改 `App.state.gamePhase` / `App.state.novelSelectPhase`
- `isMidGame` 由 FSM 状态 + `beatCount` 自动推导（getter），禁止手动赋值

### ADR-003：灵魂附生为唯一游戏模式

**决策**：移除 interactive 模式，`game_mode` 固定为 `soul_possession`。

**理由**：
- 双模式维护成本高，interactive 使用率低
- 灵魂附生（玩家灵魂附到 NPC 身上）是核心叙事驱动力
- 简化欢迎界面（不需要模型选择），canon_ready 后自动弹选角

**约束**：
- 所有叙事逻辑默认走 soul_possession 路径
- 不再需要 `if game_mode == "interactive"` 分支

### ADR-010：灵魂附生双人格数据模型

**决策**：`player_profile`(玩家灵魂) 与 `characters_state[protagonist_id]`(角色原主) 作为**独立数据结构**，通过 `soul_possession` 控制融合度。

**设计哲学**：

```
                本我选择(authentic)             贴合选择(conforming)
                      ↓                               ↓
            player_profile 演化              characters_state 不变
            (玩家灵魂特质积累)                (角色原主性格参照)
                      ↓                               ↓
                 NPC 认知冲突 ──────────────────────────┘
                 (dissonance: 角色行为异常)
```

| 概念 | 存储位置 | 演化方式 | 用途 |
|------|---------|---------|------|
| 玩家灵魂人格 | `player_profile` | 通过本我选择积累 traits/motivation | 生成本我选项、驱动 NPC 认知偏离 |
| 角色原主人格 | `characters_state[protagonist_id]` (canon) | 不变（从 Canon JSON 加载） | 生成贴合选项、NPC 记忆参照 |
| 灵魂融合度 | `soul_possession.blend_ratio` | 随选择动态调整 | 控制叙事中人格表现比例 |
| NPC 认知冲突 | `cognitive_dissonance[{npc_id}]` | 本我选择时累积，贴合选择时不触发 | 驱动 NPC 对"非本人"的发现剧情 |
| **共享状态** | | | |
| 物理位置 | `player_location` ↔ `characters_state[protagonist_id].location` | **双向同步**（`apply_patch`, `apply_location_change`） | 玩家和角色在同一具身体中 |

**共享 vs 分离规则**：
- ✅ **共享**：位置（同一具身体）、名字
- ❌ **分离**：人格特质、动机、倾向 — 这两套人格的差异就是认知冲突的来源

**实现**：
- `WorldState._protagonist_id` 追踪当前附生角色
- `reconcile_player_state()` 在每个状态变更点自动调平位置
- `add_player_trait()` 等方法**仅写入 `player_profile`**，不修改 `characters_state`

### ADR-004：MaNA 管线分层架构

**决策**：叙事生成分为 L0~L5 六层，每层调用不同 tier 的 LLM：

| 层 | Agent | Tier | 功能 |
|----|-------|------|------|
| L0 | ContextBuilder | - | 构建上下文（角色、记忆、线索） |
| L1 | Director | strong | 场景导演：选角、叙事模式、节拍规划 |
| L1B | ContinuityChecker | medium | 一致性检查：拒绝 → 重做 L1 |
| L2R1 | Motivation × N | medium | 各角色动机生成（并行） |
| L2R2 | Dialogue × N + Action × N | medium + light | 对话+动作生成（并行） |
| L2R3 | RoleReflector | light | 角色反思：过渡/重写判定 |
| L3 | Composer | strong | 叙事文本合成 + Auditor 评分 |
| L3B | Auditor + Extractor + CharMgr + LocMgr | mixed | 4 路并行状态抽取 |
| L4A | StateExtractor | light | 世界状态更新 |
| L4B | ThreadManager | medium | 叙事线索管理 |
| L5 | Oracle | strong | 深度反思（每 5 拍） |
| - | MicroOracle | light | 微观健康检查（每拍） |

**Tier 定义**：
- `strong`：DeepSeek 大模型，用于核心创作任务
- `medium`：中等模型，用于角色引擎和一致性检查
- `light`：轻量模型/规则引擎，用于状态抽取和辅助任务

### ADR-005：WebSocket 单连接持久化

**决策**：前后端通过单个 WebSocket 连接通信，支持断线重连（从 localStorage 恢复 session_id）。

**理由**：
- 避免 HTTP 轮询开销
- 服务端推送叙事流（`narrative_chunk` 逐步打字效果）
- session 30 分钟 TTL，自动清理

**约束**：
- WebSocket 40+ 消息类型，全部通过 `if/else if` 链路由（禁止顺序 `if`）
- `WebSocketManager` 使用 `asyncio.Lock` 保护共享字典

### ADR-006：Canon 目录结构

**决策**：Canon（世界观数据）以目录结构存储：

```
novel/{title}/
├── meta.json
├── rules/world_rules.json
├── characters/char_*.json
└── locations/loc_*.json
```

**理由**：独立编辑单个条目，无需加载全量 JSON；通过 `CanonManager` + `CanonStorage` 统一访问。

### ADR-007：配置热重连

**决策**：F7 设置面板修改 API 配置后，`pipeline.reload_config()` 触发管线热重连。

**理由**：无需重启即可切换 LLM 后端，配置备份（`.yaml.bak`）防误操作。

### ADR-008：Canon 仅通过 JSON 导入

**决策**：移除 TXT/EPUB 上传和 LLM 生成 Canon 功能，仅支持 JSON 文件导入。`server/extractors/` 目录已删除。

**理由**：
- LLM Canon 生成不稳定、耗时、成本高
- 用户通常已有或可手写 Canon JSON
- 简化欢迎界面，降低用户认知负担

**约束**：
- 欢迎界面仅显示 Canon JSON 列表 + 导入按钮
- `regenerate_canon` / `upload_novel` 消息处理器已移除
- `start_llm_generation_with_progress()` 已删除

### ADR-009：Canon 存储后端抽象

**决策**：`server/storage/` 提供 `CanonStorage` 抽象接口，`FileStorage` 为默认实现。CanonManager 通过存储后端执行 CRUD。

**理由**：
- Canon 目录结构（`novel/{title}/characters/`, `locations/`, `rules/`）需要统一的读写接口
- 抽象层允许未来替换为数据库/云存储
- 支持独立编辑单个角色/地点条目

**约束**：
- 所有 Canon 数据操作必须通过 CanonManager → CanonStorage 接口
- 不允许直接读写 `novel/{title}/` 下的文件

---

## 三、代码规范（强制）

| 规则 | 说明 |
|------|------|
| **import 置顶** | 所有 import 必须在文件顶部（排除 `TYPE_CHECKING` 和可选依赖） |
| **FSM 转换** | 禁止直接修改 `App.fsm.phase/.state`，使用 `App.setPhase()` |
| **定时器** | 使用递归 `setTimeout` 替代 `setInterval`，定时器 ID 必须存储 |
| **WS 消息路由** | 使用 `if/else if` 链，确保单一匹配 |
| **相对导入** | 项目内使用 `from .xxx import`，禁止 `from server.xxx` |
| **异常处理** | 禁止空的 `try/except: pass`，必须至少记录日志 |
| **async 并发** | 共享字典操作必须加 `asyncio.Lock` |
| **不写死** | 预留扩展接口（可选参数、回调/事件、配置项、策略模式） |
| **联动修改** | 改一处必须同步检查上下游依赖 |

---

## 四、关键数据流

```
config.yaml → GameSession → MananaPipeline → 15 Agent LLM 调用
                                    ↓
                              WorldState ← state_patch
                                    ↓
                              SaveManager → saves/slot_*.json
                                    ↓
                              前端 FSM → App.state → UI 面板
```

### WorldState 核心字段（29 个）

| 字段 | 类型 | 说明 |
|------|------|------|
| `canon` | dict | 世界观数据（角色/地点/规则） |
| `characters_state` | dict | 角色运行时状态（情绪、态度等），**主角包含位置但人格独立** |
| `player_profile` | dict | 玩家灵魂人格（traits/motivation/tendency/name），**与角色原主人格分离** |
| `player_location` | str | 玩家/主角当前位置，**与 `characters_state[protagonist_id].location` 双向同步** |
| `player_reputation` | dict | 玩家在各 NPC 处的声望值 |
| `_protagonist_id` | str | 当前附生角色 ID，用于双向同步 |
| `soul_possession` | object | 灵魂附生状态（canon_soul/player_soul/blend_ratio） |
| `narrative_threads` | dict | 叙事线索 |
| `world_divergence` | float | 世界偏离度 |
| `narrative_tension` | float | 叙事张力 |
| `cognitive_dissonance` | dict | NPC 认知冲突 |
| `narrative_history` | list | 叙事历史 |
| `scene_memory` | list | 场景记忆 |
| `pending_emergences` | dict | 待处理的涌现事件 |
| `memory` | object | 记忆系统 |

---

## 五、已弃用/移除的架构

| 项目 | 状态 | 说明 |
|------|------|------|
| Interactive 模式 | ❌ 已移除 | 仅保留 soul_possession |
| `@app.on_event("startup")` | ❌ 已替换 | 改为 `lifespan` async context manager |
| `setInterval` | ❌ 已替换 | 全部改为递归 `setTimeout` |
| `_config_cache` | ❌ 已删除 | 统一使用 `_config_yaml` |
| 欢迎界面模型选择 | ❌ 已删除 | canon_ready 后自动弹选角 |
| `save_traces()` | ❌ 已删除 | 无实际作用的死代码 |
| 中文 tier 名称 | ❌ 已统一 | 全部改为 strong/medium/light |
| `progress` 字段 | ❌ 已替换 | 改为 intensity + complexity |
| `server/extractors/` | ❌ 已删除 | LLM 文本抽取模块（3 文件） |
| `start_llm_generation_with_progress()` | ❌ 已删除 | 170 行异步生成函数 |
| TXT/EPUB 上传 | ❌ 已移除 | 仅保留 Canon JSON 导入 |
| `regenerate_canon` / `upload_novel` | ❌ 已移除 | WS 消息处理器 |

---

## 六、变更记录

| 日期 | 变更 | 影响范围 |
|------|------|---------|
| 2026-06-22 | 初始创建 ADR | 全项目 |
| 2026-06-22 | 灵魂附生唯一化 | 5 个文件 |
| 2026-06-22 | FSM isMidGame getter 化 | AppState.js + app.js |
| 2026-06-22 | WebSocketManager 加锁 | ws_manager.py + main.py |
| 2026-06-22 | 角色数量上限 8/12 | game_session.py |
| 2026-06-22 | setInterval → setTimeout | app.js + AppState.js |
| 2026-06-22 | FastAPI lifespan 迁移 | main.py |
| 2026-06-22 | RewardTracker 日志轮换 | reward_tracker.py |
| 2026-06-22 | model_list 合并为单一处理器 | app.js |
| 2026-06-23 | 删除 extractors/ + 死代码清理 | game_session.py, novel_loader.py, main.py |
| 2026-06-23 | 欢迎界面简化为 Canon JSON 导入 | index.html, app.js |
| 2026-06-23 | 品牌更名 Rain → 小说模拟器 | index.html, app.js, narrative.js |
| 2026-06-23 | 仪表盘死数据清理（天气/HP/MP） | index.html, dashboard.js, dashboard.css |
| 2026-06-23 | 删除 7 个未使用 REST API | main.py (-260行) |
| 2026-06-23 | player/角色一致性重构（ADD-010） | world_state.py, game_session.py, pipeline_context.py, AppState.js, characters.js |
| 2026-06-23 | location ID → name 解析 | game_session.py._init_soul_possession |
| 2026-06-23 | 存档恢复前端状态修复 | fsm.js, app.js, save_manager.py, ws-client.js |
| 2026-06-23 | 初始 10 拍后弹出 soul choice | game_session.py._needs_soul_choice |
| 2026-06-23 | window.App 全局暴露修复 | app.js |
