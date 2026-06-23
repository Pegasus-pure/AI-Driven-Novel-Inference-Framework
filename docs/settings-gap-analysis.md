# Rain Web — 配置与前端设置映射差距分析

> 分析日期: 2026-06-23
> config.yaml 总段落: **14 个**；前端设置暴露段落: **3 个**（API / UI / 管线）

---

## 一、总体概览

| config.yaml 段落 | 参数数量 | 前端是否暴露 | 暴露位置 | 状态 |
|:--|:--|:--|:--|:--|
| `app` | 3 | ❌ | — | 完全缺失 |
| `providers` (×3 tier) | 7×3=21 | ⚠️ 部分 | API 设置 | 缺 timeout |
| `features` | 11 | ✅ | 管线配置 → 功能开关 | 完整 |
| `game` | 3 | ❌ | — | 完全缺失 |
| `emergence` | 4 | ❌ | — | 完全缺失 |
| `continuity` | 2 | ❌ | — | 完全缺失 |
| `reflection` | 5 | ❌ | — | 完全缺失 |
| `memory` | 15 | ❌ | — | 完全缺失 |
| `soul_possession` | 12 | ❌ | — | 完全缺失 |
| `desktop` | 4 | ❌ | — | 完全缺失(pygame) |
| `truncation` | 4 | ❌ | — | 完全缺失 |
| `reward` | 7 | ❌ | — | 完全缺失 |
| `prompt_optimization` | 5 | ❌ | — | 仅功能开关存在 |
| `composer` | 3 | ❌ | — | 完全缺失 |

**暴露率: ~15%**（仅 features 段 11 个开关 + providers 基础参数）  
**缺失参数总数: ~90+ 个**

---

## 二、逐段详细分析

### 2.1 `app` 段 — ❌ 完全缺失

```yaml
app:
  title: Rain
  host: 127.0.0.1
  port: 8000
```

| 参数 | 类型 | 默认值 | 说明 | 建议操作 |
|:--|:--|:--|:--|:--|
| `title` | str | Rain | 应用标题 | 只读展示在关于页 |
| `host` | str | 127.0.0.1 | 监听地址 | 服务端配置，不建议前端改 |
| `port` | int | 8000 | 监听端口 | 服务端配置，不建议前端改 |

**结论**: app 段是服务器启动参数，不适合放在前端设置中。建议以后端重启参数形式提供，而非运行时配置。

---

### 2.2 `providers` 段 — ⚠️ 部分暴露（缺 timeout）

**已暴露**: type, endpoint, model, api_key, temperature, max_tokens (所有 3 层)  
**缺失**: `timeout` (每层都有 strong=180, medium=120, light=60)

```yaml
providers:
  strong:
    timeout: 180    # ❌ 前端不可见
  medium:
    timeout: 120    # ❌ 前端不可见
  light:
    timeout: 60     # ❌ 前端不可见
```

**影响**: 用户无法调整 LLM 请求超时时间，本地 Ollama 响应慢时可能触发不必要的超时。  
**建议**: 在 API 设置 → 每层卡片底部添加「高级」折叠区，包含 timeout 滑块。

---

### 2.3 `game` 段 — ❌ 完全缺失

```yaml
game:
  oracle_interval: 5          # 神谕间隔（每 N 拍）
  auto_save_interval: 10       # 自动保存间隔（每 N 拍）
  max_reconnect_attempts: 5    # 最大重连次数
```

| 参数 | 影响 | 优先级 |
|:--|:--|:--|
| `oracle_interval` | 宏观神谕评估频率，影响叙事节奏 | 🔴 高 |
| `auto_save_interval` | 自动保存频率，影响数据安全 | 🔴 高 |
| `max_reconnect_attempts` | WebSocket 断线重连 | 🟡 中 |

**建议**: 新增「⚔️ 游戏参数」子页面。

---

### 2.4 `emergence` 段 — ❌ 完全缺失

```yaml
emergence:
  hit_threshold: 3             # 提及阈值
  similarity_threshold: 0.75   # 相似度阈值
  feature_extraction: llm      # 特征提取方式
  max_pending_entities: 50     # 最大待处理实体数
```

**影响**: 涌现实体系统核心参数，直接影响新角色/地点的自动检测行为。  
**建议**: 新增「🌱 涌现系统」子页面。

---

### 2.5 `continuity` 段 — ❌ 完全缺失

```yaml
continuity:
  max_rewrite: 2    # 最大重写次数
  tier: medium      # 使用的智能层
```

**影响**: 连续性检查失败后的重试策略。  
**建议**: 合并到「⚔️ 游戏参数」或独立「🔍 连续性审计」子页面。

---

### 2.6 `reflection` 段 — ❌ 完全缺失

```yaml
reflection:
  tier: light               # 使用的智能层
  check_clothing: true      # 检查服装
  check_location: true      # 检查地点
  check_mood: true          # 检查情绪
  check_relationship: true  # 检查关系
```

**影响**: 角色反思的检查维度，影响 NPC 一致性。  
**建议**: 新增「✨ 角色反思」子页面。

---

### 2.7 `memory` 段 — ❌ 完全缺失（15 个参数！）

```yaml
memory:
  persist: true                     # 是否持久化
  persist_path: novel/{title}/...   # 持久化路径
  auto_flush_beats: 1              # 自动刷新频率
  recency_weight: 0.4              # 近期权重
  relevance_weight: 0.3            # 相关性权重
  importance_weight: 0.3           # 重要性权重
  decay_lambda: 0.05               # 衰减系数
  reflection_threshold: 30         # 反思阈值
  top_k_director: 5                # 导演检索数
  top_k_character: 3               # 角色检索数
  max_entries_per_agent: 200       # 最大记忆条数
  retrieve_recency_window: 100     # 检索窗口
  retention_window: 50             # 保留窗口
  low_importance_threshold: 4.0    # 低重要性阈值
  compact_interval: 10             # 压缩间隔
```

**这是最大的缺失段落！** 记忆系统是 Rain 核心架构之一，15 个参数全部不可见。  
**建议**: 新增「🧠 记忆系统」子页面，分为「权重」「容量」「检索」三个 Tab。

---

### 2.8 `soul_possession` 段 — ❌ 完全缺失

```yaml
soul_possession:
  initial_blend_ratio: 0.8
  memory_access: full
  personality_derivation_beats: 10
  dissonance:
    authentic_increment: 0.1
    conforming_decrement: 0.08
    decay_rate: 0.05
    adaptation_rate: 0.05
    confrontation_threshold: 0.7
  scratchpad:
    max_entries: 20
    max_important_entries: 10
    injection_motivation: 3
    injection_dialogue: 2
```

**影响**: 灵魂附生机制的核心参数，直接影响游戏核心体验。  
**建议**: 新增「👻 灵魂附生」子页面，分为「融合」「不协和」「草稿纸」三区。

---

### 2.9 `desktop` 段 — ❌ 完全缺失

```yaml
desktop:
  window_width: 1280
  window_height: 800
  resizable: true
  fullscreen: false
```

**说明**: pygame 版使用，Web 版不适用。标记为「仅桌面版」。

---

### 2.10 `truncation` 段 — ❌ 完全缺失

```yaml
truncation:
  thread_context: 3000      # 线索上下文 Token
  llm_extract: 15000        # LLM 提取 Token
  scene_context: 4000       # 场景上下文 Token
  narrative_history: 2000   # 叙事历史 Token
```

**影响**: 控制各 Agent 注入的上下文窗口大小，直接影响 API 成本和推理质量。  
**建议**: 合并到「🧠 记忆系统」或独立「📐 Token 配额」子页面。

---

### 2.11 `reward` 段 — ❌ 完全缺失

```yaml
reward:
  enabled: true
  log_path: server/manana/metrics/reward_log.jsonl
  weights:
    auditor_score: 0.3
    micro_oracle_health: 0.2
    narrative_tension: 0.2
    canon_adherence: 0.2
    issue_penalty: 0.1
```

**影响**: 奖励跟踪和 Prompt 自优化的数据基础。  
**建议**: 新增「📊 奖励系统」子页面。

---

### 2.12 `prompt_optimization` 段 — ❌ 完全缺失（仅 feature toggle 存在）

```yaml
prompt_optimization:
  provider: strong
  high_reward_threshold: 0.7
  min_samples_for_optimization: 50
  optimization_interval: 50
```

**现状**: `features.prompt_optimization` 开关在管线配置中可见，但优化参数不可见。  
**建议**: 合并到「📊 奖励系统」或独立子页面。

---

### 2.13 `composer` 段 — ❌ 完全缺失

```yaml
composer:
  best_of_n:
    enabled: false
    sample_count: 3
    temperatures: [0.5, 0.7, 0.9]
```

**影响**: 编剧层 Best-of-N 候选策略。  
**建议**: 合并到「⚡ 管线配置」的功能开关区。

---

## 三、后端 API 支持情况

当前已暴露的 API 端点:

| 端点 | 方法 | 覆盖 |
|:--|:--|:--|
| `/api/config/features` | GET | features 段读取 |
| `/api/config/features` | PUT | features 段写入 |
| `/api/config/define` | GET | 配置定义（仅 features） |
| `/api/pipeline/nodes-meta` | GET | 管线节点元数据 |

**缺失的后端 API**:
- ❌ 无通用 `/api/config` GET（读取完整 config）
- ❌ 无分段写入 API（除 features 外所有段）
- ❌ `/api/config/define` 定义了所有段，但前端只用了 features

---

## 四、优化建议优先级

### 🔴 P0 — 高频使用，影响核心体验

| 段落 | 参数 | 理由 |
|:--|:--|:--|
| `memory` | 全部 15 个 | 记忆系统是 Rain 核心，直接影响叙事连贯性 |
| `game` | oracle_interval, auto_save_interval | 直接控制游戏节奏和数据安全 |
| `soul_possession` | 全部 12 个 | 核心玩法机制 |

### 🟡 P1 — 进阶调优

| 段落 | 参数 | 理由 |
|:--|:--|:--|
| `reflection` | check_* 4 个 | 角色一致性调优 |
| `emergence` | hit_threshold, max_pending_entities | 涌现行为控制 |
| `continuity` | max_rewrite | 重试次数控制 |
| `truncation` | 全部 4 个 | Token 预算控制（成本） |

### 🟢 P2 — 高级/低频

| 段落 | 参数 | 理由 |
|:--|:--|:--|
| `reward` | weights 5 个 | 高级调优 |
| `prompt_optimization` | 除 provider 外 4 个 | 自优化参数 |
| `composer` | best_of_n 3 个 | 实验性功能 |
| `providers` | timeout 3 个 | 高级参数 |

---

## 五、建议的新设置结构

```
⚙️ 设置
├── 🔌 API 设置          (现有 — 补 timeout)
├── ⚡ 管线配置          (现有 — 补 composer)
├── ⚔️ 游戏参数          (NEW — game + continuity)
├── 🧠 记忆系统          (NEW — memory + truncation)
├── 👻 灵魂附生          (NEW — soul_possession)
├── 🌱 涌现系统          (NEW — emergence)
├── ✨ 角色反思          (NEW — reflection)
├── 📊 奖励系统          (NEW — reward + prompt_optimization)
├── 🎨 UI 设置           (现有)
└── ℹ️  关于              (NEW — app 信息只读展示)
```
