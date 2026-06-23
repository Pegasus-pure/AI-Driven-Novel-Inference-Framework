# Agentopia 的优秀编码习惯 — 来自 Agentopia 的经验，适用于你的项目

> 以下习惯全部提取自 Agentopia 源代码，有具体文件名和行号可查。
> 建议：把这些作为团队的编码规范，逐一落实到 Code Review 检查清单中。

---

## 一、类型系统与数据契约

### 习惯 1：`from __future__ import annotations` 放在每个文件第一行

**Agentopia 中 19/23 个源文件都用了**，包括 clock.py、reward.py、world.py、god.py 等所有核心模块。

**为什么好**：
- 所有类型注解变为字符串，Python 运行时不再评估它们
- 消除了循环导入（circular import）问题
- 支持前向引用（forward reference），写 `-> "RoleAgent"` 而不必导入

```python
# rewards.py（好习惯）
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.agents.role_agent import RoleAgent

class SocialMetrics:
    avg_affection_from_others: float   # 类型在 class body 中定义
```

**你的项目这样做**：所有 `.py` 文件的第一行 non-blank 代码都写 `from __future__ import annotations`

---

### 习惯 2：数据用 `@dataclass` 定义，不用裸 dict

**Agentopia 中用了 26 个 @dataclass**，覆盖 `TimeState`、`SocialRanking`、`Schedule`、`JointActivityOutcome` 等所有核心数据结构。

```python
# clock.py — TimeState
@functools.total_ordering
@dataclass
class TimeState:
    year: int
    week: int
    stage: Stage
    day: int = 0
    slot: int = 0

    def __lt__(self, other): ...  # 支持排序
    def __str__(self): ...         # 格式化输出
    @classmethod
    def from_string(cls, s): ...   # 反序列化
```

```python
# reward.py — SocialReward
@dataclass
class SocialReward:
    agent_name: str
    time: str
    affection_score: float
    respect_score: float
    combined_score: float

    @staticmethod
    def from_dict(d): ...  # 从 dict 反序列化的标准工厂方法
```

**为什么好**：
- 类型是自文档的：一眼看出结构
- IDE 支持自动补全和重构
- `asdict()` 直接序列化为 JSON
- 不会被拼写错误的 key 破坏（dict 访问 `["afection"]` 不会报错）

**你的项目这样做**：
1. 核心数据全部 `@dataclass`
2. 提供 `from_dict()` 反序列化方法
3. 用 `asdict()` 序列化

---

### 习惯 3：函数签名必须有完整的类型注解

**Agentopia 中每个函数都有完整类型注解**，从 utils.py 到 world.py 无一例外。

```python
# reward.py
def calculate_social_rewards(
    affection_graph: SocialGraph,
    respect_graph: SocialGraph,
    time_str: str,
    all_agent_names: Optional[List[str]] = None,
) -> Dict[str, SocialReward]:
```

```python
# world.py
def step(self) -> None:
def _build_today_activities_all_types(
    self, n_activity_day: int
) -> Dict[str, List[Activity]]:
```

**为什么好**：
- 调用者不需要翻看文档就知道参数类型
- IDE 静态检查能拦截类型不匹配
- 重构时修改参数类型会产生编译警告

**你的项目这样做**：
- 所有函数参数加类型注解
- 所有返回值加类型注解
- 可选参数用 `Optional[Type]` / `Type | None`

---

## 二、模块与文件组织

### 习惯 4：一个文件只做一件事，严格控制文件大小

**Agentopia 的文件分布**：
```
src/world/ 下 12 个文件，每个职责分明：
  clock.py       (351行, 仅时间系统)
  reward.py      (1089行, 仅奖励计算)
  scheduling.py  (896行, 仅调度+消息)
  activity.py    (1562行, 仅活动执行)
  god.py         (2000+行, 仅 God Model)
  locations.py   (仅位置管理)
  mapgen.py      (仅地图生成)
  cleanup.py     (仅数据清理)
  ...
```

**Rain-web 对比**：pipeline.py 一个文件 1,936 行包揽 14 级管线。

**为什么好**：
- 定位代码快：你要找"奖励计算"就去 reward.py
- 单元测试聚焦：一个文件一个测试文件
- git diff 可读：改 reward.py 就是改奖励系统

**你的项目这样做**：
- 一个新功能 → 至少一个新文件
- 文件超过 800 行→ 思考能否拆分
- 一个函数超过 100 行 → 要拆

---

### 习惯 5：路径和配置不硬编码，全部集中到 config.py + paths.py

```python
# config.py
_CONFIG: Dict[str, Any] | None = None

def get_config() -> Dict:
    """全局配置访问点，全部从 config.json 读取"""

# 使用方式（任意位置）：
config = get_config()
n_week = config["world"]["time"]["n_week"]
reward_cfg = config["world"]["reward"]
damping = reward_cfg["pagerank_damping"]
```

**对比 Rain-web** 中 `add_scene_memory` 硬编码 5 条、embedding 模型硬编码 `nomic-embed-text`。

**为什么好**：
- 修改配置不修改代码
- 不同运行场景用不同配置文件
- 上线后调参不需要部署新版本

**你的项目这样做**：
- 所有可调参数放到 config 文件
- `get_config()` 全局访问点，惰性加载
- 敏感字段用 `_redact_secrets()` 脱敏打印

---

## 三、函数级编码习惯

### 习惯 6：纯函数优先

**Agentopia 的奖励系统全是纯函数**：

```python
# reward.py
def ranking_to_weights(ranking: List[str], max_score: float = 100.0) -> Dict[str, float]:
    """输入排序列表 → 输出权重字典，无副作用"""

def pagerank(graph: SocialGraph, ...) -> Dict[str, float]:
    """输入社交图 → 输出 PageRank 分数，不修改输入"""

def build_social_graphs(rankings: List[SocialRanking]) -> Tuple[SocialGraph, SocialGraph]:
    """纯转换函数"""
```

**为什么好**：
- 纯函数极易测试：给定输入，断言输出
- 纯函数容易缓存：相同输入永远相同输出
- 纯函数可并行：无共享状态
- 问题定位精确：错误一定在输入 → 输出链中

**你的项目这样做**：
- 业务逻辑优先写为纯函数
- 需要副作用（数据库/磁盘）的写在调用者的外层
- `def function(data: InputType) -> OutputType:` 模式

---

### 习惯 7：有意义的错误信息 + 断言

```python
# 好习惯 — 错误信息说清楚问题 + 期望
raise ValueError(
    f"Agent '{name}' has no fulfillment history - data error"
)

raise ValueError(
    f"Agent set mismatch: social={len(social_agents)}, "
    f"subjective={len(subj_agents)}, economy={len(econ_agents)}"
)

# 断言 + 原因说明
assert x >= 1, f"minus_x_weeks requires x >= 1, got {x}"
assert pos is not None, (
    f"Agent {agent_name}'s position {self.original_positions[agent_name]} "
    f"not found in store"
)
```

**为什么好**：
- 线上出问题时，错误信息直接告诉你"缺 agent 数据"而不是 "KeyError"
- 断言包含前置条件说明，维护者也敢改代码

**你的项目这样做**：
- 每个 `raise` 都带上下文
- 每个 `assert` 都带理由
- 绝不写 `raise Exception("error")`——那等于什么也没说

---

### 习惯 8：文档字符串说"是什么+为什么"，不只是"参数列表"

```python
# clock.py
@staticmethod
def get_year_begin(year: int) -> str:
    """Return the year-begin time string: Y{year}-W00-begin.

    This represents the start of a year, before any week has begun.
    Used for Return/Advantage calculations where we need a baseline
    before the first reward is calculated.
    """

# reward.py
def calculate_advantages(returns):
    """Calculate advantages from returns over a time period.

    Advantage measures state improvement: A_{period} = Return_end - Return_start

    Timeline and advantage mapping:
        Timeline:  |----Year 1----|----Year 2----|----Year 3----|
                   ^              ^              ^              ^
                Return_0       Return_1       Return_2       Return_3
    """
```

**注意**：
- 第一行：一句话说明功能
- 第二段：用 ASCII 图/例子来说明"为什么需要这个函数"

**你的项目这样做**：
- 公共函数和复杂函数必须带 docstring
- docstring 的"为什么"部分比"是什么"更重要
- 算法逻辑（如 PageRank、调度算法）要画出流程图或示例

---

## 四、架构与设计模式

### 习惯 9：三层分离 — 调度层不关心执行细节

**Agentopia 的 World 是纯调度器**：

```python
# world.py — World 只负责"什么阶段做什么"
for y in range(total_years):
    for week in range(n_week):
        self.step()  # 按阶段推进

def step(self):
    self._before_week_start()         # 前置处理（收入/衰减）
    agent.plan()                      # 计划阶段
    self._generate_public_events()    # 公共事件
    agent.signup_public_events()      # 签到
    agent.contact()                   # 联络
    ...
    Activity.run()                    # 活动执行
    agent.review()                    # 回顾
    agent.settle_week()               # 结算
```

**World 不知道 RoleAgent 内部如何执行 `plan()` 或 `contact()`**——它只关心"调用了"和"调完了"。

**你的项目这样做**：
- 调度层只负责流程编排
- 执行层只负责具体逻辑
- 调度层不 import 执行层的内部细节

---

### 习惯 10：用 IntEnum 定义有序枚举，替代字符串比较

```python
# clock.py
class Stage(IntEnum):
    BEGIN = 0
    PLAN = 1
    BEFORE_CONTACT = 2
    CONTACT = 3
    AFTER_CONTACT = 4
    ACTIVITY = 5
    REVIEW = 6
    SETTLE = 7
```

**为什么好**：
- 用数字比较比字符串效率高
- 可以排序（`Stage.CONTACT > Stage.PLAN` 返回 True）
- IDE 自动补全，杜绝拼写错误
- 反例：Rain-web 用中文 dict key `"导演层"`，一旦拼错不报错

**你的项目这样做**：
- 有限状态集合 → IntEnum
- 绝不把状态存为字符串做比较

---

### 习惯 11：函数注册表 + 预处理/后处理模式

**Agentopia 中 God Model 的后处理模式**：

```python
# 每个 God 函数都遵循：调用 LLM → 后处理校验 → 失败重试
def _validate_ranking_response(response: str, **kwargs) -> Optional[Dict]:
    """后处理函数：解析 JSON + 校验字段 + 返回结构数据"""
    data = extract_json(response, **kwargs)
    if not data or not isinstance(data, dict):
        return None       # 返回 None = 触发重试
    ...
    return result         # 返回 Dict = 成功

# 使用方式：
data = get_response_with_retry(
    post_processing_funcs=[_validate_ranking_response],
    model=config["god_model"],
    messages=messages,
    known_names=valid_names,  # 传递给后处理器的额外参数
)
```

**你的项目这样做**：
- LLM 调用或外部 API 调用用"后处理校验 → 失败重试"模式
- 后处理函数可以自由组合（`[check_format, check_content]`）
- 将校验逻辑与调用逻辑分离

---

### 习惯 12：去重、排序用确定性的哈希

```python
# functions.py
def dedupe_tool_calls(tool_calls: List[dict]) -> List[dict]:
    """按 (name, arguments) 去重，保留首次出现顺序"""
    seen: Set[Tuple[str, str]] = set()
    unique: List[dict] = []
    for fc in tool_calls:
        key = (fc["function"]["name"], fc["function"]["arguments"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(fc)
    return unique

# position_application.py
def _deterministic_hash(seed: str, item: str) -> str:
    """使用 SHA256 确保跨运行一致性"""
    payload = f"{seed}-{item}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

**为什么好**：
- LLM 有时会生成重复调用 → 必须去重
- Python 的 dict/set 顺序在不同运行间不保证 → 确定性哈希修复
- 结果可重现，调试友好

---

## 五、数据与持久化

### 习惯 13：JSONL 追加写入 + 时间有序性校验

```python
# data_manager.py
def _append_jsonl(self, path: Path, obj: dict) -> None:
    """追加写入 JSONL，校验时间有序性"""
    if path.exists():
        last_line = self._fast_read_last_line(path)
        if last_line:
            last_record = json.loads(last_line)
            last_time = last_record.get("time", "")
            if new_time < last_time:
                raise ValueError(
                    f"Time order violation: new={new_time} < last={last_time} "
                    f"in {path}"
                )
    ...
```

**为什么好**：
- 追加写入是 O(1) 操作
- 天然的不可变日志（不修改历史）
- 时间有序性校验确保数据完整性
- 崩溃不丢失已写入数据

**你的项目这样做**：
- 事件日志用 JSONL 追加写入
- 写入前校验时间有序性
- 快照/状态才用覆盖写入（JSON）

---

### 习惯 14：数据清理支持可恢复性

```python
# cleanup.py
def clean_append_only_jsonl_before(path, time):
    """清理 append-only JSONL 中 time >= 指定时间之后的数据。
    
    用于 checkpoint 恢复场景：从恢复点之后的数据不可信 -> 删除。
    """
```

**为什么好**：
- 支持模拟中断后从最近 checkpoint 恢复
- 恢复时自动清理恢复点之后的数据 → 幂等
- 不需要每次都从头运行

---

## 六、日志与调试

### 习惯 15：分级日志 + 特征验证日志

```python
# utils.py
logger = get_logger(f"agent_{name}")       # 普通日志 → logs/{run_id}/agent_{name}.log
verify_logger = get_verify_logger("reward") # 特征日志 → logs/verify/{run_id}/reward.log
error_logger = get_logger("error")          # 错误日志 → logs/{run_id}/error.log

# reward.py 中使用
verify_logger.info(
    f"[VERIFY-REWARD] {name} subjective: score={score:.3f}, n_penalties={n_penalties}"
)
```

**为什么好**：
- 普通日志不会因特征日志的细节而过长
- 特征日志可以针对性输出，开发期开启、生产期关闭
- 分级清晰：正常 / 验证 / 错误

**你的项目这样做**：
- get_logger("module") 按模块分文件
- get_verify_logger("feature") 特征开发
- get_logger("error") 统一错误日志

---

## 七、总结：你可以直接复制的 10 条编码规范

| # | 规范 | 具体做法 |
|---|------|---------|
| 1 | **类型优先** | 每个文件加 `from __future__ import annotations`，所有函数写类型注解 |
| 2 | **数据用 dataclass** | 核心结构不用裸 dict，提供 `from_dict()` / `asdict()` |
| 3 | **纯函数核心** | 业务逻辑写纯函数，副作用放在调用层 |
| 4 | **IntEnum 替代字符串** | 所有有限状态、类型用枚举 |
| 5 | **先契约后实现** | 先定义 `SocialReward` 等 dataclass，再写逻辑 |
| 6 | **断言带理由** | `assert x, f"因为 {x} 不满足 {condition}"` |
| 7 | **一个文件一个职责** | 超过 800 行考虑拆分 |
| 8 | **JSONL 追加写入** | 日志、事件用 JSONL，不可变 + 校验时间有序 |
| 9 | **分层调度** | 调度层（World）不知道执行层（Agent）内部细节 |
| 10 | **确定性哈希** | 依赖排序的场景用 SHA256 代替 Python 随机化 |
