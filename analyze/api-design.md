# API 设计文档 (API Design)

> **基于需求分析设计**
> 
> **日期**: 2026-06-23
> **架构师**: Orchestrator

---

## 1. API 端点总览

### 1.1 现有端点 (保持不变)
- `GET /health` - 健康检查
- `POST /api/abort` - 中止生成
- `GET /api/config/features` - 读取功能开关
- `PUT /api/config/features` - 写入功能开关
- `GET /api/config/define` - 读取配置定义
- `GET /api/pipeline/nodes-meta` - 读取管线节点元数据

### 1.2 新增端点 (需要实现)

| 方法 | 路径 | 用途 | 优先级 |
|------|------|------|--------|
| `GET` | `/api/game/info` | 获取游戏概览信息 | 🔴 高 |
| `GET` | `/api/dashboard` | 获取 Dashboard 数据 | 🔴 高 |
| `GET` | `/api/threads` | 获取线索列表 | 🔴 高 |
| `GET` | `/api/log` | 获取事件日志 | 🟡 中 |
| `GET` | `/api/soul/profile` | 获取灵魂档案 | 🔴 高 |
| `PUT` | `/api/soul/blend` | 调整灵魂支配比 | 🟢 低 |
| `GET` | `/api/npc/dissonance` | 获取 NPC 认知冲突 | 🔴 高 |
| `GET` | `/api/characters` | 获取角色列表（增强版） | 🟡 中 |
| `GET` | `/api/locations` | 获取地点列表 | 🟢 低 |

---

## 2. 详细 API 设计

### 2.1 `GET /api/game/info`

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

**错误响应**:
```json
{
  "success": false,
  "message": "游戏会话不存在",
  "error_code": "SESSION_NOT_FOUND"
}
```

**后端实现**:
```python
@app.get("/api/game/info")
async def get_game_info(session_id: str = Depends(get_session_id)):
    """获取游戏概览信息"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    return {
        "success": True,
        "data": {
            "game_time": session.game_time,
            "weather": session.weather,
            "current_location": session.current_location,
            "location_meta": session.location_meta,
            "tension": session.tension,
            "active_threads": len(session.get_active_threads()),
            "npcs_present": len(session.get_npcs_present()),
            "epoch": session.epoch,
            "beat": session.beat
        }
    }
```

---

### 2.2 `GET /api/dashboard`

**用途**: 获取 Dashboard 面板所需的所有数据

**请求参数**: 无

**响应格式**:
```json
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
      "stats": {
        "active": 3,
        "evolving": 2,
        "resolved": 5
      },
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
        }
      ]
    },
    "npc_dissonance": {
      "npcs": [
        {
          "name": "莉亚妮",
          "affinity": 85,
          "dissonance_phase": "normal"
        }
      ],
      "stats": {
        "normal": 2,
        "subtle": 1,
        "questioning": 1,
        "confront": 1
      }
    },
    "soul": {
      "player_soul": "异界旅人",
      "canon_echo": "艾琳·晨风",
      "blend_ratio": 0.68,
      "choice_stats": {
        "authentic_choices": 7,
        "canon_compliant_choices": 4
      }
    }
  }
}
```

**后端实现**:
```python
@app.get("/api/dashboard")
async def get_dashboard(session_id: str = Depends(get_session_id)):
    """获取 Dashboard 数据"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    # 获取线程数据
    threads = session.get_threads()
    thread_stats = session.get_thread_stats()
    
    # 获取 NPC 认知冲突数据
    npc_dissonance = session.get_npc_dissonance()
    
    # 获取灵魂数据
    soul_data = session.get_soul_profile()
    
    return {
        "success": True,
        "data": {
            "game_time": {
                "display": session.game_time,
                "weather": session.weather
            },
            "current_location": {
                "display": session.current_location,
                "meta": session.location_meta
            },
            "tension": session.tension,
            "threads": {
                "stats": thread_stats,
                "list": threads
            },
            "npc_dissonance": npc_dissonance,
            "soul": soul_data
        }
    }
```

---

### 2.3 `GET /api/threads`

**用途**: 获取线索列表（用于 Dashboard 和 Threads Panel）

**请求参数**:
- `type` (可选): 过滤线索类型 (`main` / `side` / `identity`)
- `status` (可选): 过滤线索状态 (`active` / `evolving` / `resolved`)
- `limit` (可选): 限制返回条数（默认 50）
- `offset` (可选): 分页偏移量（默认 0）

**响应格式**:
```json
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
        "status": "active",
        "urgency": 0.85,
        "complexity": 0.60,
        "tension": 0.75,
        "priority": 0.90,
        "involved_characters": ["莉亚妮", "费伦", "索恩"],
        "player_attention": 0.70,
        "question": "谁在暗中操纵翡翠商会？"
      }
    ],
    "total": 10,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

**后端实现**:
```python
@app.get("/api/threads")
async def get_threads(
    type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session_id: str = Depends(get_session_id)
):
    """获取线索列表"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    # 过滤线索
    threads = session.get_threads(type=type, status=status)
    
    # 分页
    total = len(threads)
    threads = threads[offset:offset + limit]
    
    return {
        "success": True,
        "data": {
            "stats": session.get_thread_stats(),
            "threads": threads,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }
    }
```

---

### 2.4 `GET /api/log`

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
      }
    ],
    "total": 26,
    "limit": 50,
    "offset": 0,
    "has_more": false
  }
}
```

**后端实现**:
```python
@app.get("/api/log")
async def get_log(
    type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session_id: str = Depends(get_session_id)
):
    """获取事件日志"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    # 过滤日志
    logs = session.get_log_entries(type=type)
    
    # 统计
    stats = session.get_log_stats()
    
    # 分页
    total = len(logs)
    logs = logs[offset:offset + limit]
    
    return {
        "success": True,
        "data": {
            "stats": stats,
            "entries": logs,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total
        }
    }
```

---

### 2.5 `GET /api/soul/profile`

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

**后端实现**:
```python
@app.get("/api/soul/profile")
async def get_soul_profile(session_id: str = Depends(get_session_id)):
    """获取灵魂档案"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    return {
        "success": True,
        "data": session.get_soul_profile()
    }
```

---

### 2.6 `PUT /api/soul/blend`

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

**后端实现**:
```python
@app.put("/api/soul/blend")
async def update_soul_blend(payload: dict, session_id: str = Depends(get_session_id)):
    """调整灵魂支配比"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    blend_ratio = payload.get("blend_ratio")
    if blend_ratio is None or not 0.0 <= blend_ratio <= 1.0:
        return {"success": False, "message": "无效的 blend_ratio 值", "error_code": "INVALID_PARAM"}
    
    session.soul.blend_ratio = blend_ratio
    
    return {
        "success": True,
        "message": "灵魂支配比已更新",
        "data": {
            "blend_ratio": blend_ratio
        }
    }
```

---

### 2.7 `GET /api/npc/dissonance`

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
      }
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

**后端实现**:
```python
@app.get("/api/npc/dissonance")
async def get_npc_dissonance(session_id: str = Depends(get_session_id)):
    """获取 NPC 认知冲突列表"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    return {
        "success": True,
        "data": session.get_npc_dissonance()
    }
```

---

### 2.8 `GET /api/characters`

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
      }
    ]
  }
}
```

**后端实现**:
```python
@app.get("/api/characters")
async def get_characters(
    location: Optional[str] = None,
    dissonance_phase: Optional[str] = None,
    session_id: str = Depends(get_session_id)
):
    """获取角色列表"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    # 过滤角色
    characters = session.get_characters(location=location, dissonance_phase=dissonance_phase)
    
    return {
        "success": True,
        "data": {
            "characters": characters
        }
    }
```

---

### 2.9 `GET /api/locations`

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
      }
    ]
  }
}
```

**后端实现**:
```python
@app.get("/api/locations")
async def get_locations(session_id: str = Depends(get_session_id)):
    """获取地点列表"""
    session = ws_manager.get_session(session_id)
    if not session:
        return {"success": False, "message": "游戏会话不存在", "error_code": "SESSION_NOT_FOUND"}
    
    return {
        "success": True,
        "data": {
            "locations": session.get_locations()
        }
    }
```

---

## 3. WebSocket 消息协议增强

### 3.1 新增消息类型

#### `game_info_update`
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

#### `character_update`
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
      }
    ]
  }
}
```

#### `thread_update`
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

#### `soul_update`
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

## 4. 后端数据模型设计 (Pydantic)

### 4.1 Thread 模型
```python
from pydantic import BaseModel
from typing import Optional, List

class ThreadModel(BaseModel):
    id: str
    title: str
    type: str  # "main" / "side" / "identity"
    status: str  # "active" / "evolving" / "resolved"
    urgency: float  # 0.0 - 1.0
    complexity: float  # 0.0 - 1.0
    tension: float  # 0.0 - 1.0
    priority: float  # 0.0 - 1.0
    question: str
    involved_characters: List[str]
    player_attention: float  # 0.0 - 1.0
```

---

### 4.2 Character 模型
```python
class CharacterModel(BaseModel):
    name: str
    role: str
    location: str
    emotion: str
    reputation: int
    trust: int  # 0 - 100
    dissonance_phase: str  # "normal" / "subtle" / "questioning" / "confront" / "adapted"
    scratchpad: Optional[str] = None
```

---

### 4.3 Soul 模型
```python
class SoulModel(BaseModel):
    player_soul: str
    canon_echo: str
    blend_ratio: float  # 0.0 - 1.0
    ocean: dict  # {"openness": 0.70, ...}
    moral_alignment: dict  # {"law_chaos": 0.65, "good_evil": 0.30}
    choice_stats: dict  # {"authentic_choices": 7, ...}
    inner_voice: Optional[str] = None
    canon_echo_voice: Optional[str] = None
```

---

## 5. 前端数据接口设计 (TypeScript)

### 5.1 Thread 接口
```typescript
interface Thread {
  id: string;
  title: string;
  type: 'main' | 'side' | 'identity';
  status: 'active' | 'evolving' | 'resolved';
  urgency: number;  // 0.0 - 1.0
  complexity: number;  // 0.0 - 1.0
  tension: number;  // 0.0 - 1.0
  priority: number;  // 0.0 - 1.0
  question: string;
  involved_characters: string[];
  player_attention: number;  // 0.0 - 1.0
}
```

---

### 5.2 Character 接口
```typescript
interface Character {
  name: string;
  role: string;
  location: string;
  emotion: string;
  reputation: number;
  trust: number;  // 0 - 100
  dissonance_phase: 'normal' | 'subtle' | 'questioning' | 'confront' | 'adapted';
  scratchpad?: string;
}
```

---

### 5.3 Soul 接口
```typescript
interface Soul {
  player_soul: string;
  canon_echo: string;
  blend_ratio: number;  // 0.0 - 1.0
  ocean: {
    openness: number;
    conscientiousness: number;
    extraversion: number;
    agreeableness: number;
    neuroticism: number;
  };
  moral_alignment: {
    law_chaos: number;  // 0.0 (守序) - 1.0 (混乱)
    good_evil: number;  // 0.0 (善良) - 1.0 (邪恶)
  };
  choice_stats: {
    authentic_choices: number;
    canon_compliant_choices: number;
  };
  inner_voice?: string;
  canon_echo_voice?: string;
}
```

---

## 6. 总结

### 6.1 API 端点清单
✅ 已设计 9 个新增 API 端点

### 6.2 WebSocket 消息类型
✅ 已设计 4 个新增消息类型

### 6.3 数据模型
✅ 已设计后端 Pydantic 模型
✅ 已设计前端 TypeScript 接口

### 6.4 下一步
完成任务 #2（架构设计），向用户展示设计文档并申请批准开始 Phase 2

---

**下一步**: 完成任务 #2，向用户展示设计文档
