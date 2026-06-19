# MaNA v4 增强方案 · 交付总结

## TL;DR
在 MaNA v4 流水线中新增 4 个 Agent（ContinuityChecker、RoleReflector、CharacterManager、LocationManager），实现三大增强改动：涌现建议系统、连续叙事审计、角色过渡反思。

## 交付概览
- **改动数**: 3 大改动，4 个新 Agent
- **修改文件**: 5 个（agents.py, pipeline.py, world_state.py, config.py, config.yaml）
- **新增文件**: 1 个（tests/test_mana_v4_enhance.py）
- **测试**: 3/3 核心测试通过（涌现实体合并、阈值判定、配置结构）

## 改动详情

### 改动一：涌现建议系统
- **CharacterManager** (L3b, light tier) — 扫描叙事文本，检测不在 Canon 中的新角色，暂存 pending_emergences
- **LocationManager** (L3b, light tier) — 同 CharMgr，检测新地点
- **机制**: 多次命中→语义合并→LLM 判定 readiness→生成 JSON 档案→正式加入动态实体
- **数据结构**: `WorldState.pending_emergences: dict[str, PendingEntity]`

### 改动二：连续叙事审计（ContinuityChecker — L1b）
- **位置**: L1 Director → L1b → L2R1
- **判决**: APPROVED / REJECTED（打回重做，上限 2 次）/ NEEDS_TRANSITION
- **模型**: medium tier

### 改动三：角色过渡反思（RoleReflector — L2R3）
- **位置**: L2R2 → L2R3 → L3
- **判决**: PASS / NEED_TRANSITION（附加过渡）/ NEED_REWRITE（打回重做）
- **模型**: light tier

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `server/manana/agents.py` | 修改 | 新增 4 个 Agent 类 |
| `server/manana/pipeline.py` | 修改 | L1b/L2R3/L3b 扩展 + 反馈回路 |
| `server/world_state.py` | 修改 | pending_emergences + dynamic_locations |
| `server/manana/config.py` | 修改 | 新配置段读取 + getter 方法 |
| `config.yaml` | 修改 | emergence/continuity/reflection 配置 |
| `server/manana/prd_mana_v4_enhance.md` | 新增 | PRD 文档 |
| `server/manana/arch_mana_v4_enhance.md` | 新增 | 架构设计文档 |
| `tests/test_mana_v4_enhance.py` | 新增 | 单元测试 |

## 用户下一步建议

1. **验证集成**: 启动游戏，确保现有 beat 流程不受影响（新功能默认通过 feature flag 开启，可随时关闭）
2. **测试涌现流程**: 输入几拍叙事，观察 CharacterManager 是否检测到新角色、3 拍后是否被采纳
3. **测试连续性审计**: 输入与历史冲突的玩家要求，观察 ContinuityChecker 是否 REJECT
4. **测试过渡反思**: 构造角色状态跳跃场景，观察 RoleReflector 是否生成过渡文本
5. **调整配置**: 根据实测效果调整 `hit_threshold`、`similarity_threshold` 等参数
