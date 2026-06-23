# Agentopia 项目深度分析 — 概览与架构

> 分析日期：2026-06-22
> 项目版本：查阅 README 为最新版本

---

## 一、项目概览

**Agentopia** 是一个基于大语言模型（LLM）的多智能体社会长期生活模拟框架。核心目标有二：

1. 构建一个让 LLM 智能体有效模拟人类社会生活的环境
2. 通过社会模拟产生的"生活奖励"（life reward）来提升 LLM 的拟人化角色扮演能力

**关键实验指标**：100 个智能体，10 个模拟年份

### 1.1 整体工作流

每个模拟周期是一个 **周循环**：

```
计划 (Plan) → 公共事件签到 (BEFORE_CONTACT) → 联络社交 (CONTACT) → 活动执行 (ACTIVITY) → 回顾总结 (REVIEW) → 结算 (SETTLE)
```

每年末额外执行：
- 年度档案更新（profile update）
- 职位申请季（position application）
- 奖励计算（reward calculation）

### 1.2 目录结构全景

```
Agentopia/
├── config.example.json         # 配置模板（LLM API Key、世界参数等）
├── requirements.txt            # 依赖：openai, anthropic, google-genai, tiktoken 等
├── data/                       # 世界数据
│   ├── apartment/              # 示例世界：现代公寓社区（100个agent）
│   ├── school/                 # 示例世界：中国高中
│   └── persona_template/       # 角色数据模板
├── scripts/                    # 运行/分析脚本
│   ├── run_world.py            # 模拟主入口
│   ├── build_rft_data.py       # 构建 RLHF 训练数据
│   ├── compute_metrics.py      # 定量指标计算
│   └── time_analysis.py        # 性能时间分析
├── src/                        # 核心源代码
│   ├── config.py               # 配置加载
│   ├── utils.py                # 工具函数（LLM调用、缓存、日志）
│   ├── agents/                 # 智能体层
│   │   ├── role_agent.py       # 角色扮演智能体核心
│   │   ├── data_manager.py     # 数据管理（记忆、档案、状态）
│   │   ├── prompts.py          # 提示词模板（~2000行）
│   │   ├── functions.py        # 工具函数注册表
│   │   ├── context.py          # 对话上下文管理
│   │   └── response_validator.py # 响应验证循环
│   └── world/                  # 世界模拟引擎
│       ├── world.py            # 顶级调度器
│       ├── clock.py            # 离散时间系统
│       ├── god.py              # "上帝模型"（Environment Model）LLM调用
│       ├── activity.py         # 活动类型：联合/单人/公共
│       ├── scheduling.py       # 调度系统 + 消息中心
│       ├── reward.py           # 奖励计算（PageRank + 主观 + 经济）
│       ├── position_application.py # 职位申请系统
│       ├── locations.py        # 位置存储
│       ├── mapgen.py           # 地图生成
│       └── cleanup.py          # 数据清理
├── logs/                       # 运行日志
└── llm_cache/                  # LLM 响应缓存
```

---

## 二、架构层次

Agentopia 采用 **三层架构**：

### 2.1 世界引擎层 (World Engine) — `src/world/`

| 模块 | 职责 |
|------|------|
| `world.py` | 主循环调度，按年/周/阶段推进模拟 |
| `clock.py` | 离散时间系统（年→周→阶段→天→slot） |
| `god.py` | "上帝模型"（Environment Model），用 LLM 驱动所有非智能体决策 |
| `activity.py` | 活动执行引擎（Joint/Solo/Public） |
| `scheduling.py` | 联合活动调度 + 消息传递中心 |
| `reward.py` | 三大奖励计算 |
| `position_application.py` | 年度职位申请流程 |
| `locations.py` | 位置数据管理 |
| `mapgen.py` | 地图生成 |
| `cleanup.py` | JSONL 文件清理 |

### 2.2 智能体层 (Agent Layer) — `src/agents/`

| 模块 | 职责 |
|------|------|
| `role_agent.py` | RoleAgent 类：核心角色扮演智能体 |
| `data_manager.py` | DataManager 类：记忆、状态、档案、日程管理 |
| `prompts.py` | 大量提示词模板（~2000行） |
| `functions.py` | LLM 工具函数定义（list/read/update scratchpad） |
| `context.py` | 对话上下文压缩算法 |
| `response_validator.py` | 响应验证 + 重试循环 |

### 2.3 基础设施层 (Infrastructure) — `src/config.py` + `src/utils.py`

| 模块 | 职责 |
|------|------|
| `config.py` | 配置加载、API key 脱敏 |
| `utils.py` | LLM 多后端调用、三层缓存系统、日志系统 |

---

## 三、核心设计模式

### 3.1 双模型架构

- **Role Model**：驱动每个智能体的角色扮演行为（可配置不同模型）
- **God Model (Environment Model)**：单一权威模型，负责所有世界级决策（活动评价、事件生成、职位匹配等）

这种设计的核心目的是让 social metrics 评估保持一致性（不因角色模型不同而产生偏差）。

### 3.2 时间系统 (Clock + TimeState)

```
Stage 枚举:
  BEGIN=0 → PLAN=1 → BEFORE_CONTACT=2 → CONTACT=3 →
  AFTER_CONTACT=4 → ACTIVITY=5 → REVIEW=6 → SETTLE=7

时间串格式:
  普通阶段: Y{year}-W{week}-{stage}
  联络阶段: Y{year}-W{week}-contact-S{slot}
  活动阶段: Y{year}-W{week}-activity-D{day}

TimeState 支持完整比较操作（<, >, ==），是排序和窗口查询的基础。
```

### 3.3 三层缓存系统

```
三层查询: worker_delta → main_thread_delta → shared_cache (disk)

- 每线程独立 delta 字典，写时先写入本地 delta
- 每 FLUSH_EVERY_N(=1) 次 miss 即落盘到 shard 文件
- 共享缓存从 llm_cache/ 只读加载，避免跨线程竞争
- 每运行使用独立缓存目录避免冲突
```

### 3.4 数据持久化策略

- **追加写入（append-only）**：JSONL 格式，所有事件日志、状态变更等都是追加
- **覆盖写入**：JSON 格式，仅 Profile（年度快照）和 Checkpoint
- **JSONL 时间有序性校验**：`_append_jsonl` 中检查新记录时间 >= 末条记录时间
