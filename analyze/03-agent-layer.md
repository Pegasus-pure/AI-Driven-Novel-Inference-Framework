# Agentopia 深度分析 — 智能体层 (Agent Layer)

---

## 一、`src/agents/role_agent.py` — 角色扮演智能体核心

**文件位置**：`E:\Agentopia\src\agents\role_agent.py`（约 1794 行）

**核心类**：`RoleAgent`

### 1.1 构造函数

```python
class RoleAgent:
    def __init__(self, name, clock, msg_center, model, *, world_name, ...):
        self.dm = DataManager(...)       # 数据管理器
        self.msg_center = msg_center      # 共享消息中心
        self._opened_scratchpads = set()  # 已读 scratchpad 追踪
        self.proposed_activities = {}     # 本周已提议的活动
```

### 1.2 核心流程方法

#### 每周阶段入口

| 方法 | 调用阶段 | 功能 |
|------|---------|------|
| `plan()` | PLAN | 制定本周计划 + 选择生活标准 |
| `signup_public_events()` | BEFORE_CONTACT | 签到公共活动 |
| `contact()` | CONTACT | 发送/接收消息、提议/回复联合活动 |
| `finalize_contact()` | AFTER_CONTACT | 确认联合活动、总结联络阶段 |
| `enter_joint_activity()` | ACTIVITY | 进入联合活动 |
| `act_in_activity()` | ACTIVITY | 在活动中发言/行动 |
| `exit_activity()` | ACTIVITY | 退出活动并生成总结/反思 |
| `review()` | REVIEW | 每周回顾并写入日记 |
| `settle_week()` | SETTLE | 清理多余物品 |

### 1.3 生成与验证流程 (`_generate_with_functions`)

这是 RoleAgent 的核心方法，执行 **工具增强的 LLM 生成循环**：

```python
def _generate_with_functions(self, inputs, *, max_rounds=8, ...):
    # 1. 循环：最多 max_rounds 轮
    for _ in range(max_rounds):
        # 2. 调用 LLM (generate_with_fc)
        output = generate_with_fc(model, messages, functions, ...)
        outputs.extend(output)

        if is_gen_finished(output):      # 无 tool_calls → 结束
            break
        else:
            for item in output:
                if tool_calls in item:
                    # 3. 去重工具调用
                    item["tool_calls"] = dedupe_tool_calls(item["tool_calls"])
                    for fc in item["tool_calls"]:
                        # 4. 执行工具（读/写 scratchpad）
                        func_res = self._exec_function(fc_name, fc_args)
                        outputs.append({"role": "tool", ...})

    # 5. 响应验证循环（可选）
    #    格式校验 → 原则校验 → 重试/重建上下文
    if format_validator and config["response_validation"]["enabled"]:
        result = run_validation_loop(...)
        outputs = result.outputs

    # 6. 后处理：完整推理摘要 + 保存
    return outputs
```

**关键设计点**：
- 最后 1 轮（`max_rounds - 1`）强制 `tool_choice = "none"`，确保最终输出文本
- 工具调用去重：相同（name + arguments）的调用只执行一次
- 更新 scratchpad 前必须已读过（`_opened_scratchpads` 追踪）
- 响应验证循环支持最多 3 次重试，失败时重建 reasoning 上下文

### 1.4 联络系统 (Contact System)

**5 种角色动作**（通过 `<role_action>` XML 标签解析）：

| 动作类型 | 参数 | 功能 |
|---------|------|------|
| `contact` | to, message | 发送一对一消息 |
| `propose_joint_activity` | activity_name, invited_persons, time, location | 提议联合活动 |
| `respond_invitation` | activity_name, to, decision | 回复邀请（yes/no） |
| `cancel_joint_activity` | activity_name, message | 取消提议 |
| `gift` | to, item | 赠送物品（活动中） |

**动作解析器** (`_parse_role_actions`)：
```python
# 使用正则提取 <role_action>content</role_action>
# 然后解析 content = "action_name(k1=v1, k2=v2)"
# 使用 parse_kv_args() 解析键值对
items: List[Dict] = []  # [{act, type, args}, ...]
```

**动作执行流水线**：
1. `contact()` 生成响应文本
2. `_parse_role_actions()` 解析所有 role_action
3. 按类型分派到对应的 handler（_handle_contact_action 等）
4. 消息通过 `MessageCenter` 广播给其他智能体
5. 在本地的 `{world}/persona/{name}/contact/{other}.jsonl` 持久化

**速率限制**：每个 contact slot 最多 `n_action_per_slot` 次动作（来自配置）

### 1.5 活动引擎交互

**联合活动 (Joint Activity) 流程**：
```
enter_joint_activity()
  ├─ meet_person() → 自动创建角色 scratchpad
  ├─ 生成活动分析 (on_enter_activity=True)
  └─ 构建活动上下文

act_in_activity()  — 每一轮调用一次
exit_activity()    — 生成总结 + 反思
```

**个人活动 (Solo Activity) 流程**：
```
enter_solo_activity()   — 构建上下文
act_in_activity()       — 生成行动计划
  └─ response_validator.validate_solo_activity_format() 校验 "Activity:" 格式
exit_activity()         — 只生成反思（无总结）
```

### 1.6 生活标准系统

`plan()` 阶段，智能体从输出中提取 `<living_standard>` 标签：

```python
<living_standard>frugal|moderate|comfortable|luxurious</living_standard>

# 效果（每周）：
# frugal:     cost=100,  material=-5
# moderate:   cost=200,  material=0
# comfortable:cost=300,  material=+5
# luxurious:  cost=500,  material=+10

# 余额不足 → 自动降级到 frugal
```

### 1.7 社交排名 (Social Ranking)

`judge_others()` 方法让智能体评价认识的其他人：

- 使用 **God Model**（而非 Role Model）确保公平一致
- 评价维度：affection（好感度） 和 respect（尊重度），各 0-100 分
- 评分数据 -> PageRank -> 社会奖励
- 响应经过 `ranking_validator` 校验（JSON 格式检查）

---

## 二、`src/agents/data_manager.py` — 数据管理器

**文件位置**：`E:\Agentopia\src\agents\data_manager.py`（约 2100 行，第二大文件）

**核心类**：`DataManager`

### 2.1 数据目录结构

```
data/{world}/persona/{name}/
├── generation/year={YYYY}/week={W}.jsonl      # LLM 生成轨迹
├── profile/year={YYYY}.json                   # 年度档案快照 (覆盖写入)
├── state.jsonl                                # 状态历史
├── schedule.jsonl                             # 日程历史
├── activity.jsonl                             # 活动记录
├── reward.jsonl                               # 奖励记录
├── memory/
│   ├── weekly_diary.jsonl                     # 每周日记
│   ├── scratchpad/
│   │   ├── general.jsonl                      # 通用笔记
│   │   ├── characters/{who}.jsonl             # 对某人的认知
│   │   └── others/{topic}.jsonl               # 其他主题笔记
│   └── history.jsonl                          # 长期历史
└── contact/
    ├── {person}.jsonl                         # 与某人的通信
    └── sig.jsonl                              # 通信信号
```

### 2.2 JSONL 读写 — `_read_jsonl` 和 `_append_jsonl`

**读取**：
```python
def _read_jsonl(self, path, max_lines=None, max_weeks=None, exact_t=None, *,
                at_t=None):
    # - 使用 FileReadBackwards 从文件末尾反向读取（最新的数据在后）
    # - 支持时间窗口过滤（max_weeks）和行数限制（max_lines）
    # - 从 cur_t 开始反向查找，满足条件后正向收集
    # - 支持精确时间点查询 (exact_t)
```

**写入**：
```python
def _append_jsonl(self, path, obj):
    # - 添加 time 字段（当前时钟时间）
    # - 通过 fcntl.flock 实现文件级互斥锁
    # - 检查时间有序性：新条目 >= 末条记录时间
    # - 自动修复文件末尾缺少换行符的问题
```

### 2.3 状态管理

**状态架构**：
```python
state = {
    "vitality": 70,           # 体力 0-100
    "fulfillment": {          # 满足感 0-100
        "mood": 50,           #   情绪
        "material": 50,       #   物质
        "social": 50,         #   社交
        "esteem": 50,         #   自尊
    },
    "skills": {},             # 技能
    "assets": {
        "deposit": 0,         # 存款
        "possessions": [],    # 物品列表
    },
}
```

**关键操作**：
- `read_state()`：读取最近的 state 快照
- `save_state()`：追加写入新的 state 快照
- `apply_fulfillment_decay()`：每周期应用满足感衰减（比例衰减）
- `update_deposit()` / `update_possessions()`：更新资产
- `get_fulfillment_history()`：获取历史的满足感序列（用于主观奖励计算）

### 2.4 提示词生成方法

DataManager 提供一系列 `*_prompt()` 方法，为不同阶段构建 LLM 输入：

```python
roleplay_prompt()       # 基础角色提示（Persona + Worldview + Scratchpads + History + Time）
plan_prompt()           # 周计划提示
signup_prompt()         # 公共活动签到提示
contact_prompt()        # 联络阶段提示
activity_prompt()       # 活动执行提示
review_prompt()         # 周回顾提示
settle_prompt()         # 物品清理提示
```

每个方法都组装多个提示片段（schedule + roleplay + 阶段特定指令），以 `\n\n` 分隔。

### 2.5 通讯机制

```
send_message(to, content):
    1. 写入我的 data/{world}/persona/{me}/contact/{to}.jsonl
    2. 写入对方的 data/{world}/persona/{to}/contact/{me}.jsonl
    3. 写入双方的 data/{world}/persona/*/contact/sig.jsonl（信号统一日志）
```

---

## 三、`src/agents/prompts.py` — 提示词模板库

**文件位置**：`E:\Agentopia\src\agents\prompts.py`（约 23732 tokens，分片读取）

**核心作用**：包含所有 LLM 提示词模板，是系统行为定义的"中枢神经"。

### 关键模板

| 模板常量 | 用途 |
|---------|------|
| `PERSONA_TEMPLATE` | 角色档案模板（姓名、年龄、外观、个性、技能等） |
| `WORLDVIEW` | 世界观描述 |
| `ROLEPLAY_PRINCIPLES` | 角色扮演原则 |
| `SCRATCHPAD_PROMPT` | 笔记模板 |
| `COMMONSENSE` | 常识指导 |
| `REQUIREMENTS` | 通用输出格式要求 |
| `PLAN_PROMPT` | 每周计划提示 |
| `CONTACT_PROMPT` | 联络阶段提示 |
| `SOLO_ACTIVITY_PROMPT` | 个人活动提示 |
| `JOINT_ACTIVITY_PROMPT` | 联合活动提示 |
| `PUBLIC_ACTIVITY_PROMPT` | 公共活动提示 |
| `REVIEW_PROMPT` | 每周回顾提示 |
| `GOD_PROMPT_JOINT_ACTIVITY` | 上帝模型联合活动评价提示 |
| `GOD_PROMPT_JOINT_ACTIVITY_WITH_VERIFICATION` | 含验证的上帝模型提示 |
| `END_SIGN` | 对话结束标记 ("<END CHAT>") |

提示词模板使用 Python 的 `str.format()` 进行变量注入。

---

## 四、`src/agents/functions.py` — 工具函数注册

**文件位置**：`E:\Agentopia\src\agents\functions.py`（187 行）

**简洁但关键**的模块：定义 LLM 可调用的工具函数 schema。

```python
FUNCTIONS = {
    "list_scratchpads": {...},     # 列出所有笔记
    "read_scratchpad": {...},      # 读取笔记内容
    "update_scratchpad": {...},    # 创建/更新笔记
}
FUNCTION_SETS = ["list_scratchpads", "read_scratchpad", "update_scratchpad"]
```

**`dedupe_tool_calls()`**：按 (name, arguments) 去重，保留首次出现。

注意：`read_map` 和 `read_diary` 等功能已被注释掉，说明设计从"智能体主动调用"转向"自动注入上下文"。

---

## 五、`src/agents/context.py` — 对话上下文管理

**文件位置**：`E:\Agentopia\src\agents\context.py`（91 行）

**核心类**：`ConversationContext`

**作用**：在 token 预算内准备聊天消息，使用启发式摘要（不调用 LLM）。

```python
def pack(self, *, system_prompt, history, user_turn) -> List[Dict]:
    budget = model_ctx_tokens - target_response_tokens
    # 1. 全部加入 → 检查是否超限
    # 2. 超限则压缩：保留后半历史，前半拼接为 summary
    # 3. 仍超限则只保留最近 3 轮对话
```

---

## 六、`src/agents/response_validator.py` — 响应验证系统

**文件位置**：`E:\Agentopia\src\agents\response_validator.py`（约 554 行）

**提供**：格式验证 + 原则验证 + 上下文重建 的验证循环。

### 6.1 验证类型

1. **格式检查** (`validate_activity_tags`)：检查 `<private>` 和 `<visible_to>` 标签闭合
2. **原则检查** (`validate_principles`)：使用独立 Judge Model 评估是否符合角色扮演原则
3. **单人活动格式** (`validate_solo_activity_format`)：检查是否包含 `Activity:` 部分

### 6.2 验证循环 (`run_validation_loop`)

```python
for attempt in range(max_retries + 1):  # 默认最多 3 次重试
    # 1. 格式检查 + 原则检查
    # 2. 全部通过 → 如有重试则重建上下文 → 返回
    # 3. 未通过且 attempt < max_retries → 将反馈发给模型重新生成
    # 4. 达到最大重试 → 使用最后的结果
```

### 6.3 上下文重建 (`rebuild_context`)

当验证失败后重试成功时，原始推理过程已不匹配最终输出，需重建：

```
原始推理 [A → B → C]  →  (验证失败) → 重试 → 最终回答 D
                                                      ↓
重建推理 [A' → B' → C' → D]   ← 新的推理自然导向 D
```

使用单独的 LLM 调用，以原始推理风格生成新的 `<rebuilt_reasoning>`。
