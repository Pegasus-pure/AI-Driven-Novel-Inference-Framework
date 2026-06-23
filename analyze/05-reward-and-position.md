# Agentopia 深度分析 — 奖励系统与职位系统

---

## 一、`src/world/reward.py` — 奖励计算系统

**文件位置**：`E:\Agentopia\src\world\reward.py`（1089 行）

**核心作用**：计算三个维度的奖励并合成为总 reward，作为 RLHF 优化的目标函数。

### 1.1 奖励架构

```
Reward System
├─ Social Reward     40%  — PageRank on 好感度/尊重度 社交图
├─ Subjective Reward 40%  — 满足感历史 + 痛苦惩罚
└─ Economy Reward    20%  — 存款变化量

总奖励 = w_social * social_z + w_subj * subj_z + w_econ * econ_z
所有分量先 Z-score 归一化后再加权组合
```

### 1.2 数据类层次

```python
@dataclass SocialRanking      # 单个智能体对他人的评价输入
@dataclass SocialReward       # 社会奖励输出（PageRank 分数）
@dataclass SocialMetrics      # 绝对社会指标（跨运行可比）
@dataclass SubjectiveReward   # 主观奖励（满足感 + 痛苦惩罚）
@dataclass TotalReward        # 加权组合
```

### 1.3 PageRank 实现

```python
def pagerank(graph, damping=0.85, max_iter=100, tol=1e-6,
             mutual_affection_alpha=0.0):
    # 1. 收集所有节点
    # 2. 初始化均匀分布
    # 3. 归一化出边权重
    # 4. 迭代 PageRank：PR(t+1) = (1-d)/N + d * Σ(PR(src) * weight)
    # 5. 互惠好感度增强（post-convergence）：
    #    S_I' = Σ_j (w_ji × (1 + α × w_ij) × S_j)
    #    → 如果你喜欢的人同时也喜欢你，你获得额外分数
```

**互惠好感度增强（Mutual Affection）** 是 PageRank 的改进：不仅考虑谁被很多人喜欢（PageRank 中心度），还考虑"喜欢我的人是否也互相喜欢"。

### 1.4 主观奖励计算

```python
def compute_subjective_rewards(agents, time_str):
    # Phase 1: 收集所有智能体所有维度的满足感值
    # Phase 2: 计算每个维度的痛苦阈值（底部分位数）
    # Phase 3: 对低于阈值的值施加惩罚：
    #   adjusted_value = value - penalty_value
    #   同时考虑活力（vitality）维度

    # 示例：threshold_percentile=0.25, penalty_value=5
    # 若某维度的底部 25% 分位数 = 30，则值 <30 时扣 5 分
```

### 1.5 经济奖励

```python
# 计算年度存款变化
economy_scores[agent.name] = deposit_end - deposit_start
# 简单直接：你的财富增长 = 你的经济奖励
```

### 1.6 Return 和 Advantage 计算（RL 优化用）

```python
def calculate_returns(reward_history, normalize=True):
    # 使用折扣因子 gamma=0.90
    # 从后向前计算: Return_t = reward_t + γ * Return_{t+1}
    # 前置虚拟时间点 (W00-begin, reward=0)
    # normalize: 除以折扣有效步数，使不同时间点的 return 可比

def calculate_advantages(returns):
    # Advantage_t = Return_{t+1} - Return_t
    # 衡量每个时间段的状态改善

def select_top_trajectories(advantages, top_fraction=1/3):
    # 选择优势最高的轨迹用于训练
```

---

## 二、`src/world/position_application.py` — 职位申请系统

**文件位置**：`E:\Agentopia\src\world\position_application.py`（约 1200 行）

### 2.1 Position 数据类

```python
@dataclass Position:
    organization: str           # 组织（如 "Fudan High School"）
    role: str                   # 角色（如 "English Teacher"）
    type: "work" | "non-work"   # 类型
    description: str            # 描述
    weekly_income: int          # 周薪
    weekly_delta_skills: Dict   # 每周技能增长
    min_age/max_age: Optional   # 年龄限制
    min_skills: Optional[Dict]  # 最低技能要求
    capacity: int               # 总容量
    occupied_by: List[str]      # 当前在职者
    created_year: Optional[int] # 创建年份
```

### 2.2 职位申请季流程

```
1. 创建 PositionApplicationContext
2. 记录所有智能体的原始职位 + 计算明年年龄
3. 收集愿望 (Collect Wishes)：
   ├─ 每个智能体可选最多 3 个职位
   ├─ <STAY_CURRENT> = 保持当前职位
   ├─ aging-out 职位对智能体不可见
   └─ 并行执行（ThreadPoolExecutor）
4. Round 1 (Wish Round) — 3 个子轮：
   ├─ Sub-round 1: 处理第 1 志愿（未匹配的竞争）
   ├─ Sub-round 2: 处理第 2 志愿
   └─ Sub-round 3: 处理第 3 志愿
5. 最终确认：
   ├─ 未匹配 → 回退到原始职位
   ├─ aging-out + 未匹配 → 失业
   └─ 批量更新 occupied_by + 智能体档案
6. 更新同事关系（最多 10 人）
7. 计算成就奖励
```

### 2.3 "1.5 轮"匹配机制

```python
# 批次处理策略：
# 1. 按受欢迎程度排序（申请人数量降序，薪资降序）
# 2. 分批：每批最多 20 个申请人
# 3. God Model 在批次内做智能匹配
# 4. 使用确定性哈希确保可重复性

def _sort_positions_by_popularity(nth_wishes, all_positions, seed):
    # 申请人多的优先处理
    # 薪资高的作为 tiebreaker

def _batch_positions_by_applicant_count(positions, nth_wishes, max_total=20):
    # 将职位分批，每批总申请人 ≈ max_total
```

### 2.4 成就奖励

```python
def calculate_achievement_rewards(ctx):
    # 对每个智能体的新职位计算 sum(min_skills)
    # 排名后转换为 0-100 分
    # 使用 reward.py 的 ranking_to_weights() 确保均匀分布
    achievements = ranking_to_weights(sorted_agents)
    # 1st place = 100, last place = 0
```

---

## 三、`src/world/locations.py` + `mapgen.py` — 位置与地图

### LocationStore

```python
class LocationStore:
    # 管理世界地图数据
    # 从 data/{world}/locations.json 加载
    # 通过 God Model 生成（如果是首次运行）
    # 为每个位置提供环境描述

    def ensure(persona_names, agents_summary):
        # 如果 locations.json 不存在 → 调用 God Model 生成
        # 如果已存在 → 从文件加载

    def get_surroundings_text(location) -> str:
        # 返回位置的环境描述

    def read_map_text(char) -> str:
        # 返回地图描述（含私人住所信息）
```

### 地图生成

地图由 God Model 根据世界设定和智能体描述生成，确保每个世界的一致性和独特性。
