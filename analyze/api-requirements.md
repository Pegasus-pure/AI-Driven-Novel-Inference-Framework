# API 需求清单 (API Requirements)

> **基于设计图 `design-interactive.html` 分析**
> 
> **日期**: 2026-06-23
> **分析员**: Orchestrator

---

## 1. 现有 API 端点分析

### 1.1 WebSocket 端点
**路径**: `/ws`
**方法**: WebSocket
**用途**: 实时通信（游戏状态更新、叙事推送）

**现有消息类型**:
- `connect` - 连接建立
- `reconnect` - 重连
- `beat_update` - Beat 更新
- `narrative_chunk` - 叙事流式输出
- `pipeline_status` - 管线状态更新

**需要增强**:
- 添加 `game_info_update` 消息（推送 Game Info Bar 数据）
- 添加 `character_update` 消息（推送 NPC 状态变化）
- 添加 `thread_update` 消息（推送线索状态变化）

---

### 1.2 REST API 端点

#### 现有端点:
- `GET /health` - 健康检查
- `POST /api/abort` - 中止生成
- `GET /api/config/features` - 读取功能开关
- `PUT /api/config/features` - 写入功能开关
- `GET /api/config/define` - 读取配置定义
- `GET /api/pipeline/nodes-meta` - 读取管线节点元数据

#### 需要新增的端点:
见下方 "2. 新增 API 端点需求"

---

## 2. 新增 API 端点需求

### 2.1 Game Info API

#### `GET /api/game/info`
**用途**: 获取游戏概览信息（用于 Game Info Bar 和 Dashboard）

**请求参数**: 无

**响应格式**:
```json
{
  "success": true,
  "data": {
    "game_time": "第3月·第2周·午后",
    "weather": "雨季 · 微风 · 凉爽 18°C",
    "current_location": "翡冷翠 · 市政广场",
    "location_meta": "城市中心 · 人口密集 · 商业区",
    "tension": 0.72,
    "active_threads": 3,
    "npcs_present": 5,
    "epoch": 47,
    "beat": 128
  }
}
```

**数据来源**: `GameSession`

---

### 2.2 Dashboard API

#### `GET /api/dashboard`
**用途**: 获取 Dashboard 面板所需的所有数据

**请求参数**: 无

**响应格式**:
```json
{
  "success": true,
  "data": {
    "game_time": {...},
    "current_location": {...},
    "tension": 0.72,
    "threads": {
      "stats": {"active": 3, "evolving": 2, "resolved": 5},
      "list": [...]
    },
    "npc_dissonance": [...],
    "soul": {...}
  }
}
```

**数据来源**: `GameSession` + `ThreadManager` + `CharacterCognition` + `SoulPossession`

---

### 2.3 Threads API

#### `GET /api/threads`
**用途**: 获取线索列表（用于 Dashboard 和 Threads Panel）

**请求参数**:
- `type` (可选): 过滤线索类型 (`main` / `side` / `identity`)
- `status` (可选): 过滤线索状态 (`active` / `evolving` / `resolved`)

**响应格式**:
```json
{
  "success": true,
  "data": {
    "stats": {"active": 3, "evolving": 2, "resolved": 5},
    "threads": [
      {
        "id": "thread_03",
        "title": "翡翠密谋",
        "type": "main",
        "status": "active",
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

**数据来源**: `ThreadManager`

---

### 2.4 Log API

#### `GET /api/log`
**用途**: 获取事件日志列表（用于 Log Panel）

**请求参数**:
- `type` (可选): 过滤日志类型 (`narrative` / `combat` / `social` / `exploration`)
- `limit` (可选): 限制返回条数（默认 50）
- `offset` (可选): 分页偏移量（默认 0）

**响应格式**:
```json
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
        "text": "翡冷翠广场发现可疑人物",
        "timestamp": "2026-06-23T10:30:00Z"
      },
      ...
    ],
    "total": 26
  }
}
```

**数据来源**: `GameSession` (事件日志)

---

### 2.5 Soul API

#### `GET /api/soul/profile`
**用途**: 获取灵魂档案（用于 Soul Tab）

**请求参数**: 无

**响应格式**:
```json
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

**数据来源**: `SoulPossession`

---

#### `PUT /api/soul/blend`
**用途**: 调整灵魂支配比（未来功能）

**请求参数**:
```json
{
  "blend_ratio": 0.75
}
```

**响应格式**:
```json
{
  "success": true,
  "message": "灵魂支配比已更新",
  "data": {
    "blend_ratio": 0.75
  }
}
```

**数据来源**: `SoulPossession`

---

### 2.6 NPC Dissonance API

#### `GET /api/npc/dissonance`
**用途**: 获取 NPC 认知冲突列表（用于 Dashboard）

**请求参数**: 无

**响应格式**:
```json
{
  "success": true,
  "data": {
    "npcs": [
      {
        "name": "莉亚妮",
        "affinity": 85,
        "dissonance_phase": "normal"
      },
      {
        "name": "费伦",
        "affinity": 42,
        "dissonance_phase": "questioning"
      },
      ...
    ],
    "stats": {
      "normal": 2,
      "subtle": 1,
      "questioning": 1,
      "confront": 1,
      "adapted": 0
    }
  }
}
```

**数据来源**: `CharacterCognition`

---

### 2.7 Characters API (增强)

#### `GET /api/characters`
**用途**: 获取角色列表（增强版，包含认知冲突数据）

**请求参数**:
- `location` (可选): 过滤地点
- `dissonance_phase` (可选): 过滤认知冲突阶段

**响应格式**:
```json
{
  "success": true,
  "data": {
    "characters": [
      {
        "name": "莉亚妮",
        "role": "主角",
        "location": "城堡",
        "emotion": "愉快",
        "reputation": 32,
        "trust": 85,
        "dissonance_phase": "normal",
        "scratchpad": "她今天似乎有些不一样……但也许是我想多了。"
      },
      ...
    ]
  }
}
```

**数据来源**: `CanonManager` + `CharacterCognition`

---

### 2.8 Locations API

#### `GET /api/locations`
**用途**: 获取地点列表

**请求参数**: 无

**响应格式**:
```json
{
  "success": true,
  "data": {
    "locations": [
      {
        "name": "翡冷翠 · 市政广场",
        "type": "城市",
        "atmosphere": "热闹",
        "npcs_present": ["莉亚妮", "费伦"]
      },
      ...
    ]
  }
}
```

**数据来源**: `CanonManager`

---

## 3. WebSocket 消息协议增强

### 3.1 新增消息类型

#### `game_info_update`
**用途**: 推送游戏信息更新（Game Info Bar）

**消息格式**:
```json
{
  "type": "game_info_update",
  "payload": {
    "current_location": "翡冷翠 · 港口区",
    "tension": 0.68,
    "active_threads": 4,
    "npcs_present": 6,
    "epoch": 47,
    "beat": 129
  }
}
```

---

#### `character_update`
**用途**: 推送角色状态更新（Right Panel - Characters Tab）

**消息格式**:
```json
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

#### `thread_update`
**用途**: 推送线索状态更新（Dashboard 和 Threads Panel）

**消息格式**:
```json
{
  "type": "thread_update",
  "payload": {
    "updated_threads": [
      {
        "id": "thread_03",
        "title": "翡翠密谋",
        "urgency": 0.90,
        "status": "active"
      }
    ],
    "stats": {
      "active": 4,
      "evolving": 2,
      "resolved": 5
    }
  }
}
```

---

#### `soul_update`
**用途**: 推送灵魂状态更新（Right Panel - Soul Tab）

**消息格式**:
```json
{
  "type": "soul_update",
  "payload": {
    "blend_ratio": 0.70,
    "inner_voice": "新的内心独白...",
    "choice_stats": {
      "authentic_choices": 8,
      "canon_compliant_choices": 4
    }
  }
}
```

---

## 4. API 设计原则

### 4.1 RESTful 设计
- 使用正确的 HTTP 方法 (GET / POST / PUT / DELETE)
- 使用语义化的 URL 路径
- 使用正确的 HTTP 状态码

### 4.2 响应格式统一
**成功响应**:
```json
{
  "success": true,
  "data": {...}
}
```

**错误响应**:
```json
{
  "success": false,
  "message": "错误描述",
  "error_code": "ERR_XXX"
}
```

### 4.3 数据分页
**请求参数**:
- `limit`: 每页条数（默认 50）
- `offset`: 偏移量（默认 0）

**响应格式**:
```json
{
  "success": true,
  "data": {
    "items": [...],
    "total": 100,
    "limit": 50,
    "offset": 0,
    "has_more": true
  }
}
```

### 4.4 数据过滤
**请求参数**:
- 使用查询参数过滤: `?type=main&status=active`
- 支持多个过滤条件（AND 关系）

---

## 5. 前后端变量名映射

### 5.1 关键数据结构

| 前端变量名 (JavaScript) | 后端变量名 (Python) | 说明 |
|------------------------|---------------------|------|
| `game_time` | `game_time` | 游戏内时间 |
| `current_location` | `current_location` | 当前位置 |
| `tension` | `tension` | 叙事张力 |
| `active_threads` | `active_threads` | 活跃线索数 |
| `npcs_present` | `npcs_present` | 在场 NPC 数 |
| `epoch` | `epoch` | Epoch 计数器 |
| `beat` | `beat` | Beat 计数器 |
| `threads` | `threads` | 线索列表 |
| `npc_dissonance` | `npc_dissonance` | NPC 认知冲突 |
| `soul` | `soul` | 灵魂状态 |
| `ocean` | `ocean` | OCEAN 人格 |
| `moral_alignment` | `moral_alignment` | 道德阵营 |
| `choice_stats` | `choice_stats` | 选择统计 |

**✅ 统一性检查**: 所有变量名已统一（前端/后端使用相同命名）

---

## 6. 总结

### 6.1 新增 API 端点清单
1. ✅ `GET /api/game/info` - 游戏概览
2. ✅ `GET /api/dashboard` - Dashboard 数据
3. ✅ `GET /api/threads` - 线索列表
4. ✅ `GET /api/log` - 日志列表
5. ✅ `GET /api/soul/profile` - 灵魂档案
6. ✅ `PUT /api/soul/blend` - 调整灵魂支配比
7. ✅ `GET /api/npc/dissonance` - NPC 认知冲突
8. ✅ `GET /api/characters` - 角色列表（增强版）
9. ✅ `GET /api/locations` - 地点列表

### 6.2 WebSocket 消息类型增强
1. ✅ `game_info_update` - 游戏信息更新
2. ✅ `character_update` - 角色状态更新
3. ✅ `thread_update` - 线索状态更新
4. ✅ `soul_update` - 灵魂状态更新

### 6.3 下一步
完成任务 #1（分析设计图），开始任务 #2（设计前后端接口）

---

**下一步**: 创建变量名映射表 (`variable-mapping.md`)
