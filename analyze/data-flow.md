# 数据流图 (Data Flow Diagram)

> **基于设计图 `design-interactive.html` 分析**
> 
> **日期**: 2026-06-23
> **分析员**: Orchestrator

---

## 1. 数据流向概览

```
┌─────────────────────────────────────────────────────────────┐
│                       前端 (Browser)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Title Bar│  │Game Info │  │ Dashboard│  │ Narrative│   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │         │
│       └──────────────┴──────────────┴──────────────┘         │
│                           │                                  │
│                           ▼                                  │
│              ┌──────────────────────────┐                   │
│              │  WebSocket Manager       │                   │
│              │  (实时数据推送)            │                   │
│              └──────────┬───────────────┘                   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    后端 (FastAPI Server)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ GameSession  │  │CanonManager  │  │PipelineEngine│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 数据来源分析

### 2.1 实时数据 (WebSocket)
**用途**: 游戏状态实时更新
**频率**: 高 (每次 Beat 更新)

**数据流**:
```
后端 (GameSession) → WebSocket → 前端 (WebSocketManager)
```

**数据示例**:
```json
{
  "type": "beat_update",
  "payload": {
    "beat": 129,
    "narrative": "叙事内容...",
    "tension": 0.68,
    "current_location": "翡冷翠 · 港口区",
    "npcs_present": ["莉亚妮", "费伦"],
    "threads": [...],
    "soul": {...}
  }
}
```

---

### 2.2 按需数据 (REST API)
**用途**: 面板切换时加载数据
**频率**: 中 (用户操作时)

**数据流**:
```
前端 → HTTP GET → 后端 API → 响应 JSON → 前端渲染
```

**API 端点**:
- `GET /api/game/info` - 游戏概览
- `GET /api/dashboard` - Dashboard 数据
- `GET /api/threads` - 线索列表
- `GET /api/log` - 日志列表
- `GET /api/soul/profile` - 灵魂档案

---

### 2.3 静态数据 (本地存储)
**用途**: 配置文件、用户偏好
**频率**: 低 (应用启动时)

**数据示例**:
- `config.yaml` - 管线配置、功能开关
- `localStorage.theme` - UI 主题偏好

---

## 3. 详细数据流

### 3.1 Title Bar 数据流向

```
数据源: GameSession (后端)
  ↓
WebSocket message: {"type": "session_state", "payload": {...}}
  ↓
前端 WebSocketManager 接收
  ↓
更新 Title Bar 组件:
  - game_time → Game Time Badge
  - narrative_mode → Mode Tag
  - deviation → Deviation Indicator
  - connection_status → Connection Status
```

**数据格式**:
```javascript
// WebSocket 消息
{
  "type": "session_state",
  "payload": {
    "session_id": "abc123",
    "game_time": "第3月·第2周·午后",
    "narrative_mode": "探索模式",
    "deviation": 0.22,
    "is_connected": true
  }
}
```

---

### 3.2 Game Info Bar 数据流向

```
数据源: GameSession (后端)
  ↓
WebSocket message: {"type": "game_info_update", "payload": {...}}
  ↓
前端更新 Game Info Bar:
  - current_location
  - tension
  - active_threads_count
  - npcs_present_count
  - epoch, beat
```

**数据格式**:
```javascript
// WebSocket 消息
{
  "type": "game_info_update",
  "payload": {
    "current_location": "翡冷翠 · 市政广场",
    "tension": 0.72,
    "active_threads": 3,
    "npcs_present": 5,
    "epoch": 47,
    "beat": 128
  }
}
```

---

### 3.3 Dashboard Panel (F0) 数据流向

```
数据源1: GameSession (后端) - 游戏状态
  ↓
前端请求: GET /api/dashboard
  ↓
后端响应: JSON
  ↓
前端渲染 Dashboard 组件

数据源2: CharacterCognition (后端) - NPC 认知冲突
  ↓
前端请求: GET /api/npc/dissonance
  ↓
后端响应: JSON
  ↓
前端渲染 NPC Chips

数据源3: SoulPossession (后端) - 灵魂状态
  ↓
前端请求: GET /api/soul/profile
  ↓
后端响应: JSON
  ↓
前端渲染 Soul Stats
```

**数据格式**:
```javascript
// API 响应: GET /api/dashboard
{
  "success": true,
  "data": {
    "game_time": {
      "display": "第3月·第2周·午后",
      "weather": "雨季 · 微风 · 凉爽 18°C"
    },
    "current_location": {
      "display": "翡冷翠 · 市政广场",
      "meta": "城市中心 · 人口密集 · 商业区"
    },
    "tension": 0.72,
    "threads": {
      "active": 3,
      "evolving": 2,
      "resolved": 5,
      "list": [
        {
          "id": "thread_03",
          "title": "翡翠密谋",
          "type": "main",
          "urgency": 0.85,
          "complexity": 0.60,
          "tension": 0.75,
          "priority": 0.90,
          "question": "谁在暗中操纵翡翠商会？"
        },
        ...
      ]
    }
  }
}
```

---

### 3.4 Right Panel - Characters Tab 数据流向

```
数据源: CharacterCognition (后端)
  ↓
WebSocket message: {"type": "character_update", "payload": {...}}
  ↓
前端更新 Characters Tab:
  - characters_present[].name
  - characters_present[].dissonance_phase
  - characters_present[].emotion
  - characters_present[].location
  - characters_present[].reputation
  - characters_present[].trust
  - characters_present[].scratchpad
```

**数据格式**:
```javascript
// WebSocket 消息
{
  "type": "character_update",
  "payload": {
    "characters": [
      {
        "name": "莉亚妮",
        "dissonance_phase": "normal",
        "emotion": "愉快",
        "location": "城堡",
        "reputation": 32,
        "trust": 85,
        "scratchpad": "她今天似乎有些不一样……但也许是我想多了。"
      },
      ...
    ]
  }
}
```

---

### 3.5 Right Panel - Soul Tab 数据流向

```
数据源1: SoulPossession (后端) - 灵魂档案
  ↓
前端请求: GET /api/soul/profile
  ↓
后端响应: JSON
  ↓
前端渲染 Soul Tab

数据源2: GameSession (后端) - 选择统计
  ↓
WebSocket message: {"type": "choice_stats_update", "payload": {...}}
  ↓
前端更新选择统计
```

**数据格式**:
```javascript
// API 响应: GET /api/soul/profile
{
  "success": true,
  "data": {
    "player_soul": "异界旅人",
    "canon_echo": "艾琳·晨风",
    "blend_ratio": 0.68,
    "ocean": {
      "openness": 0.70,
      "conscientiousness": 0.55,
      "extraversion": 0.40,
      "agreeableness": 0.65,
      "neuroticism": 0.45
    },
    "moral_alignment": {
      "law_chaos": 0.65,
      "good_evil": 0.30
    },
    "choice_stats": {
      "authentic_choices": 7,
      "canon_compliant_choices": 4
    },
    "inner_voice": "她不喜欢这样……但必须走下去。",
    "canon_echo_voice": "从什么时候开始，你变得如此陌生？"
  }
}
```

---

### 3.6 Log Panel (F5) 数据流向

```
数据源: GameSession (后端) - 事件日志
  ↓
前端请求: GET /api/log?type=narrative (可选过滤)
  ↓
后端响应: JSON
  ↓
前端渲染 Log Entries
```

**数据格式**:
```javascript
// API 响应: GET /api/log
{
  "success": true,
  "data": {
    "stats": {
      "narrative": 12,
      "combat": 3,
      "social": 7,
      "exploration": 4
    },
    "entries": [
      {
        "beat": 128,
        "type": "narrative",
        "text": "翡冷翠广场发现可疑人物"
      },
      ...
    ]
  }
}
```

---

### 3.7 Threads Panel (F8) 数据流向

```
数据源: ThreadManager (后端) - 线索数据
  ↓
前端请求: GET /api/threads?type=main (可选过滤)
  ↓
后端响应: JSON
  ↓
前端渲染 Thread Full Cards
```

**数据格式**:
```javascript
// API 响应: GET /api/threads
{
  "success": true,
  "data": {
    "stats": {
      "active": 3,
      "evolving": 2,
      "resolved": 5
    },
    "threads": [
      {
        "id": "thread_03",
        "title": "翡翠密谋",
        "type": "main",
        "urgency": 0.85,
        "complexity": 0.60,
        "tension": 0.75,
        "priority": 0.90,
        "involved_characters": ["莉亚妮", "费伦", "索恩"],
        "player_attention": 0.70,
        "question": "谁在暗中操纵翡翠商会？"
      },
      ...
    ]
  }
}
```

---

## 4. 数据更新机制

### 4.1 实时更新 (WebSocket)
**触发条件**:
- 新的 Beat 生成
- 玩家做出选择
- NPC 状态变化
- 线索状态变化

**更新频率**: 高 (每次 Beat ~ 几秒)

**消息类型**:
- `beat_update` - Beat 更新
- `character_update` - 角色状态更新
- `thread_update` - 线索状态更新
- `game_info_update` - 游戏信息更新

---

### 4.2 按需更新 (REST API)
**触发条件**:
- 面板切换 (F0-F8)
- 用户点击刷新按钮
- 过滤条件变化

**更新频率**: 中 (用户操作时)

**API 端点**:
- `GET /api/dashboard` - Dashboard 数据
- `GET /api/threads` - 线索列表
- `GET /api/log` - 日志列表
- `GET /api/soul/profile` - 灵魂档案
- `GET /api/characters` - 角色列表
- `GET /api/locations` - 地点列表

---

### 4.3 定时更新 (Polling)
**触发条件**: 无 (设计图中使用模拟数据更新)
**用途**: 演示目的

**实现**:
```javascript
// 设计图中的模拟更新
setInterval(() => {
  idx = (idx + 1) % 4;
  document.getElementById('gameTimeDisplay').textContent = times[idx];
  document.getElementById('currentLocation').textContent = locations[idx];
  document.getElementById('tensionValue').textContent = tension.toFixed(2);
}, 4000);
```

**生产环境**: 应使用 WebSocket 实时更新，而非轮询

---

## 5. 数据持久化

### 5.1 前端持久化
**存储位置**: `localStorage`
**数据类型**:
- UI 主题偏好 (`theme`)
- 面板选择状态 (`active_panel`)
- 过滤条件 (`log_filter`, `thread_filter`)

---

### 5.2 后端持久化
**存储位置**: `saves/` 目录 (JSON 文件)
**数据类型**:
- 游戏状态 (GameSession)
- 角色状态 (Character state)
- 线索状态 (Thread state)
- 灵魂状态 (Soul state)

---

## 6. 数据安全与验证

### 6.1 输入验证
**前端**:
- 验证用户输入 (选项选择、表单提交)
- 防止 XSS (使用 `textContent` 而非 `innerHTML`)

**后端**:
- 验证 API 请求参数
- 验证 WebSocket 消息格式
- 防止 SQL 注入 (使用参数化查询)

### 6.2 输出编码
**前端**:
- 对用户输入进行 HTML 转义
- 对 JSON 数据进行安全解析

**后端**:
- 对响应数据进行 JSON 序列化
- 防止 JSON 注入

---

## 7. 性能优化

### 7.1 数据压缩
**WebSocket**: 使用二进制协议 (可选)
**REST API**: 使用 Gzip 压缩

### 7.2 数据缓存
**前端**:
- 缓存 API 响应 (使用 `Map` 或 `Object`)
- 避免重复请求

**后端**:
- 缓存游戏状态 (GameSession 对象)
- 缓存 Canon 数据 (CanonManager)

### 7.3 增量更新
**WebSocket**: 只发送变化的数据
```json
// 完整更新 (不推荐)
{
  "type": "beat_update",
  "payload": {
    "beat": 129,
    "narrative": "...",
    "tension": 0.68,
    "current_location": "...",
    "npcs_present": [...],
    "threads": [...],
    "soul": {...}
  }
}

// 增量更新 (推荐)
{
  "type": "beat_update",
  "payload": {
    "beat": 129,
    "narrative": "...",
    "tension": 0.68,
    "changed_fields": ["tension", "beat"]
  }
}
```

---

## 8. 总结

### 8.1 数据源优先级
1. **WebSocket** (实时数据) - 高优先级
2. **REST API** (按需数据) - 中优先级
3. **LocalStorage** (用户偏好) - 低优先级

### 8.2 数据更新策略
- **实时数据** → WebSocket 推送
- **按需数据** → REST API 请求
- **静态数据** → 应用启动时加载

### 8.3 下一步
创建 API 需求清单 (`api-requirements.md`)

---

**下一步**: 创建 API 需求清单
