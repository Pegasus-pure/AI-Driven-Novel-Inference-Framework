# Agentopia 深度分析 — 脚本层与模块交互

---

## 一、`scripts/run_world.py` — 模拟入口

**文件位置**：`E:\Agentopia\scripts\run_world.py`

### 启动流程

```bash
python scripts/run_world.py [--world apartment] [--resume Y W] [--max_agents N] [--parallel]
```

```python
def main():
    # 1. 解析命令行参数
    # 2. 加载配置 (config.json)
    # 3. 设置数据目录 + 运行 ID
    #    run_dir = ensure_run_world_data(world, run_id)
    #    # 从 data/{world}/ 复制到 data/{world}_{run_id}/
    #    # 跳过 locations.json（让 LocationStore 重新生成）
    # 4. 保存运行配置到 data/{run_id}/config.json
    # 5. 初始化世界 (World)
    # 6. 运行模拟 (world.run())
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--world` | config 或 apartment | 世界名称 |
| `--resume` | 无（自动检测 checkpoint） | 恢复起始年/周 |
| `--max_agents` | 无限制 | 限制智能体数量 |
| `--parallel` | 否 | 启用并行执行 |
| `--no_context_engineering` | 否 | 禁用上下文工程 |
| `--no_history` | 否 | 禁用历史 |

---

## 二、`scripts/build_rft_data.py` — RFT 训练数据构建

**文件位置**：`E:\Agentopia\scripts\build_rft_data.py`

**作用**：从完成的模拟中提取高优势轨迹，构建 RLHF (RFT) 训练数据。

### 核心流程

```python
# 1. 加载模拟运行数据
# 2. 计算每个智能体的 rewards（从 reward.jsonl）
# 3. 计算 Returns（折扣累积）
# 4. 计算 Advantages
# 5. 选择 top_fraction 的轨迹（默认 25%）
# 6. 收集对应时间段的 LLM 生成数据
# 7. 输出训练数据

# 输出：
# rft_data/{run_id}_Y{year}W{week}.jsonl  — 训练样本
# rft_data/{run_id}_Y{year}W{week}.md     — 统计报告
# rft_data/god_{run_id}_Y{year}W{week}.jsonl — God Model 样本
```

---

## 三、`scripts/compute_metrics.py` — 定量指标

**文件位置**：`E:\Agentopia\scripts\compute_metrics.py`

**作用**：对完成的运行计算定量指标。

### 输出指标

| 类别 | 指标 |
|------|------|
| Token | 总消耗、按阶段分布 |
| 联络 | 消息数、提议数、响应数 |
| 活动 | 各类活动数量、参与度 |
| 经济 | 收入、支出、存款变化 |
| 技能 | 技能增长分布 |
| 满足感 | 各维度趋势 |
| 社会评价 | 好感/尊重评分 |

---

## 四、`scripts/time_analysis.py` — 性能分析

**文件位置**：`E:\Agentopia\scripts\time_analysis.py`

**作用**：从 `logs/{run_id}/world.log` 中解析每周墙钟耗时。

---

## 五、模块交互全景图

### 5.1 数据流方向

```
run_world.py
    │
    ├─ config.py ← → config.json（加载配置）
    │
    └─ World (world.py)
        │
        ├─ Clock (clock.py) — 时间推进
        │
        ├─ God (god.py)
        │   ├─ → LLM (utils.py/generate_with_fc)
        │   └─ → data/{run_id}/god/ (保存 SFT 数据)
        │
        ├─ MessageCenter (scheduling.py)
        │   ├─ RoleAgent.contact() 写入消息
        │   └─ World.confirm_schedule() 调度
        │
        ├─ RoleAgent (role_agent.py)
        │   ├─ DataManager (data_manager.py) — 数据持久化
        │   ├─ Prompts (prompts.py) — 提示词
        │   ├─ Functions (functions.py) — 工具
        │   ├─ Context (context.py) — 上下文压缩
        │   ├─ ResponseValidator — 响应校验
        │   └─ LLM (utils.py/generate_with_fc)
        │
        ├─ Activity (activity.py)
        │   ├─ JointActivity — 联合活动
        │   ├─ SoloActivity — 单人活动
        │   └─ PublicActivity — 公共活动
        │
        ├─ LocationStore (locations.py)
        │   └─ data/{run_id}/locations.json
        │
        └─ PositionStore (position_application.py)
            └─ data/{run_id}/positions.json
```

### 5.2 调用关系图（简化版）

```
World.run()
  → for year: for week:
    → World.step()
        → _before_week_start()
            → DataManager.apply_fulfillment_decay()
            → DataManager.update_deposit() (income)
        → RoleAgent.plan()
            → DataManager.roleplay_prompt()
            → DataManager.plan_prompt()
            → generate_with_fc() (LLM)
            → _apply_living_standard()
        → World._generate_public_events()
            → God.generate_public_events()
                → generate_with_fc() (God Model)
            → save_generation() (SFT)
        → RoleAgent.signup_public_events()
            → DataManager.roleplay_prompt()
            → generate_with_fc() (LLM)
            → DataManager.add_schedule()
        → RoleAgent.contact() (x n_slots)
            → DataManager.contact_prompt()
            → generate_with_fc() (LLM + tools)
            → MessageCenter.add()
            → DataManager.send_message()
        → MessageCenter.confirm_schedule()
            → 调度算法（~200行）
        → Activity.run() (x n_days)
            → JointActivity/SoloActivity/PublicActivity
            → RoleAgent.enter/act_in/exit_activity()
            → God.evaluate_*()
            → DataManager.apply_activity_outcome()
        → RoleAgent.review()
            → generate_with_fc() (LLM)
            → DataManager.append_weekly_summary()
        → RoleAgent.settle_week()
            → generate_with_fc() (LLM)
            → DataManager.update_possessions()
    → World._update_yearly_profiles()
        → God.update_yearly_profile()
        → DataManager.write_profile()
    → World._run_position_application_season()
        → PositionApplication.run()
        → God.god_evaluate_position_application()
    → World._calculate_rewards()
        → RoleAgent.judge_others()
        → Reward.calculate_*()
        → DataManager.save_reward()
```

---

## 六、关键设计决策总结

| 决策 | 原因 |
|------|------|
| **双模型架构** | God Model 确保评估一致性，Role Model 可低成本替换 |
| **JSONL 追加写入** | 不可变数据源，支持时间旅行查询和恢复 |
| **三层缓存** | LLM 调用昂贵，需要高效复用 |
| **启发式上下文压缩** | 避免递归 LLM 成本，简单截断足够好 |
| **确定性哈希排序** | 确保跨运行可重现性（避免 Python 随机化） |
| **工具调用去重** | LLM 有时会生成重复调用，需去重 |
| **响应验证循环** | 保证输出质量，重建推理保持日志一致性 |
| **Checkpoint 机制** | 支持长时间模拟的中断恢复 |
| **并行执行** | 利用 Semaphore + ThreadPoolExecutor 控制并发 |
| **生活标准系统** | 让智能体自主选择消费水平（影响经济和满足感） |
