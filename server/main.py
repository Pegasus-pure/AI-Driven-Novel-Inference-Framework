# -*- coding: utf-8 -*-
"""AI-Driven-Novel-Inference-Framework — FastAPI 应用入口

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
import uuid
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .game_session import GameSession
from .websocket_manager import WebSocketManager
from .canon_manager import CanonManager

# ── 日志（使用模块级 logger，避免 basicConfig 冲突） ──
from .logging_config import get_logger
_log = get_logger("AINovelFramework.Server")

# ── 路径（统一从 paths.py 导入）──
from .paths import STATIC_DIR as _STATIC_DIR, CONFIG_PATH as _CONFIG_PATH

# ── FastAPI 应用 ──
app = FastAPI(
    title="AI-Driven-Novel-Inference-Framework",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# ── WebSocket 管理器（全局单例）──
ws_manager = WebSocketManager()


# ═══════════════════════════════════════════════════════════
# 静态文件服务
# ═══════════════════════════════════════════════════════════

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
async def health_check() -> dict:
    """健康检查端点"""
    return {"status": "ok", "version": "1.0.0"}


# ═══════════════════════════════════════════════════════════
# SPA 回退 — 所有非 API/WS 路由返回 index.html
# ═══════════════════════════════════════════════════════════


@app.get("/")
async def serve_index() -> HTMLResponse:
    """服务首页"""
    index_path = _STATIC_DIR / "index.html"
    if index_path.is_file():
        content = index_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)
    return HTMLResponse(content="<h1>AI-Driven-Novel-Inference-Framework — static/index.html 未找到</h1>", status_code=404)


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
    return HTMLResponse(content="<h1>AI-Driven-Novel-Inference-Framework — 页面未找到</h1>", status_code=404)


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

            ws_manager.register_session(sid, session)

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
            import json
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
    import json

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

    elif msg_type == "regenerate_canon":
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

        txt_path = str(payload.get("txt_path", ""))
        content = str(payload.get("content", ""))

        if not txt_path and not content:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "INVALID_CANON_JSON", "message": "需要提供 txt_path 或 content"},
            })
            return

        # 定义进度回调闭包（闭包捕获 websocket）
        async def _progress_callback(status_data: dict) -> None:
            """LLM 生成进度回调"""
            await ws_manager.send_json(websocket, {
                "type": "canon_generation_status",
                "payload": status_data,
            })
            # 如果生成完成或回退，发送 canon_ready
            status = status_data.get("status", "")
            if status in ("completed", "fallback"):
                await ws_manager.send_json(websocket, {
                    "type": "canon_ready",
                    "payload": session.canon_ready_payload(),
                })
            elif status == "error":
                # 生成失败：发送明确的失败消息，让前端恢复选择界面
                await ws_manager.send_json(websocket, {
                    "type": "canon_generation_failed",
                    "payload": {
                        "message": status_data.get("message", "世界观数据生成失败"),
                        "elapsed_seconds": status_data.get("elapsed_seconds", 0),
                    },
                })

        # 启动异步生成
        await session.start_llm_generation_with_progress(
            txt_path=txt_path,
            content=content,
            progress_cb=_progress_callback,
        )

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
                "payload": {"code": "INVALID_CANON_JSON", "message": message},
            })

    elif msg_type == "canon_generation_status":
        # 查询生成状态（前端重连后可能用到）
        status_info = {
            "status": "generating" if session._generation_in_progress else "idle",
            "message": "世界观数据生成中..." if session._generation_in_progress else "无进行中的任务",
            "elapsed_seconds": 0.0,
        }
        await ws_manager.send_json(websocket, {
            "type": "canon_generation_status",
            "payload": status_info,
        })

    # ──────────────────────────────────────────────────
    # 原有消息处理
    # ──────────────────────────────────────────────────

    elif msg_type == "player_action":
        text = str(payload.get("text", ""))
        choice_id = str(payload.get("choice_id", "")) if payload.get("choice_id") else ""
        if not text.strip() and not choice_id:
            text = "继续推进剧情"

        if choice_id:
            _log.info("玩家选择: choice_id=%s, text=%s", choice_id, text)

        # 流式输出叙事
        await session.stream_beat(text, lambda chunk: ws_manager.send_json(websocket, chunk))

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

    elif msg_type == "upload_novel":
        # 上传小说前检查
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

        filename = str(payload.get("filename", "unknown.txt"))
        content = str(payload.get("content", ""))
        if content:
            from .novel_loader import NovelLoader
            loader = NovelLoader()
            # 优先尝试 LLM 抽取（需要 pipeline 的 provider）
            if session.pipeline:
                try:
                    provider = session.pipeline._get_provider_for_tier("medium")
                except Exception:
                    provider = None

                if provider:
                    canon_data = await loader.extract_canon_with_llm(provider, content, filename)
                else:
                    canon_data = await loader.extract_canon_from_text(content, filename)
            else:
                canon_data = await loader.extract_canon_from_text(content, filename)
            if canon_data:
                # ── 持久化：保存 TXT 原文 + Canon JSON 到磁盘 ──
                from .paths import NOVEL_DIR as _NOVEL_DIR
                novel_dir = _NOVEL_DIR
                novel_dir.mkdir(exist_ok=True)

                novel_title = canon_data.get("title", filename.rsplit(".", 1)[0])
                safe_name = "".join(c for c in novel_title if c.isalnum() or c in "._- ()（）")
                if not safe_name:
                    safe_name = "uploaded_novel"

                # 保存 TXT 原文
                txt_path = novel_dir / f"{safe_name}.txt"
                try:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    _log.info("TXT 原文已保存: %s", txt_path)
                except Exception:
                    pass  # TXT 保存失败不阻断主流程

                # 保存 Canon JSON
                loader.save_canon_json(canon_data, novel_title)

                session.world_state.canon = canon_data
                session.current_novel = filename
                await ws_manager.send_json(websocket, {
                    "type": "canon_ready",
                    "payload": session.canon_ready_payload(),
                })
            else:
                await ws_manager.send_json(websocket, {
                    "type": "error",
                    "payload": {"code": "CANON_FAILED", "message": "无法从文本中提取 Canon 数据"},
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
                "payload": {"success": True},
            })
        except Exception as exc:
            await ws_manager.send_json(websocket, {
                "type": "error",
                "payload": {"code": "CONFIG_FAILED", "message": str(exc)},
            })

    else:
        await ws_manager.send_json(websocket, {
            "type": "error",
            "payload": {"code": "UNKNOWN_TYPE", "message": f"未知消息类型: {msg_type}"},
        })
