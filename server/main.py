# -*- coding: utf-8 -*-
"""Rain Web 版 — FastAPI 应用入口

提供:
  - 静态文件服务 (static/)
  - SPA 回退路由
  - WebSocket 端点 /ws
  - 健康检查 /health
"""
from __future__ import annotations

# ── 确保项目根目录在 sys.path 中（uvicorn 子进程兼容） ──
import os
import sys
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import yaml as _yaml

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from server.app.game_session import GameSession
from server.network.websocket_manager import WebSocketManager
from server.data.canon_manager import CanonManager
from server.manana.pipeline_definition import get_config_define, get_pipeline_nodes_meta

# ── 日志（使用模块级 logger，避免 basicConfig 冲突） ──
from server.config.logging_config import get_logger
_log = get_logger("Rain.Server")

# ── 路径（统一从 paths.py 导入）──
from server.config.paths import STATIC_DIR as _STATIC_DIR, CONFIG_PATH as _CONFIG_PATH

# ── FastAPI 应用（使用 lifespan 替代已弃用的 on_event）──
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理器（替代 @app.on_event）"""
    # 启动时执行
    asyncio.ensure_future(_session_cleanup_loop())
    _log.info("session 过期清理任务已启动 (TTL=%ds)", 1800)
    yield
    # 关闭时执行（如果需要清理资源）


app = FastAPI(
    title="Rain Web",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# ── WebSocket 管理器（全局单例）──
ws_manager = WebSocketManager()


# ── session 过期清理后台任务 ──
async def _session_cleanup_loop() -> None:
    """每 5 分钟检查一次过期 session。"""
    while True:
        await asyncio.sleep(300)
        cleaned = await ws_manager.cleanup_stale_sessions()
        if cleaned:
            _log.info("session 清理循环: 清理了 %d 个过期会话", cleaned)




# ═══════════════════════════════════════════════════════════
# 静态文件服务
# ═══════════════════════════════════════════════════════════

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
async def health_check() -> dict:
    """健康检查端点"""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/abort")
async def api_abort(session_id: str = "") -> dict:
    """HTTP 中止接口（供 navigator.sendBeacon 使用）

    当用户刷新/关闭页面时，前端可以发送一个 HTTP 请求来中止管线。
    """
    if not session_id:
        return {"success": False, "message": "缺少 session_id"}

    session = ws_manager.sessions.get(session_id)
    if session is None:
        return {"success": False, "message": f"会话 {session_id} 不存在"}

    try:
        if session._generation_in_progress:
            session.cancel_typing()
            if session._generation_task:
                session._generation_task.cancel()
                try:
                    await session._generation_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            session._generation_in_progress = False
            session._current_agent = None
            _log.info("HTTP 中止: session=%s", session_id)
            message = "生成已中止"
        else:
            message = "当前无进行中的生成"
        return {"success": True, "message": message}
    except Exception as exc:
        _log.error("HTTP 中止失败: %s", exc)
        return {"success": False, "message": str(exc)}



# ═════════════════════════════════════════════════════
# 配置 API — 读取/写入 config.yaml 的 features 段
# ═════════════════════════════════════════════════════

@app.get("/api/config/features")
async def get_features() -> dict:
    """读取 config.yaml 的 features 段"""
    try:
        from server.config.paths import CONFIG_PATH as _CP
        if not _CP.is_file():
            return {"success": False, "message": "config.yaml 不存在"}
        with open(_CP, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        features = data.get("features", {})
        return {"success": True, "features": features}
    except Exception as exc:
        _log.error("读取 features 失败: %s", exc)
        return {"success": False, "message": str(exc)}


@app.put("/api/config/features")
async def put_features(payload: dict) -> dict:
    """写入 config.yaml 的 features 段"""
    try:
        from server.config.paths import CONFIG_PATH as _CP
        if not _CP.is_file():
            return {"success": False, "message": "config.yaml 不存在"}
        with open(_CP, "r", encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        new_features = payload.get("features", {})
        data["features"] = new_features
        with open(_CP, "w", encoding="utf-8") as f:
            _yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        _log.info("Features 已更新: %s", new_features)
        return {"success": True, "features": new_features}
    except Exception as exc:
        _log.error("写入 features 失败: %s", exc)
        return {"success": False, "message": str(exc)}




@app.get("/api/config/define")
async def api_get_config_define() -> dict:
    """返回所有配置项的说明定义（供前端动态显示注释）"""
    try:
        define = get_config_define()
        return {"success": True, "define": define}
    except Exception as exc:
        _log.error("读取配置定义失败: %s", exc)
        return {"success": False, "message": str(exc)}

# ═══════════════════════════════════════════════════════════
# SPA 回退 — 所有非 API/WS 路由返回 index.html
# ═══════════════════════════════════════════════════════════

@app.get("/api/pipeline/nodes-meta")
async def api_get_pipeline_nodes_meta() -> dict:
    """返回管线节点的元数据（label、desc、icon、emoji、tier）"""
    try:
        meta = get_pipeline_nodes_meta()
        return {"success": True, "meta": meta}
    except Exception as exc:
        _log.error("读取管线节点元数据失败: %s", exc)
        return {"success": False, "message": str(exc)}



@app.get("/api/soul/profile")
async def api_get_soul_profile(session_id: str = "") -> dict:
    """返回灵魂附生档案（OCEAN 人格、道德阵营）"""
    try:
        if not session_id:
            return {"success": False, "message": "缺少 session_id"}
        
        session = ws_manager.sessions.get(session_id)
        if session is None:
            return {"success": False, "message": f"会话 {session_id} 不存在"}
        
        # 从 soul_possession 模块中提取数据
        # TODO: 实际实现需要从 SoulPossessionManager 中获取
        soul_data = {
            "ocean": {
                "openness": 0.7,
                "conscientiousness": 0.6,
                "extraversion": 0.4,
                "agreeableness": 0.8,
                "neuroticism": 0.3
            },
            "moral_alignment": "neutral_good",
            "inner_monologue": "内心独白内容..."
        }
        
        return {"success": True, "data": soul_data}
    except Exception as exc:
        _log.error("获取灵魂档案失败: %s", exc)
        return {"success": False, "message": str(exc)}


@app.get("/api/npc/dissonance")
async def api_get_npc_dissonance(session_id: str = "") -> dict:
    """返回 NPC 认知冲突列表"""
    try:
        if not session_id:
            return {"success": False, "message": "缺少 session_id"}
        
        session = ws_manager.sessions.get(session_id)
        if session is None:
            return {"success": False, "message": f"会话 {session_id} 不存在"}
        
        # 从 character_cognition 模块中提取数据
        # TODO: 实际实现需要从 CharacterCognitionManager 中获取
        dissonance_data = {
            "npc_dissonances": [
                {
                    "npc_id": "npc_001",
                    "npc_name": "李四",
                    "conflict_type": "identity_confusion",
                    "conflict_level": 0.7,
                    "description": "李四对主角的身份感到困惑"
                }
            ]
        }
        
        return {"success": True, "data": dissonance_data}
    except Exception as exc:
        _log.error("获取 NPC 认知冲突失败: %s", exc)
        return {"success": False, "message": str(exc)}

@app.get("/")
async def serve_index() -> HTMLResponse:
    """服务首页"""
    index_path = _STATIC_DIR / "index.html"
    if index_path.is_file():
        content = index_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Rain Web — static/index.html 未找到</h1>", status_code=404)


@app.get("/{full_path:path}", response_model=None)
async def serve_spa(full_path: str):
    """SPA 回退：非静态文件路由均返回 index.html"""
    # 先尝试匹配 static 目录下的文件
    static_file = _STATIC_DIR / full_path
    if static_file.is_file():
        return FileResponse(static_file)

    # 回退到 index.html（SPA 路由）
    index_path = _STATIC_DIR / "index.html"
    if index_path.is_file():
        content = index_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>Rain Web — 页面未找到</h1>", status_code=404)


# ═══════════════════════════════════════════════════════════
# WebSocket 端点
# ═══════════════════════════════════════════════════════════


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = "") -> None:
    """WebSocket 端点 — 所有游戏通信的主通道

    连接 URL: ws://host:port/ws?session_id=xxx（重连时携带）
    """

    await ws_manager.connect(websocket, session_id)

    sid = ws_manager.get_session_id(websocket) or str(uuid.uuid4())[:8]
    _log.info("WS 连接: session=%s", sid)

    try:
        # 创建或恢复 GameSession
        if session_id and session_id in ws_manager.sessions:
            session = ws_manager.sessions[session_id]
            _log.info("恢复会话: %s", session_id)
            # 重连时也同步更新 _connections 映射
            await ws_manager.register_connection(session_id, websocket)
            # 发送重连确认
            await ws_manager.send_json(websocket, {
                "type": "reconnected",
                "payload": {
                    "session_id": session_id,
                    "last_beat_id": f"beat_{session.beat_count:03d}",
                },
            })
            # 发送当前状态同步
            await ws_manager.send_json(websocket, {
                "type": "state_sync",
                "payload": session.get_state_snapshot(),
            })
            # canon_list 由客户端重连后自动请求，不再主动推送
        else:
            # 创建会话（构造失败时使用最小配置）
            try:
                session = GameSession(sid)
            except Exception as exc:
                _log.error("GameSession 构造失败: %s", exc)
                # 发送错误并断开
                await ws_manager.send_json(websocket, {
                    "type": "error",
                    "payload": {
                        "code": "SESSION_CREATE_FAILED",
                        "message": f"无法创建游戏会话: {exc}",
                    },
                })
                await websocket.close()
                return

            await ws_manager.register_session(sid, session)

            # 同步更新 _connections 映射（首次连接时 connect() 无法正确注册）
            await ws_manager.register_connection(sid, websocket)

            # 初始化会话（不再自动加载 Canon）
            try:
                await session.initialize(str(_CONFIG_PATH))
            except Exception as exc:
                _log.error("Session 初始化失败: %s", exc)
                # 继续运行，使用回退模式

            # 发送连接确认
            await ws_manager.send_json(websocket, {
                "type": "connected",
                "payload": {"session_id": sid},
            })
            # 发送初始状态（失败则使用空快照）
            try:
                snapshot = session.get_state_snapshot()
            except Exception as exc:
                _log.warning("状态快照失败: %s", exc)
                snapshot = {}
            await ws_manager.send_json(websocket, {
                "type": "state_sync",
                "payload": snapshot,
            })
            # 发送配置信息（失败则使用空配置）
            try:
                config_payload = session.get_config_info()
            except Exception as exc:
                _log.warning("配置信息读取失败: %s", exc)
                config_payload = {"providers": {}}
            await ws_manager.send_json(websocket, {
                "type": "config_info",
                "payload": config_payload,
            })
            # canon_list 由客户端连接后自动发送 request_canon_list 请求，
            # 服务端不再主动推送，避免重复消息导致前端 FSM 状态冲突。

        # ── 消息循环 ──
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send_json(websocket, {
                    "type": "error",
                    "payload": {"code": "INVALID_JSON", "message": "消息格式无效，需要 JSON"},
                })
                continue

            msg_type = str(msg.get("type", ""))
            payload = msg.get("payload", {}) or {}

            # ── 消息路由 ──
            await _route_message(msg_type, payload, websocket, session)

    except WebSocketDisconnect:
        _log.info("WS 断开: session=%s", sid)
    except Exception as exc:
        _log.error("WS 异常: session=%s, error=%s", sid, exc)
        try:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INTERNAL_ERROR", "message": str(exc)},
            })
        except Exception:
            pass
    finally:
        await ws_manager.disconnect(websocket)
        _log.info("WS 清理: session=%s", sid)


async def _route_message(
    msg_type: str,
    payload: dict,
    websocket: WebSocket,
    session: GameSession,
) -> None:
    """WebSocket 消息路由器"""

    # ──────────────────────────────────────────────────
    # 新增：小说选择流程消息
    # ──────────────────────────────────────────────────

    if msg_type == "request_canon_list":
        # 重新扫描并返回 canon_list
        scan_result = session._scan_available_canons()
        await ws_manager.send_json(websocket, {
            "type": "canon_list",
            "payload": scan_result,
        })

    elif msg_type == "load_existing_canon":
        # 切换小说前检查
        can_switch, reason = session.can_switch_novel()
        if not can_switch:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {
                    "code": "CANNOT_SWITCH_MID_GAME",
                    "message": reason,
                },
            })
            return

        source_file = str(payload.get("source_file", ""))
        if not source_file:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_CANON_JSON", "message": "未指定 Canon 文件路径"},
            })
            return

        success = session.load_existing_canon(source_file)
        if success:
            await ws_manager.send_json(websocket, {
                "type": "canon_ready",
                "payload": session.canon_ready_payload(),
            })
        else:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_CANON_JSON", "message": f"无法加载 Canon 文件: {source_file}"},
            })

    elif msg_type == "update_canon_entry":
        # Canon 条目编辑（增/改/删）
        entity_type = str(payload.get("entity_type", "character"))
        action = str(payload.get("action", "update"))
        entry_id = str(payload.get("entry_id", ""))
        data = payload.get("data", {}) or {}

        if not entry_id and action != "create":
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_REQUEST", "message": "更新/删除操作需要 entry_id"},
            })
            return

        result = session.update_canon_entry(entity_type, action, entry_id, data)

        await ws_manager.send_json(websocket, {
            "type": "canon_entries_updated",
            "payload": {
                "entity_type": entity_type,
                "action": action,
                "success": result.get("success", False),
                "entry_id": result.get("entry_id", entry_id),
                "message": result.get("message", ""),
            },
        })

        # 编辑成功后同步完整 canon_ready（让前端刷新完整面板）
        if result.get("success", False):
            await ws_manager.send_json(websocket, {
                "type": "canon_ready",
                "payload": session.canon_ready_payload(),
            })

    elif msg_type == "load_running_canon":
        """加载手动创建的运行 Canon（无对应 canon JSON 文件）"""
        title = str(payload.get("title", "")).strip()
        if not title:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_REQUEST", "message": "未指定小说标题"},
            })
            return

        can_switch, reason = session.can_switch_novel()
        if not can_switch:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CANNOT_SWITCH", "message": reason},
            })
            return

        if not session.canon_manager.load_running_canon(title):
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "LOAD_FAILED", "message": f"加载失败: {title}（目录结构不存在或已损坏）"},
            })
            return

        session.current_novel = title
        _log.info("运行 Canon 已加载: %s", title)

        await ws_manager.send_json(websocket, {
            "type": "canon_ready",
            "payload": session.canon_ready_payload(),
        })

    elif msg_type == "create_empty_canon":
        """从头创建空白 Canon（不加载任何文件）"""
        title = str(payload.get("title", "")).strip()
        if not title:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_REQUEST", "message": "请输入小说标题"},
            })
            return

        # 切换小说前检查
        can_switch, reason = session.can_switch_novel()
        if not can_switch:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CANNOT_SWITCH", "message": reason},
            })
            return

        success = session.canon_manager.create_empty_running_canon(title)
        if not success:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CREATE_FAILED", "message": "创建失败，可能已存在同名小说"},
            })
            return

        session.current_novel = title
        _log.info("空白 Canon 已创建: %s", title)

        await ws_manager.send_json(websocket, {
            "type": "canon_ready",
            "payload": session.canon_ready_payload(),
        })

    elif msg_type == "import_canon_json":
        # 切换小说前检查
        can_switch, reason = session.can_switch_novel()
        if not can_switch:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {
                    "code": "CANNOT_SWITCH_MID_GAME",
                    "message": reason,
                },
            })
            return

        filename = str(payload.get("filename", ""))
        json_content = str(payload.get("content", ""))
        if not json_content:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_CANON_JSON", "message": "JSON 内容为空"},
            })
            return

        success, message = session.import_canon_json(json_content, filename)
        if success:
            await ws_manager.send_json(websocket, {
                "type": "canon_ready",
                "payload": session.canon_ready_payload(),
            })
        else:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "IMPORT_FAILED", "message": message},
            })

    # ──────────────────────────────────────────────────
    # 原有消息处理
    # ──────────────────────────────────────────────────


    elif msg_type == "abort_generation":
        """中止当前生成（前端中止按钮）"""
        if session._generation_in_progress:
            # 先尝试取消 _generation_task（Canon 生成）
            if session._generation_task and not session._generation_task.done():
                session._generation_task.cancel()
                try:
                    await session._generation_task
                except (asyncio.CancelledError, Exception):
                    pass
            # 叙事管线：设置 skip_typing 让 stream_beat 尽快结束
            session.cancel_typing()
            session._generation_in_progress = False
            session._current_agent = None
            await ws_manager.send_json(websocket, {
                "type": "generation_aborted",
                "payload": {"message": "生成已中止"},
            })
        else:
            await ws_manager.send_json(websocket, {
                "type": "generation_aborted",
                "payload": {"message": "当前无进行中的生成"},
            })

    elif msg_type == "player_action":
        text = str(payload.get("text", ""))
        choice_id = str(payload.get("choice_id", "")) if payload.get("choice_id") else ""
        soul_mode = payload.get("soul_mode", "")

        # ★ 灵魂附生模式：存储 soul_mode 供 stream_beat 使用
        if soul_mode:
            session._soul_choice = {"action_type": soul_mode}

        if not text.strip() and not choice_id:
            text = "继续推进剧情"

        if choice_id:
            _log.info("玩家选择: choice_id=%s, text=%s", choice_id, text)

        # 流式输出叙事（包装为可取消任务）
        async def _send_callback(chunk: dict) -> None:
            """使用已建立的 WebSocket 连接发送消息"""
            await ws_manager.send_json(websocket, chunk)

        session._generation_in_progress = True
        session._generation_task = asyncio.create_task(
            session.stream_beat(text, _send_callback)
        )
        try:
            await session._generation_task
        except asyncio.CancelledError:
            _log.info("player_action 已被中止（abort_generation 已发送中止事件）")
        except Exception as exc:
            _log.error("player_action 异常: %s", exc)
            try:
                await ws_manager.send_json(websocket, {
                    "type": "error",
                    "payload": {"code": "PIPELINE_FAILED", "message": str(exc)},
                })
            except Exception:
                pass
        finally:
            session._generation_in_progress = False
            session._generation_task = None
            session._current_agent = None

    elif msg_type == "save_game":
        slot = int(payload.get("slot", 0))
        name = str(payload.get("name", ""))
        result = session.save_manager.save(slot, session, name)
        await ws_manager.send_json(websocket, {
            "type": "save_complete",
            "payload": result,
        })

    elif msg_type == "load_game":
        slot = int(payload.get("slot", 0))
        data = session.save_manager.load(slot)
        if data:
            session.restore_state(data)
            await ws_manager.send_json(websocket, {
                "type": "load_complete",
                "payload": {
                    "session_id": session.session_id,
                    "world_state": session.get_state_snapshot(),
                },
            })
        else:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "LOAD_FAILED", "message": f"存档槽 {slot} 不存在或已损坏"},
            })

    elif msg_type == "list_saves":
        slots = session.save_manager.list_slots()
        await ws_manager.send_json(websocket, {
            "type": "save_list",
            "payload": {"slots": slots},
        })

    elif msg_type == "delete_save":
        slot = int(payload.get("slot", 0))
        ok = session.save_manager.delete_slot(slot)
        await ws_manager.send_json(websocket, {
            "type": "save_deleted",
            "payload": {"slot": slot, "success": ok},
        })

    elif msg_type == "skip_typing":
        # 跳过前端打字机动画 — 这由前端处理，服务端只需确认
        await ws_manager.send_json(websocket, {
            "type": "skip_ack",
            "payload": {},
        })

    elif msg_type == "update_config":
        # F6 设置面板 — 运行时更新三级模型 API 配置
        providers = payload.get("providers", {})
        api_key = str(payload.get("api_key", ""))

        try:
            await session.update_config(providers=providers, api_key=api_key)
            await ws_manager.send_json(websocket, {
                "type": "config_updated",
                "payload": {
                    "success": True,
                    "available_models": getattr(session, '_available_models', []),
                },
            })
        except Exception as exc:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CONFIG_FAILED", "message": str(exc)},
            })

    # ═══════════════════════════════════════════════════
    # 提供者选择（启动时选模型）
    # ═══════════════════════════════════════════════════

    elif msg_type == "get_providers":
        """前端启动时获取可选提供者列表"""
        try:
            from server.config.paths import CONFIG_PATH

            # 从现有 tier 配置中读取 Ollama 端点（不可硬编码）
            ollama_endpoint = ""
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
                    raw = _yaml.safe_load(_f) or {}
                raw_providers = raw.get("providers", {}) or {}
                for tname in ("strong", "medium", "light"):
                    t = raw_providers.get(tname, {})
                    if isinstance(t, dict) and t.get("type") == "ollama" and t.get("endpoint"):
                        ollama_endpoint = t["endpoint"]
                        break

            # DeepSeek 硬编码，Ollama 端点从 config 读取
            templates = {
                "deepseek": {
                    "name": "deepseek",
                    "type": "deepseek",
                    "endpoint": "https://api.deepseek.com",
                    "has_key": False,
                    "timeout": 120,
                },
                "ollama": {
                    "name": "ollama",
                    "type": "ollama",
                    "endpoint": ollama_endpoint or "http://127.0.0.1:11434",
                    "has_key": False,
                    "timeout": 120,
                },
            }
            await ws_manager.send_json(websocket, {
                "type": "providers_list",
                "payload": {"providers": templates},
            })
        except Exception as exc:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CONFIG_READ_FAILED", "message": str(exc)},
            })

    elif msg_type == "set_provider":
        """用户选定提供者后应用到所有 tier"""
        provider_name = str(payload.get("provider", ""))
        model_name = str(payload.get("model", ""))
        api_key = str(payload.get("api_key", ""))

        if not provider_name:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_REQUEST", "message": "未指定提供者"},
            })
            return

        try:
            # 获取模板配置
            # DeepSeek: 硬编码；Ollama: 端点从现有 tier 读取（不可硬编码）
            from server.config.paths import CONFIG_PATH

            if provider_name == "deepseek":
                template = {"type": "deepseek", "endpoint": "https://api.deepseek.com"}
            elif provider_name == "ollama":
                # 从现有 tier 配置中读端点
                ollama_endpoint = ""
                if CONFIG_PATH.exists():
                    with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
                        raw = _yaml.safe_load(_f) or {}
                    raw_providers = raw.get("providers", {}) or {}
                    for tname in ("strong", "medium", "light"):
                        t = raw_providers.get(tname, {})
                        if isinstance(t, dict) and t.get("endpoint"):
                            ollama_endpoint = t["endpoint"]
                            break
                template = {"type": "ollama", "endpoint": ollama_endpoint or "http://127.0.0.1:11434"}
            else:
                raise ValueError(f"未知提供者: {provider_name}")

            if not template.get("endpoint"):
                raise ValueError(f"提供者 {provider_name} 缺少端点地址")

            # 构建三层配置：保留 config.yaml 中已有的温度/token/超时，
            # 仅覆盖 type/endpoint/model（用户选定部分）
            prov_type = template.get("type", "ollama")
            endpoint = template.get("endpoint", "")
            tier_providers = {}
            # 读取 config 中的现有 provider 配置
            existing_providers = (raw.get("providers", {}) if CONFIG_PATH.exists() else {}) or {}
            for tier_key in ("strong", "medium", "light"):
                existing = existing_providers.get(tier_key, {}) if isinstance(existing_providers.get(tier_key), dict) else {}
                tier_providers[tier_key] = {
                    "type": prov_type,
                    "endpoint": endpoint,
                    "model": model_name or existing.get("model", ""),
                    "temperature": existing.get("temperature", 0.7 if tier_key == "strong" else (0.7 if tier_key == "medium" else 0.5)),
                    "max_tokens": existing.get("max_tokens", 4096 if tier_key == "strong" else (2048 if tier_key == "medium" else 1024)),
                    "api_key": api_key or existing.get("api_key", ""),
                    "timeout": existing.get("timeout", 120),
                }

            # 应用配置
            await session.update_config(providers=tier_providers, api_key="")

            _log.info("提供者已切换: %s → 模型=%s", provider_name, model_name or template.get("model", ""))

            await ws_manager.send_json(websocket, {
                "type": "provider_set",
                "payload": {
                    "success": True,
                    "provider": provider_name,
                    "model": model_name or template.get("model", ""),
                },
            })
        except Exception as exc:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "SET_PROVIDER_FAILED", "message": str(exc)},
            })

    # ═══════════════════════════════════════════════════
    # 模型查询（动态获取可用模型列表）
    # ═══════════════════════════════════════════════════

    elif msg_type == "fetch_models":
        """用户配置完成后查询可用模型列表

        Payload: { type, endpoint, api_key }
        Response: { models: [str], error: str }
        """
        prov_type = str(payload.get("type", ""))
        endpoint = str(payload.get("endpoint", ""))
        api_key = str(payload.get("api_key", ""))

        if not prov_type or not endpoint:
            await ws_manager.send_json(websocket, {
                "type": "model_list",
                "payload": {"models": [], "error": "缺少 type 或 endpoint"},
            })
            return

        try:
            from server.manana.providers import ProviderFactory
            config = {
                "type": prov_type,
                "endpoint": endpoint,
                "api_key": api_key,
                "timeout": 10,
            }
            provider = ProviderFactory.create(prov_type, config)
            if not provider:
                await ws_manager.send_json(websocket, {
                    "type": "model_list",
                    "payload": {"models": [], "error": f"不支持的提供者类型: {prov_type}"},
                })
                return

            models, error = await provider.list_models()
            # 统一转小写：部分 API（如 DeepSeek）返回的模型名带大写但接口只接受小写
            models = [m.lower() for m in models]
            await ws_manager.send_json(websocket, {
                "type": "model_list",
                "payload": {"models": models, "error": error},
            })
        except Exception as exc:
            await ws_manager.send_json(websocket, {
                "type": "model_list",
                "payload": {"models": [], "error": str(exc)},
            })

    elif msg_type == "ping":
        # 心跳消息 — 更新活动时间 + 返回 pong
        sid = ws_manager.get_session_id(websocket)
        if sid:
            await ws_manager.mark_active(sid)
        await ws_manager.send_json(websocket, {
            "type": "pong",
            "payload": {"timestamp": asyncio.get_event_loop().time()},
        })

    # ═══════════════════════════════════════════════════
    # 灵魂附生 — 角色选择 & 游戏开始
    # ═══════════════════════════════════════════════════

    elif msg_type == "request_character_list":
        """前端选角界面请求角色清单"""
        canon = getattr(session.world_state, "canon", None) or {}
        # ★ 手动模式：world_state.canon 可能为空，从 canon_manager 获取
        if not canon.get("characters"):
            running = session.canon_manager.get_running_canon()
            if running:
                canon = running
        if not canon.get("characters"):
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "NO_CANON_DATA", "message": "当前无加载的 Canon 数据"},
            })
            return
        from server.data.novel_loader import NovelLoader
        loader = NovelLoader()
        char_list = loader.get_character_list_for_selection(canon)
        await ws_manager.send_json(websocket, {
            "type": "character_list",
            "payload": {"characters": char_list},
        })

    elif msg_type == "request_game_start_soul":
        """玩家确认选角后启动灵魂附生模式"""
        protagonist_id = str(payload.get("protagonist_id", ""))
        if not protagonist_id:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_REQUEST", "message": "未指定附身角色"},
            })
            return

        canon = getattr(session.world_state, "canon", None) or {}
        # ★ 手动模式：world_state.canon 可能为空，从 canon_manager 获取
        if not canon.get("characters"):
            running = session.canon_manager.get_running_canon()
            if running:
                canon = running
        if not canon.get("characters"):
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "NO_CANON_DATA", "message": "当前无加载的 Canon 数据"},
            })
            return

        # 检查是否可切换（已进入灵魂模式则跳过检查）
        if session.world_state.game_mode != "soul_possession":
            can_switch, reason = session.can_switch_novel()
            if not can_switch:
                await ws_manager.send_json(websocket, {
                    "type": "error",
                    "payload": {"code": "ALREADY_IN_SOUL_MODE", "message": reason or "已在灵魂附生模式中"},
                })
                return

        # 初始化灵魂附生
        from server.data.novel_loader import NovelLoader
        loader = NovelLoader()
        enhanced_canon = loader.load_canon_with_memory(canon)

        session.world_state.canon = enhanced_canon
        session.world_state.game_mode = "soul_possession"
        session._soul_protagonist_id = protagonist_id
        session._init_soul_possession(enhanced_canon, protagonist_id)

        _log.info("灵魂附生启动: 主角=%s", protagonist_id)

        await ws_manager.send_json(websocket, {
            "type": "game_started_soul",
            "payload": {
                "protagonist_id": protagonist_id,
                "canon": session.canon_ready_payload(),
                "soul_state": session._get_soul_state_payload(),
            },
        })

        # 灵魂附生模式：自动生成前 10 拍叙事（人格积累期）
        session._generation_in_progress = True
        async def _send_init_callback(chunk: dict) -> None:
            await ws_manager.send_json(websocket, chunk)
        for i in range(10):
            try:
                session._generation_task = asyncio.create_task(
                    session.stream_beat("", _send_init_callback)
                )
                await session._generation_task
            except asyncio.CancelledError:
                _log.info("灵魂附生第 %d 拍生成被取消", i + 1)
                break
            except Exception as exc:
                _log.error("灵魂附生第 %d 拍生成异常: %s", i + 1, exc)
                break
        session._generation_in_progress = False
        session._generation_task = None

    elif msg_type == "request_soul_state":
        """前端主动请求灵魂状态刷新"""
        soul_payload = session._get_soul_state_payload()
        await ws_manager.send_json(websocket, {
            "type": "soul_state_update",
            "payload": soul_payload,
        })

    elif msg_type == "read_memory":
        agent_id = str(payload.get("agent_id", ""))
        query = str(payload.get("query", ""))
        mm = getattr(session.world_state, '_memory_manager', None)
        if mm and agent_id:
            entries = mm.retrieve(agent_id, query, top_k=5, current_beat=session.beat_count)
            results = [e.to_dict() for e in entries]
        else:
            results = []
        await ws_manager.send_json(websocket, {
            "type": "memory_read_result",
            "payload": {"agent_id": agent_id, "entries": results},
        })

    elif msg_type == "write_memory":
        agent_id = str(payload.get("agent_id", ""))
        content = str(payload.get("content", ""))
        importance = float(payload.get("importance", 5.0))
        mm = getattr(session.world_state, '_memory_manager', None)
        if mm and agent_id and content:
            # Use add_decision helper (avoids MemoryEntry import
            # which conflicts with memory/ package directory)
            mm.add_decision(
                agent_id, content,
                timestamp=session.beat_count,
                importance=importance,
                source="write_memory WS",
            )
            await ws_manager.send_json(websocket, {
                "type": "memory_write_result",
                "payload": {"success": True, "agent_id": agent_id},
            })
        else:
            await ws_manager.send_json(websocket, {
                "type": "memory_write_result",
                "payload": {"success": False, "message": "缺少参数"},
            })

    else:
        await ws_manager.send_json(websocket, {
            "type": "error",
            "payload": {"code": "UNKNOWN_TYPE", "message": f"未知消息类型: {msg_type}"},
        })