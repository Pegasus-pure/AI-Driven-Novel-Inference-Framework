# Agentopia 深度分析 — 世界引擎层 (World Engine)

---

## 一、`src/world/world.py` — 顶级模拟调度器

**文件位置**：`E:\Agentopia\src\world\world.py`（1560 行）

**核心类**：`World`

### 1.1 初始化流程

```python
class World:
    def __init__(self, ..., resume_from=None):
        1. self.clock = Clock(...)              # 初始化时钟
        2. set_log_run_id(run_id)               # 设置运行日志 ID
        3. init_god_module(clock, data_dir)     # 初始化上帝模块
        4. 解析 resume 点 (checkpoint / 参数)
        5. clean_append_only_jsonl_before()     # 清理 resume 点之后的数据
        6. self.msg_center = MessageCenter(...) # 初始化消息中心
        7. self.agents = _init_agents_from_data() # 加载智能体
        8. 分配模型（均匀分布、持久化）
        9. 初始化位置存储（LocationStore）
        10. 初始化职位存储（PositionStore）
        11. 写入初始状态（W00-begin）
```

**关键设计**：
- 数据目录包含 run_id（例如 `school_06031205`），每次运行相互隔离
- 支持从 checkpoint 恢复（年 + 周）
- 恢复时自动清理恢复点之后的数据，确保幂等性
- 模型分配持久化到 `model_assignment.json`，恢复时保持一致性

### 1.2 主循环 `run()`

```python
for y in range(total_years):       # 逐年
    for week in range(1, n_week+1): # 每周
        self.clock.set_week(week)
        self.step()                  # 执行一周
        self._write_checkpoint(year, week)

    # 年末处理
    self._update_yearly_profiles()   # 更新所有智能体档案
    self._run_position_application_season()  # 职位申请季
    self._calculate_rewards()        # 奖励计算
```

### 1.3 每周流程 `step()`

```
step():
  ├─ _before_week_start()
  │   ├─ _apply_fulfillment_decay()    # 满足感衰减
  │   └─ _settle_weekly_income()      # 发放周薪
  │
  ├─ clear_on_week_start() → 清空智能体本周缓存
  │
  ├─ [PLAN] set_stage(PLAN)
  │   └─ agent.plan()                  # 每个智能体制定周计划
  │
  ├─ [BEFORE_CONTACT] set_stage(BEFORE_CONTACT)
  │   ├─ _generate_public_events()     # God Model 生成本周公共活动
  │   └─ agent.signup_public_events()  # 智能体签到公共活动
  │
  ├─ [CONTACT] set_stage(CONTACT)
  │   ├─ msg_center.clear()            # 清空消息中心
  │   └─ for slot in range(n_contact_slot):
  │       ├─ clock.set_slot(slot)
  │       └─ agent.contact()           # 智能体联络
  │
  ├─ [AFTER_CONTACT] set_stage(AFTER_CONTACT)
  │   ├─ msg_center.confirm_schedule()  # 确认联合活动
  │   └─ agent.finalize_contact()      # 智能体终结合
  │   └─ _generate_encounter_events()  # 生成偶遇事件（God Model）
  │
  ├─ [ACTIVITY] set_stage(ACTIVITY)
  │   └─ for day in range(1, n_day+1):
  │       └─ _build_today_activities_all_types()
  │           ├─ joint_acts            # 联合活动
  │           ├─ encounter_acts        # 偶遇活动
  │           ├─ public_acts           # 公共活动
  │           └─ solo_acts             # 单人活动
  │       └─ 并行执行所有活动（Semaphore 控制并发）
  │
  ├─ [REVIEW] set_stage(REVIEW)
  │   └─ agent.review()               # 每周回顾
  │
  └─ [SETTLE] set_stage(SETTLE)
      └─ agent.settle_week()          # 物品清理
```

### 1.4 并行执行设计

**Activity 阶段使用三层并发控制**：

```python
# Semaphore(max_concurrency) 控制总并发任务数
# Slot 分配：
#   - Joint/Encounter: 1 slot
#   - Solo: 1 slot
#   - Public: min(participants, internal_parallelism) slots

# 提价优先级：
# 1. Joint（慢，先占 slot）
# 2. Solo（快，填满剩余 slot）
# 3. Public（按参与人数升序，小活动先释放 slot）
```

### 1.5 活动构建 `_build_today_activities_all_types()`

从智能体日程中收集所有活动，按类型分组：

```python
# 1. 遍历所有智能体，获取今日日程
# 2. 按 type（joint/public/encounter）和 activity_id 分组
# 3. 分组验证：参与者必须完全匹配
# 4. 无任何活动的智能体 → SoloActivity
```

**优先级**：Encounter > Joint > Public（在 `agent.get_schedule()` 中处理）

---

## 二、`src/world/clock.py` — 时间系统

**文件位置**：`E:\Agentopia\src\world\clock.py`（351 行）

### TimeState

```python
@dataclass
class TimeState:
    year: int
    week: int
    stage: Stage     # 枚举：BEGIN=0 ~ SETTLE=7
    day: int = 0     # ACTIVITY 阶段使用
    slot: int = 0    # CONTACT 阶段使用

# 时间比较：year → week → stage → day/slot（完全有序）
# 字符串格式：
#   Y2020-W01-plan              → 计划阶段
#   Y2020-W01-contact-S3        → 联络阶段 slot 3
#   Y2020-W01-activity-D2       → 活动阶段第 2 天

# 重要方法：
TimeState.from_string(s)     # 解析时间串
TimeState.get_year_begin(y)  # 获取年初时间 Y{y}-W00-begin
TimeState.minus_x_weeks(x)   # 前推 x 周
```

### Clock

```python
class Clock:
    # 提供 set_*/get_time 接口
    # prev_contact_slot(): 获取前一个联络 slot（用于历史查询）
```

---

## 三、`src/world/god.py` — 上帝模型

**文件位置**：`E:\Agentopia\src\world\god.py`（2000+ 行）

**核心作用**：作为 Environment Model（环境模型），执行所有需要"世界级"判断的 LLM 调用。

### 3.1 功能模块

| 功能函数 | 用途 |
|---------|------|
| `env_and_nsp()` | 联合活动：生成环境反馈 + 指定下一发言者 |
| `evaluate_solo_activity()` | 评估单人活动结果 |
| `generate_consumption_offers()` | 生成消费场景和商品 |
| `evaluate_joint_activity()` | 评估联合活动所有参与者的变化 |
| `evaluate_public_activity()` | 评估公共活动所有参与者的变化 |
| `generate_public_events()` | 生成本周公活动 |
| `god_generate_encounter_events()` | 生成偶遇事件 |
| `god_design_positions()` | 初始职位设计 |
| `god_grow_positions()` | 年度职位扩张 |
| `god_evaluate_position_application()` | 职位申请评估 |
| `update_yearly_profile()` | 年度档案更新 |

### 3.2 后处理函数模式

每个 God 函数都遵循 **post-processing 模式**：

```python
# 1. 定义后处理函数（_pp_* 命名）
def _pp_parse_xxx(response, **kwargs) -> Optional[Dict]:
    # 解析 LLM 输出 → 验证格式 → 返回结构数据 or None（触发重试）

# 2. 使用 get_response_with_retry() 调用
data = get_response_with_retry(
    post_processing_funcs=[_pp_parse_xxx],
    model=config["god_model"],
    messages=messages,
    **kwargs  # 传递给后处理函数的额外参数
)
```

**后处理函数签名约定**：
- 输入：`response: str` + `**kwargs`
- 成功：返回 `dict`
- 失败：返回 `None`（触发重试）

### 3.3 关键函数详解

#### `env_and_nsp()` — 联合活动对话引擎

```python
# 输入：对话历史 messages + 参与者列表
# 输出：(raw_text, env_fdbk, speaker, verification)
# 功能：
# 1. 用 God Model 生成环境反馈
# 2. 决定下一发言者（或 <END CHAT> 结束对话）
# 3. 验证发言者是否在参与者列表中
# 4. 可选的 Verification 机制（验证上一发言者的响应质量）

# Fallback：speaker 无效时，使用确定性哈希随机选择
```

#### `split_response_by_visible_blocks()` — 对话可见性控制

```python
# 解析智能体响应中的可见性标签：
# <visible_to="A,B">内容</visible>  → 仅 A 和 B 可见
# <private>内容</private>            → 仅自己可见
# 无标签内容                         → 所有人可见

# 输出：[(blk_type, content, visible_group)]
# - blk_type: "public" | "group" | "private"
```

#### `evaluate_solo_activity()` — 两阶段评估

```
Stage 1: God Model 判断是否消费事件
  ├─ 消费事件 (is_consumption_event=true):
  │     → 进入 Stage 2 生成消费商品
  └─ 非消费事件:
        → 直接返回 outcome + deltas

Stage 2: 生成消费场景和商品（仅消费事件）
  ├─ 生成 outcome_text + 商品列表
  └─ 智能体选择购买 → 应用 deltas
```

#### `evaluate_joint_activity()` — 联合活动评价

```python
# 输入：活动背景 + 全对话历史 + 参与者信息
# 输出：Dict[agent_name → JointActivityOutcome]
# 每个 outcome 包含：delta_vitality, delta_fulfillment, delta_skills
# 应用配置中的 delta_limits 钳制
```

### 3.4 数据保存

每次 God Model 调用都会调用 `save_generation()` 保存两份数据：

```python
# 1. SFT 训练数据
data/{run_id}/god/{feature}/year={Y}/week={W}.jsonl

# 2. 验证日志
logs/verify/{run_id}/generations/{feature}.jsonl
```

---

## 四、`src/world/activity.py` — 活动执行引擎

**文件位置**：`E:\Agentopia\src\world\activity.py`（1562 行）

### 4.1 类层次

```
Activity (基类)
  ├── JointActivity    (多人交互对话)
  ├── SoloActivity     (单人行动)
  └── PublicActivity   (公共活动，并行执行)
```

### 4.2 `JointActivity.run()` — 联合活动执行流程

```
1. 初始化活动上下文
2. 记录活动前状态（验证用）
3. 初始化内存中物品列表（用于礼物转移）
4. 智能体进入活动 (enter_joint_activity)
5. 对话循环：
   ├─ God Model 生成环境反馈 + 指定下一位发言者
   ├─ 当前发言者行动 (act_in_activity)
   ├─ 解析礼物行为 (parse_gift_actions) → 立即执行
   ├─ 检查退出动作 (exit_activity())
   ├─ 可见性控制广播 (split_response_by_visible_blocks)
   └─ 直到 <END CHAT> 或达到 max_turns
6. God Model 评估所有参与者 (evaluate_joint_activity)
7. 各智能体接收结果 → 退出 → 应用状态变更 → 保存记录
```

**礼物系统**：
```python
# 格式: <role_action>gift(to="Alice", item="Book")</role_action>
# 验证: 发送者拥有该物品 + 接收者在活动中
# 执行: 实时更新内存中物品列表（不落地，在 APPLY 阶段一次写入）
# 记录: 在 outcome 中记录 items_sent / items_received
```

### 4.3 `SoloActivity.run()` — 单人活动流程

```
1. 智能体进入活动 (enter_solo_activity)
2. 智能体行动 (act_in_activity) → 提取 Activity: 内容
3. Stage 1: God Model 评估 → 非消费/消费
4. 非消费: 智能体接收 outcome
5. 消费事件: Stage 2 生成消费商品 → 智能体选择 → 购买处理
6. 智能体接收 deltas → 退出 → 应用状态 → 保存记录
```

**消费流程智能匹配**：
```python
# 智能体选择的物品名可能不精确匹配，分三阶段匹配：
# Stage 1: 严格匹配 (exact name)
# Stage 2: 包含匹配 (selected_name in opt.name)
# Stage 3: 模糊匹配 (difflib.get_close_matches)
```

### 4.4 `PublicActivity.run()` — 公共活动流程

类似 Solo 但支持大量参与者并行、群组划分：

```python
# >30 人: 2 组, >60 人: 3 组, >90 人: 4 组
# 智能体只能看到同组成员的参与情况
# EXIT 阶段可创建角色 scratchpad
```

### 4.5 `Activity._format_outcome_message()` — 结果格式化

```python
# 将 outcome 对象格式化为智能体能阅读的消息
# 包含：Vitality、Fulfillment、Skills、Money、Items 的变更
```

---

## 五、`src/world/scheduling.py` — 调度与消息中心

**文件位置**：`E:\Agentopia\src\world\scheduling.py`（896 行）

### 5.1 Schedule 数据类

```python
@dataclass
class Schedule:
    activity_id: Optional[str]       # 唯一标识（自动生成）
    activity_name: str               # 活动名称
    activity_time: TimeState         # 活动时间
    participants: List[str]          # 参与者
    type: "joint"|"solo"|"public"|"encounter"
    status: "created"|"canceled"|"failed"
    proposer: Optional[str]          # 提议者
    actions: Optional[Dict]          # 提议过程的动作记录
    location: Optional[str]          # 地点
    # ...（更多的可选字段）
```

**`make_activity_id()`**：统一 ID 生成
```python
# 格式: {type}-{time}-{identifier}
# 示例: joint-Y2024-W05-activity-D2-Alice-dinner
#       encounter-Y2024-W05-activity-D2-Alice-Bob
#       solo-Y2024-W05-activity-D3-Charlie
```

### 5.2 PublicEvent 数据类

```python
@dataclass
class PublicEvent:
    event_id: str                          # 唯一标识
    event_name: str                        # 事件名称
    start_year/start_week/start_day        # 起始时间
    repeat_weeks: int                      # 持续周数
    description: str                       # 描述
    eligible_participants: "all" | [names] # 可参与名单
```

### 5.3 MessageCenter — 消息中心

**消息处理流水线**：

```
add(msg)         → 追加原始消息（无处理验证）
confirm_schedule() → 执行联合活动调度确认
clear()          → 清空本周消息缓存
```

**`confirm_schedule()` 调度算法**（约 200 行，最复杂的调度逻辑）：

```
1. 预处理：解析 propose / respond / cancel 消息
2. 构建提案索引：proposer+activity_name → Proposal
3. 处理取消：cancel 时间必须 >= propose 时间
4. 匹配响应：
   - 精确匹配 (proposer + activity_name)
   - 回退匹配 (同提议者的最近提案)
5. 时间冲突解决：
   - 每人每时间槽保留最高优先级安排
   - 优先级: existing_joint > prop > resp > existing_lower
6. 决策：
   - 创建条件：提议者参与 + 所有必需者接受 + 至少 2 人
7. 输出：各参与者看到各自的活动安排（含取消/失败记录）
```
