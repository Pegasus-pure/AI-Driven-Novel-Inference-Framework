# Rain 项目记忆

## 项目定位
- 通用 AI 小说推演框架
- 灵感来源：米哈游《Varsapura》（雨之城）
- 玩家导入完结小说 → AI 自动抽取世界观/角色/剧情 → 玩家以穿越者（路人）身份沉浸
- 目标受众：看过原著的「重温者」和没看过的「发现者」

## 技术栈
- Godot 4.x（游戏引擎）
- LLM API（叙事引擎运行时，Ollama/DeepSeek/OpenAI）
- 终端风格 UI

## GDD 位置
- `E:\Godot-Project\Rain\GDD\GDD.md`（v0.2.0，2026-06-15）

---

## 整体进度概览

### Phase 0: 基础框架 ✅ 已完成
- [x] Godot 项目骨架搭建（project.godot、main.tscn）
- [x] 终端 UI 框架（叙事区 + 输入区 + 状态栏 + F1-F5 面板）
- [x] 世界状态管理器（WorldState autoload）
- [x] Canon 加载器（CanonLoader autoload）
- [x] 事件总线（EventBus autoload）
- [x] Novel Scanner / Canon Extractor autoload

### Phase 1: 导入管道 ⚠️ 部分完成
- [x] 小说文本预处理（NovelScanner）
- [x] Canon 自动提取器（CanonExtractor）
- [x] LLM API 封装（LLMClient → 已被 Provider 体系替代）
- [ ] 完整 5-Pass 导入流程（Pass A-E）未实现
- [ ] 手动修正界面未实现

### Phase 2: 叙事引擎 MVP ✅ 已完成 → 升级为 MaNA v3
- **v0.1（6/15-6/16）**: 单体 LLM 调用 + 导演 Agent + 角色 AI + 连续性校验
  - 线索池系统（3 线索短弧线）
  - 世界偏离度机制（5 级，基于线索/进度/声誉）
  - 连续性自检（内联 prompt，零额外 token）
- **v3（6/17）**: 重构为 MaNA 五层多 Agent 叙事管线（详见下方）

### Phase 3: 完整体验 ✅ 已完成
- [x] F1-F5 面板体系（角色档案/地点/日志/关系图/存档）
- [x] 存档/读档系统（3 槽位，JSON 序列化）
- [x] 结局系统（偏离度 ≥ 0.8 或 主线关闭触发）
- [ ] 多种结局条件细化
- [ ] 角色关系图谱可视化（当前为文字版）
- [ ] 小说导入引导流程

### Phase 4: 打磨 ❌ 未开始

---

## MaNA 架构 v3（当前核心）

### 架构概述
- **5 层流水线**: Context Builder → Scene Director → Character Engines (Motivation → Dialogue+Action) → Scene Composer → Auditor/Extractor → Thread Manager → Reflection Oracle
- **三级模型分配**: strong (Director/Composer/Oracle) / medium (Motivation/Dialogue/Action/Auditor/Thread) / light (StateExtractor)
- **全新 JSON 输出格式**, 废弃 HTML 注释标记
- **Provider 抽象层**: Ollama / DeepSeek / OpenAI 统一接口

### 每节拍调用数
- 5 + 3N（N = 出场角色数），3 轮串行
- Layer 2 R1（动机）N 并行 + Layer 2 R2（对话+动作）N×2 并行

### 关键设计决策
| # | 决策 | 说明 |
|---|------|------|
| D1 | 多 Agent 分离 | 每个 Agent 独立推理，不计成本 |
| D2 | 全新架构 | 不复用现有 LLMClient |
| D3 | 全新 JSON Schema | 废弃 HTML 注释标记 |
| D4 | 聚焦 LLM 层 | UI 暂不动 |
| Q2 | Auditor FAIL → WARNING | 不自动重写叙事 |
| Q3 | mood delta 叠加 | 非覆盖 |
| Q4 | canon 范围由 Director 决定 | required_canon 字段 |
| Q6 | Oracle 输出注入 Director | 作为隐藏上下文 |

### 已实现文件（28 个）
```
src/llm/manana/  (16 文件):
  manana_pipeline.gd, manana_config.gd, manana_schema.gd, manana_logger.gd
  base_agent.gd, context_builder.gd, scene_director.gd
  motivation_engine.gd, dialogue_weaver.gd, action_director.gd
  scene_composer.gd, consistency_auditor.gd, state_extractor.gd
  thread_manager.gd, reflection_oracle.gd, interaction_pair.gd

src/llm/providers/  (5 文件):
  base_provider.gd, ollama_provider.gd, deepseek_provider.gd
  openai_provider.gd, provider_factory.gd

src/autoload/  (6 文件):
  world_state.gd, event_bus.gd, provider_registry.gd
  canon_loader.gd, novel_scanner.gd, canon_extractor.gd

prompts/  (9 文件):
  director.md, motivation.md, dialogue_weaver.md, action_director.md
  composer.md, auditor.md, state_extractor.md, thread_manager.md, oracle.md
```

### 改造文件
- `project.godot`: 新增 MananaPipeline + ProviderRegistry autoload
- `world_state.gd`: 新增 apply_state_patch() 方法
- `event_bus.gd`: 新增 beat_started/beat_completed/agent_error/pipeline_degraded 等信号
- `main.gd`: 删除约 400 行旧 Pipeline 逻辑，入口改为 MananaPipeline.run_beat()

### 废弃但保留的文件
- `src/llm/llm_client.gd` — 被 Provider 体系替代
- `src/narrative/narrative_template.gd` — prompt 外移到 prompts/*.md

### 配置
- `manana_config.cfg`: Ollama qwen3.5:9b 全 tier（近期统一为同一模型）
- 降级链: strong → medium → light → 兜底
- Oracle 触发间隔: 每 5 节拍

### 测试状态
- beat_001 已运行（debug/agent_traces/ 中有完整 trace）
- QA 2 轮测试通过，4 Bug 修复，全部 IS_PASS YES

---

## Prompt 瘦身 (6/16)
- system prompt: 1800 → 600 字（删冗长示例、合并重复规则）
- 角色上下文: 7 字段 → 4 字段（性格/说话风格/动机/态度），2000 → 1200 字
- 叙事历史: 3 条 → 2 条
- 预估请求体 ~8000 → ~5600 字节，减少 ~30%
- 线索标题: `substr()` → `left(4)+"…"` 安全截断 + 空值守卫
- 线索重复修复: `_seed_initial_threads` 加 `if active.size() > 0: return` 守卫

## LLM 通信关键踩坑

### HTTPRequest 重写
- HTTPClient + SSE 流式方案多轮调试仍不可用 → 完全重写为 HTTPRequest 非流式
- 参考: `E:\Godot-Project\AI编排游戏` 的 HTTPRequest 范式
- API 路径: `/api/chat` (Ollama 原生) → `/v1/chat/completions` (OpenAI 兼容)
- 响应解析: `resp["message"]["content"]` → `choices[0].message.content`

### qwen3.5:9b 思考模式陷阱
- **症状**: 提示 "400 input length too long"（实际 prompt 仅 ~600-1000 字，模型原生 256K 上下文）
- **根因**: qwen3.5:9b 默认开启思考模式，思考消耗全部 max_tokens，content 为空，finish_reason="length"
- **证据链**: max_tokens=200 → content 空; max_tokens=1024 → 思考~600 + 回复~400; `reasoning_effort="none"` → 26 token 秒回
- **修复**: max_tokens 200 → 2048；增强错误日志（非 200 打印完整 body）；新增 reasoning 非空但 content 为空的专项诊断

## 世界偏离度计算
- 公式: `已关闭线索数 × 0.08 + 活跃线索平均进度 × 0.1 + 声誉离散度(abs spread) × 0.15`
- 5 级: "紧密沿原著" < "局部微小偏离" < "显著偏离" < "大幅偏离" < "完全脱离"
- 触发时机: `adjust_player_reputation()` 和 `_close_thread()` 后自动重算

## GDScript 语法修复案例 (5 处，Godot 4.6)
1. `llm_client.gd`: `connect_to_host(api_base)` — api_base 是全 URL，需拆分为 `api_host` + `api_port`
2. `world_state.gd`: 4 处 `.get()` 返回值缺失 `as Type` (get_character_state / get_relation)
3. `canon_loader.gd`: 链式 `.get().get()` 在 Variant 上不可用 (personality.core_motivation)，拆分为独立函数
4. `main.gd`: `.get("atmosphere")` 缺失 `as String`
5. 修复后全项目无 `var :=` 推断声明，所有 `for in` 循环正确使用 `as` 转换

---

## Godot MCP Server
- 38 个 MCP 工具，8 大类，5 个 Resources
- TypeScript (Node 22.22.2)，编译通过
- WebSocket 通道 (port 4099) + File-only 降级
- 安全标签: 23 个工具带 [READ-ONLY] / [EDITOR] / [DESTRUCTIVE] 标签
- Rain 专属 canon 管理工具（10 个）

---

## 测试数据
- 2 部导入小说: 《成為我筆下小說的路人甲》《魔王去上學》
- 1 个测试 canon: canon.json
- debug/ 中有 12 组 v0.1 响应日志 + 1 个 beat_001 的完整 MaNA trace

---

## Provider 配置
- 当前: Ollama qwen3.5:9b @ 192.168.71.11:11434（全 tier）
- 已预配: DeepSeek API、OpenAI API（API Key 待填）
- 超时: strong 180s / medium 120s / light 60s
- 重试: max 3 次，base_delay 1.0s
