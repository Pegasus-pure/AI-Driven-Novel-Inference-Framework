# 选项区生成状态气泡 — 设计文档

> 状态: 待实现 | 优先级: P1 | 创建: 2026-06-19

## 概述

在叙事区选项面板紧上方新增一条"状态气泡区"，与顶部 `#pipelineBar` 并存。生成过程中气泡依次弹出，最多同时显示 3 个，叙事文本到达后全部消失。

顶部 `#pipelineBar` 保持不变（全流程 dot 进度 + 标签），气泡区提供"近距视觉反馈"。

## 布局

```
┌─ panel-narrative ─────────────────────┐
│                                        │
│  叙事文本区 (#narrativeArea)            │
│                                        │
│  ┌─ 气泡区 (新增) ──────────────────┐  │
│  │                ┌────────────┐    │  │
│  │                │ 对话编织     │ ← 最旧 │  │
│  │                └────────────┘    │  │
│  │         ┌────────────┐           │  │
│  │         │ 动机分析     │ ← 次新     │  │
│  │         └────────────┘           │  │
│  │  ┌────────────┐                  │  │
│  │  │ 场景导演     │ ← 最新           │  │
│  │  └────────────┘                  │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ┌─ 选项区 (#choicePanel) ──────────┐  │
│  │  (1) 继续冒险                     │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

### 元素

| 元素 | ID / Class | 说明 |
|------|-----------|------|
| 气泡容器 | `#pipelineBubbles` | `<div>`，纵向 flex (`column`)，`justify-content: flex-end`（新气泡从底部推入） |
| 单个气泡 | `.pipeline-bubble` | `<span>`，含 agent 图标 + 状态文字，圆角胶囊形 |

## 行为

### 进入

- `agent_status` 事件触发（含 `label`）→ 创建新气泡 → 插入容器底部（`appendChild`）
- 气泡从下方滑入（`translateY(16px)` → 0），透明度 0→1
- 已有气泡向上推移，最旧气泡靠近容器顶部

### 退出

- 容器内气泡数 > 3 → 移除顶部（最旧）气泡
- 被移除的气泡向上滑出并淡出（`translateY(-16px)` + `opacity:0`），200ms 后销毁 DOM
- `narrative_chunk` 事件 → 所有剩余气泡统一淡出（200ms），容器清空

### 生命周期

```
agent_status(label) → bubble 创建 → appendChild 到容器底部
                    → len > 3 → 移除顶部（最旧）气泡（向上滑出）
narrative_chunk     → 全部 bubble 淡出 → 容器清空
```

### 状态管理

- 追踪列表: `bubbles: Array<{agent: string, label: string, el: HTMLElement}>`
- 最大: 3
- 策略: 新气泡从底部进入，向上堆叠，超过 3 时顶部最旧气泡向上滑出

## 与现有 `#pipelineBar` 的关系

| | `#pipelineBar`（顶部） | `#pipelineBubbles`（叙事区） |
|---|---|---|
| 定位 | header 下方固定 | 选项区紧上方 |
| 形式 | 横向 dot 进度条 + 标签 | 胶囊气泡堆叠 |
| 可见时机 | 生成中始终可见 | 生成中始终可见 |
| 信息密度 | 全流程概览 | 最近 3 步详情 |
| 实现方 | `pipeline-status.js` | 同上模块扩展 |

## 视觉规格

### 气泡样式

```css
.pipeline-bubble {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 20px;        /* 胶囊形 */
  background: rgba(59,109,17,0.12);
  border: 1px solid rgba(59,109,17,0.25);
  color: #8b949e;
  font-size: 12px;
  white-space: nowrap;
  animation: bubbleIn 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
```

### 动画

```
bubbleIn:   translateY(16px) opacity:0 → translateY(0) opacity:1（下方弹入）
bubbleOut:  opacity:1 translateY:0 → opacity:0 translateY(-16px)（上方滑出，200ms）
```

### 气泡容器

```css
.pipeline-bubbles {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: flex-end;
  gap: 4px;
  padding: 4px 0;
  min-height: 0;
  overflow: hidden;
}
```

## 实现计划

### Phase 1: HTML + CSS（10 分钟）

1. `index.html`: 在 `#narrativeArea` 和 `#choicePanel` 之间插入 `<div id="pipelineBubbles" class="pipeline-bubbles"></div>`
2. `main.css`: 添加 `.pipeline-bubbles` / `.pipeline-bubble` 样式 + `@keyframes bubbleIn / bubbleOut`

### Phase 2: JS 逻辑（15 分钟）

3. `pipeline-status.js` 构造函数: 新增 `this._bubbleContainer` / `this._bubbles = []`
4. `init()`: 绑定 `#pipelineBubbles`，注册事件
5. `_onAgentStatus()`: 调用 `_addBubble(agent, label)`
6. `_addBubble()`: 创建气泡元素 → `appendChild` 到容器底部 → 超限时移除容器顶部第一个子元素（向上滑出动画）
7. `_hideStatusLabel()`: 扩展为同时清空气泡容器

### Phase 3: 测试（5 分钟）

8. 发起一次 beat → 观察气泡依次弹出 → 最多 3 个 → 叙事到达后消失

## 验收标准

- [ ] 生成中选项区上方依次出现胶囊气泡，每个带 agent 图标 + 状态文字
- [ ] 同时最多可见 3 个气泡，旧气泡自动消失
- [ ] `narrative_chunk` 到达后所有气泡 200ms 内淡出
- [ ] 不影响顶部 `#pipelineBar` 的正常工作
- [ ] 不影响现有 `#pipelineStatusLabel` 的单行状态（可考虑合并或移除单行标签）
