# -*- coding: utf-8 -*-
"""游戏会话编排器 — 连接 WebSocket ↔ Pipeline ↔ WorldState

GameSession 是游戏循环的核心，负责:
  1. 初始化 MaNA 管线
  2. 接收玩家输入 → 调用 Pipeline → 流式推送叙事
  3. 自动存档、结局检测（U6+ 移除结局阈值机制）
  4. 小说选择流程：扫描 canon 列表、加载/生成/导入 canon

架构:
  - 使用 Extractor 模式进行 Canon 抽取（可替换）
  - 使用 CanonStorage 接口进行 Canon 存储（可替换）
  - 默认使用 LLM 提取器 + 文件存储
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import re
import shutil
import time
import yaml
from pathlib import Path
from typing import Any, Callable, Optional

from .world_state import WorldState
from server.data.save_manager import SaveManager
from server.data.canon_manager import CanonManager
from server.data.novel_loader import NovelLoader
from server.config.paths import NOVEL_DIR

from server.storage import get_storage
from server.manana.defaults import get_default_choices

_log = logging.getLogger("Rain.GameSession")

# ── 默认 choices（当 SceneComposer 未返回有效 choices 时使用）
#    统一从 manana/defaults.py 导入

class GameSession:
    """游戏会话编排器

    每个 WebSocket 连接对应一个 GameSession 实例。
    """

    def __init__(
        self,
        session_id: str,
        storage_name: str = "file",
        **kwargs: Any,
    ) -> None:
        """初始化游戏会话

        Args:
            session_id: 会话 ID
            storage_name: 存储后端名称（默认 "file"）
            **kwargs: 传递给存储后端构造函数的参数
        """
        self.session_id: str = session_id
        self.world_state: WorldState = WorldState()
        self.pipeline: Optional[Any] = None  # MananaPipeline
        self.beat_count: int = 0
        self.is_active: bool = False
        self.current_novel: str = ""
        self.event_log: list[dict] = []
        self.save_manager: SaveManager = SaveManager()

        # 使用存储后端
        storage = get_storage(storage_name, **kwargs)
        self.canon_manager: CanonManager = CanonManager(storage=storage)

        self._config_path: str = ""
        self._auto_save_interval: int = 10
        # 结局阈值已移除（U6+ 使用叙事张力驱动的动态演化）
        self._skip_typing: bool = False

        # ── 新增：小说选择流程状态 ──
        self._generation_in_progress: bool = False
        self._current_agent: Optional[str] = None  # 当前正在执行的 agent
        self._last_scan_result: dict = {}
        self._last_pipeline_result: dict = {}  # 上一拍的 pipeline 完整结果（供在场角色判定等使用）

    # ── 默认 Choices（灵魂模式）──

    @staticmethod
    def _get_default_choices() -> dict:
        """返回默认 soul_decision，统一从 manana/defaults.py 获取。"""
        return get_default_choices(3)

    # ────────────────────────────────────────────────
    # 提取器懒加载
    # ────────────────────────────────────────────────

    def set_storage(self, name: str, **kwargs: Any) -> None:
        """设置存储后端（运行时切换）

        Args:
            name: 存储后端名称
            **kwargs: 传递给存储后端构造函数的参数
        """
        storage = get_storage(name, **kwargs)
        self.canon_manager = CanonManager(storage=storage)
        _log.info("存储后端已切换: %s", name)

    # ────────────────────────────────────────────────
    # 生命周期
    # ────────────────────────────────────────────────

    async def initialize(self, config_path: str = "") -> None:
        """初始化游戏会话：加载配置、初始化管线

        注意：不再自动加载 Canon。启动后前端通过 request_canon_list
        消息获取 scan 结果，由用户决定加载、生成或导入。

        Args:
            config_path: config.yaml 路径
        """
        self._config_path = config_path

        # 加载 YAML 配置
        try:
            config_file = Path(config_path)
            if config_file.is_file():
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
            else:
                cfg = {}
        except Exception as exc:
            _log.warning("加载 config.yaml 失败: %s，使用默认配置", exc)
            cfg = {}

        # 缓存配置供前端查询
        self._config_yaml = cfg

        # 读取游戏设置
        game_cfg = cfg.get("game", {}) or {}
        self._auto_save_interval = int(game_cfg.get("auto_save_interval", 10))
        # ending_divergence_threshold 已移除（U6+ 使用动态叙事演化）

        # 初始化管线（直接传 YAML dict，不再生成 INI 文件）
        # 加超时保护，避免阻塞 WS 连接
        try:
            from server.manana.pipeline import MananaPipeline
            self.pipeline = MananaPipeline(yaml_dict=cfg)
            # 超时 10 秒，避免阻塞 WS 连接
            try:
                await asyncio.wait_for(self.pipeline.initialize(), timeout=10.0)
                _log.info("MaNA 管线初始化成功: session=%s", self.session_id)
            except asyncio.TimeoutError:
                _log.warning("MaNA 管线初始化超时（10s），跳过，游戏将使用回退模式")
                self.pipeline = None
            except Exception as exc:
                _log.error("MaNA 管线初始化失败: %s", exc)
                self.pipeline = None
        except Exception as exc:
            _log.error("MaNA 管线导入失败: %s", exc)
            self.pipeline = None

        self.is_active = True
        _log.info("GameSession 初始化完成: session=%s (未加载 Canon)", self.session_id)

    def _scan_available_canons(self) -> dict:
        """扫描 novel/ 目录，返回可用资源列表

        这是 _load_canon_on_startup() 的替代。只扫描不加载，
        将决策权交给前端。

        检测运行 Canon：扫描 novel/*/meta.json 识别已存在的运行 Canon 目录。

        Returns:
            ScanResult 字典:
            {
                "txt_files": [...],
                "canons": [...],
                "has_existing_canon": bool,
                "has_txt_files": bool,
                "running_canons": [{"title": str, "dir": str, "char_count": int, "loc_count": int}],
                "has_running_canon": bool,
            }
        """
        try:
            loader = NovelLoader()
            result = loader.scan_novel_directory("novel")
            self._last_scan_result = result
            canons_count = len(result.get("canons", []))
            txt_count = len(result.get("txt_files", []))
            running_count = len(result.get("running_canons", []))
            _log.info(
                "Canon 扫描完成: %d canons, %d txt 文件, %d 运行 Canons",
                canons_count, txt_count, running_count
            )
            return result
        except Exception as exc:
            _log.warning("扫描 Canon 失败: %s", exc)
            empty_result = {
                "txt_files": [],
                "canons": [],
                "has_existing_canon": False,
                "has_txt_files": False,
                "running_canons": [],
                "has_running_canon": False,
            }
            self._last_scan_result = empty_result
            return empty_result

    # ────────────────────────────────────────────────
    # Canon 管理（新增）
    # ────────────────────────────────────────────────

    def load_existing_canon(self, source_file: str) -> bool:
        """加载指定的 Canon JSON 文件并创建运行副本

        新流程:
          1. 读取初始 Canon JSON
          2. 调用 canon_manager.create_running_canon() 创建运行副本
          3. 加载运行 Canon
          4. 应用到 world_state

        Args:
            source_file: Canon JSON 文件路径（如 novel/canon_xxx.json）

        Returns:
            是否加载成功
        """

        # 1. 读取初始 Canon
        try:
            source_path = Path(source_file)
            if not source_path.is_file():
                _log.error("Canon 文件不存在: %s", source_file)
                return False

            with open(source_path, "r", encoding="utf-8") as f:
                initial_canon = _json.load(f)
        except Exception as exc:
            _log.error("读取初始 Canon 失败: %s, error=%s", source_file, exc)
            return False

        if not isinstance(initial_canon, dict):
            _log.error("Canon JSON 格式无效: %s", source_file)
            return False

        # 2. 创建运行 Canon 副本（拆成形态B：角色/地点/world_rules 独立文件）
        title = str(initial_canon.get("title", source_path.stem.replace("canon_", "", 1)))
        ok = self.canon_manager.create_running_canon(
            str(source_file),
            initial_data=initial_canon,  # ★ 传入已读取的完整数据，跳过B→A回读
        )
        if not ok:
            _log.error("创建运行 Canon 失败: %s", source_file)
            return False

        # 3. 从 canon_manager 获取运行时 Canon（完整版，非形态B重建）
        running_canon = self.canon_manager.get_running_canon()
        if running_canon is None:
            _log.error("获取运行时 Canon 失败: %s", title)
            return False

        # 4. 应用到 world_state
        running_canon["_source_file"] = str(source_file)
        self._apply_canon_to_world_state(running_canon)
        self.current_novel = title

        # ★ 灵魂附生初始化（唯一模式，protagonist_id 由 request_game_start_soul 流程设置）
        protagonist_id = getattr(self, '_soul_protagonist_id', '')
        if protagonist_id:
            self._init_soul_possession(running_canon, protagonist_id)

        _log.info(
            "Canon 已加载 (目录结构模式): %s → novel/%s/ (source=%s)",
            source_file,
            title,
            "running",
        )
        return True

    # ────────────────────────────────────────────────
    # 灵魂附生初始化
    # ────────────────────────────────────────────────

    def _init_soul_possession(
        self, running_canon: dict, protagonist_id: str
    ) -> None:
        """初始化灵魂附生状态

        1. 从 Canon 加载主角人格
        2. 初始化 NPC 认知冲突
        3. 设置 WorldState 灵魂附生状态
        """
        self._soul_protagonist_id = protagonist_id
        from server.manana.soul.soul_state import (
            PlayerSoulProfile,
            SoulPossessionState,
            NPCCognitiveDissonance,
        )

        ws = self.world_state

        # 1. 提取主角 Canon 人格
        protagonist = None
        for c in running_canon.get("characters", []):
            if c.get("id") == protagonist_id:
                protagonist = c
                break
        if not protagonist:
            _log.warning("未找到主角 %s，跳过灵魂附生初始化", protagonist_id)
            return

        # ★ 同步玩家位置到主角初始位置（解析 location ID → 名称）
        start_loc_id = protagonist.get("starting_location", protagonist.get("first_appearance", ""))
        if start_loc_id:
            # 从 Canon locations 列表中解析位置名称
            loc_name = start_loc_id  # 默认使用 ID
            for loc in running_canon.get("locations", []) or []:
                if isinstance(loc, dict) and loc.get("id") == start_loc_id:
                    loc_name = loc.get("name", start_loc_id)
                    break
            ws.player_location = loc_name
            _log.debug("玩家位置已同步: %s → %s (id=%s)", protagonist.get("name", protagonist_id), loc_name, start_loc_id)

        # ★ 同步 player_profile 到主角（灵魂附生：玩家 = 选定角色）
        personality = dict(protagonist.get("personality", {}))
        ws.player_profile = {
            "traits": list(protagonist.get("key_traits", [])),
            "motivation": personality.get("core_motivation", ""),
            "tendency": str(protagonist.get("role", "中立")),
            "name": protagonist.get("name", ""),
            "character_id": protagonist_id,
        }

        # ★ 设置主角 ID，建立 player ↔ protagonist 双向同步
        ws._protagonist_id = protagonist_id

        canon_personality = {
            "id": protagonist.get("id", ""),
            "name": protagonist.get("name", ""),
            "role": str(protagonist.get("role", "")),
            "personality": dict(protagonist.get("personality", {})),
            "abilities": list(protagonist.get("abilities", [])),
            "key_traits": list(protagonist.get("key_traits", [])),
        }

        # 2. 灵魂状态
        ws.soul_possession = SoulPossessionState(
            canon_soul=canon_personality,
            player_soul=PlayerSoulProfile.default(),
            dominant_soul="player",
            blend_ratio=0.8,
        )

        # 3. 初始化 NPC 认知冲突
        for npc in running_canon.get("characters", []):
            if npc.get("id") == protagonist_id:
                continue
            memory = npc.get("memory_of_protagonist", {}).get(protagonist_id, {})
            if not memory:
                # 从 relationships 降级推断
                for rel in npc.get("relationships", []):
                    if rel.get("target") == protagonist_id:
                        memory = self._infer_memory_from_rel(rel, npc)
                        break

            ws.cognitive_dissonance[npc["id"]] = NPCCognitiveDissonance(
                char_id=npc["id"],
                memory_of_protagonist=dict(memory),
            )

        _log.info(
            "灵魂附生已初始化: 主角=%s, NPC认知=%d个",
            protagonist.get("name", ""),
            len(ws.cognitive_dissonance),
        )

        # ★ 双向同步 player ↔ protagonist 状态
        ws.reconcile_player_state()

    @staticmethod
    def _infer_memory_from_rel(rel: dict, npc: dict) -> dict:
        """从 relationships 降级推断 NPC 记忆"""
        rel_type = rel.get("type", "")
        intensity = rel.get("intensity", 0)
        expected = "正常"
        if "仇敌" in rel_type:
            expected = "敌视、警惕"
        elif "朋友" in rel_type or "挚友" in rel_type:
            expected = "友善、信任"
        elif "家人" in rel_type or "兄妹" in rel_type:
            expected = "亲近、依赖"
        return {
            "expected_behavior": expected,
            "trust_level": max(0.3, abs(intensity)),
            "relationship_note": rel_type,
            "impression": npc.get("name", "") + "记忆中" + expected,
        }

    def update_canon_entry(
        self,
        entity_type: str,
        action: str,
        entry_id: str,
        data: dict,
    ) -> dict:
        """更新/新增/删除 Canon 条目

        委托给 canon_manager 执行实际 CRUD，然后同步 world_state。

        Args:
            entity_type: 'character' | 'location' | 'world_rule'
            action: 'create' | 'update' | 'delete'
            entry_id: 目标条目 ID
            data: 条目数据

        Returns:
            {"success": bool, "message": str, "entry_id": str}
        """
        # 将前端的 entity_type 映射到 can_manager 的 section
        section_map = {
            "character": "characters",
            "location": "locations",
            "world_rule": "world_rules",
        }
        section = section_map.get(entity_type, entity_type)

        success, updated_canon, message = self.canon_manager.save_canon_entry(
            section=section,
            action=action,
            entry_data=data,
            entry_id=entry_id,
        )

        if success:
            # 同步 world_state.canon
            self.world_state.canon = updated_canon
            # 同步 characters_state（刷新角色注册信息）
            self._sync_characters_state_from_canon(updated_canon)

        return {
            "success": success,
            "message": str(message),
            "entry_id": str(message) if success and action == "create" else entry_id,
        }

    def canon_ready_payload(self) -> dict:
        """构建增强的 canon_ready 消息负载

        包含 meta、world_rules、source 字段。
        手动模式下 world_state.canon 可能为空，从 canon_manager 读取。

        Returns:
            canon_ready payload 字典
        """
        canon = self.world_state.canon or {}
        # ★ 手动模式：从 running_canon 获取
        if not canon.get("characters"):
            running = self.canon_manager.get_running_canon()
            if running:
                canon = running
        return {
            "novel_title": self.current_novel,
            "characters": canon.get("characters", []),
            "locations": canon.get("locations", []),
            "world_rules": canon.get("world_rules", {}),
            "meta": canon.get("meta", {}),
            "source": canon.get("_source", "initial"),
        }

    def _sync_characters_state_from_canon(self, canon: dict) -> None:
        """从 Canon 刷新 characters_state（角色注册信息）

        用于编辑后同步，不会覆盖运行时状态（mood、attitude 等）。
        """
        for c in canon.get("characters", []) or []:
            c = c if isinstance(c, dict) else {}
            cid = str(c.get("id", ""))
            if not cid:
                continue

            personality = c.get("personality", {}) or {}
            status = c.get("status", "alive")

            if cid not in self.world_state.characters_state:
                self.world_state.characters_state[cid] = {}

            cs = self.world_state.characters_state[cid]
            cs.setdefault("name", c.get("name", cid))
            cs.setdefault("mood", "中性")
            cs.setdefault("attitude", "中立")
            cs.setdefault("motivation", personality.get("core_motivation", ""))
            cs.setdefault("reputation", 0.0)
            cs.setdefault("location", c.get("starting_location", c.get("first_appearance", "未知")))
            # 更新死亡状态
            if status == "dead":
                cs["status"] = "dead"
                cs["death_location"] = c.get("death_location", "")
                cs["death_time"] = c.get("death_time", "")
                cs["death_cause"] = c.get("death_cause", "")

    def _replace_ids_with_names(self, text: str) -> str:
        """将叙事文本中的 raw ID 替换为可读名称

        Args:
            text: 原始叙事文本

        Returns:
            替换后的文本
        """
        if not text:
            return text

        canon = self.world_state.canon or {}
        result = text

        # 长 ID 优先替换，避免部分匹配（如 char_001 被 char_00 误替换）
        chars = sorted(canon.get("characters", []) or [], key=lambda c: len(c.get("id", "")), reverse=True)
        for c in chars:
            cid = c.get("id", "")
            cname = c.get("name", "")
            if cid and cname:
                result = result.replace(cid, cname)

        locs = sorted(canon.get("locations", []) or [], key=lambda l: len(l.get("id", "")), reverse=True)
        for loc in locs:
            lid = loc.get("id", "")
            lname = loc.get("name", "")
            if lid and lname:
                result = result.replace(lid, lname)

        return result


    def import_canon_json(self, json_content: str, filename: str = "") -> tuple:
        """验证并导入 Canon JSON 内容

        Args:
            json_content: JSON 字符串
            filename: 原始文件名（用于日志和保存）

        Returns:
            (success: bool, message: str)
        """
        loader = NovelLoader()

        canon_data = loader.import_canon_from_json(json_content)
        if canon_data is None:
            return (False, "JSON 解析失败或缺少必要字段（需要 title 或 characters）")

        # 保存 JSON 到 novel/ 目录
        title = canon_data.get("title", filename.rsplit(".", 1)[0] if filename else "imported")
        safe_name = "".join(c for c in title if c.isalnum() or c in "._- ()（）")
        if not safe_name:
            safe_name = "imported"

        out_dir = NOVEL_DIR
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"canon_{safe_name}.json"
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                _json.dump(canon_data, f, ensure_ascii=False, indent=2)
            _log.info("导入 Canon 已保存: %s", out_path)
        except Exception as exc:
            _log.error("保存导入 Canon 失败: %s", exc)
            return (False, f"保存文件失败: {exc}")

        # 应用到 world_state
        self._apply_canon_to_world_state(canon_data)
        self.current_novel = title
        _log.info("Canon JSON 导入成功: %s", title)

        char_count = len(canon_data.get("characters", []) or [])
        loc_count = len(canon_data.get("locations", []) or [])
        return (True, f"导入成功：{title}（{char_count} 角色, {loc_count} 地点）")

    # ────────────────────────────────────────────────
    # 辅助：将 Canon 应用到 WorldState
    # ────────────────────────────────────────────────

    def _apply_canon_to_world_state(self, canon: dict) -> None:
        """将 Canon 数据注入 world_state，注册角色到 characters_state

        处理 status: "dead" 角色的死亡信息。

        Args:
            canon: Canon 字典
        """
        self.world_state.canon = canon

        # 将 Canon 角色注册到 characters_state
        for c in canon.get("characters", []) or []:
            c = c if isinstance(c, dict) else {}
            cid = str(c.get("id", c.get("name", "")))
            if cid and cid not in self.world_state.characters_state:
                # 提取 personality 相关信息
                personality = c.get("personality", {}) or {}
                char_entry = {
                    "name": c.get("name", cid),
                    "mood": "中性",
                    "attitude": "中立",
                    "motivation": personality.get("core_motivation", ""),
                    "location": c.get("starting_location", c.get("first_appearance", "未知")),
                }
                # 处理死亡状态
                status = c.get("status", "alive")
                if status == "dead":
                    char_entry["status"] = "dead"
                    char_entry["death_location"] = c.get("death_location", "")
                    char_entry["death_time"] = c.get("death_time", "")
                    char_entry["death_cause"] = c.get("death_cause", "")
                self.world_state.characters_state[cid] = char_entry

        char_count = len(canon.get("characters", []) or [])
        _log.debug("Canon 已应用到 world_state: %d 角色已注册", char_count)

    # ────────────────────────────────────────────────
    # 切换小说前检查
    # ────────────────────────────────────────────────

    def can_switch_novel(self) -> tuple[bool, str]:
        """检查当前是否允许切换小说

        Returns:
            (允许: bool, 原因: str)
        """
        if self.beat_count > 0:
            return (False, "游戏进行中，无法切换小说")
        if self._generation_in_progress:
            return (False, "世界观数据生成中，请稍后再试")
        # 手动模式：已创建 running canon 后不允许切换
        if self.canon_manager.is_running():
            return (False, "当前小说已创建，无法切换（请刷新页面重新开始）")
        return (True, "")

    async def cleanup(self) -> None:
        """清理资源"""
        self._generation_in_progress = False

        if self.pipeline:
            try:
                await self.pipeline.cleanup()
            except Exception as exc:
                _log.warning("管线清理异常: %s", exc)
        self.is_active = False

    # ────────────────────────────────────────────────
    # 核心游戏循环
    # ────────────────────────────────────────────────

    async def run_beat(self, player_action: str, progress_cb=None, soul_choice: Optional[dict] = None) -> dict:
        """执行一个叙事节拍（非流式，返回完整结果）

        Args:
            player_action: 玩家输入文本
            progress_cb: 可选异步回调(agent_key, label)，推送 agent 状态到前端

        Returns:
            Pipeline 输出字典
        """
        if not self.pipeline:
            return {"error": "Pipeline 未初始化"}

        self.beat_count += 1
        self._skip_typing = False
        self._generation_in_progress = True

        try:
            result = await self.pipeline.run_beat(player_action, self.world_state, progress_cb=progress_cb, soul_choice=soul_choice, needs_soul_choices=self._needs_soul_choice())
        except asyncio.CancelledError:
            _log.info("run_beat 被取消")
            # 直接向上抛，让 stream_beat → main.py 的 CancelledError 处理器处理
            raise
        except Exception as exc:
            import traceback
            _log.error("Pipeline run_beat 异常: %s\n%s", exc, traceback.format_exc())
            self._generation_in_progress = False
            return {"error": f"Pipeline 执行失败: {exc}"}
        finally:
            self._generation_in_progress = False

        if "error" in result:
            return result

        # 应用状态补丁
        state_patch = result.get("state_patch", {}) or {}
        self.world_state.apply_patch(state_patch)

        # 推进时间
        self.world_state.advance_time()

        # ★ 认知冲突更新（第一档：纯本地）
        dissonance_map = self.world_state.cognitive_dissonance
        if dissonance_map:
            from server.manana.soul import DissonanceUpdater, SocialPropagator, ScratchpadManager
            soul_decision = result.get("soul_decision", {}) or {}
            soul_possession = self.world_state.soul_possession
            recent_actions = [soul_decision] if soul_decision else []

            updater = DissonanceUpdater()
            changes = updater.update_all(
                dissonance_map,
                soul_possession.canon_soul if soul_possession else {},
                soul_possession.player_soul.to_dict() if soul_possession else {},
                recent_actions,
            )

            # ★ NPC 认知笔记写入 + theory_of_change 模板
            beat_id = f"beat_{self.beat_count:03d}"
            protagonist_name = (
                soul_possession.canon_soul.get("name", "主角")
                if soul_possession else "主角"
            )
            scratchpad = ScratchpadManager()
            for cid, ch in changes.items():
                if not ch.get("dissonance_delta", 0):
                    continue
                state = dissonance_map.get(cid)
                if state is None:
                    continue
                scratchpad.add_observation(
                    state,
                    beat_id=beat_id,
                    action_type=soul_decision.get("action_type", "auto"),
                    observed_behavior=(
                        f"{protagonist_name}: {soul_decision.get('decision', '')}"
                    ),
                    npc_reaction=(
                        "感到有些不对劲"
                        if soul_decision.get("action_type") == "authentic"
                        else "觉得一切正常"
                    ),
                    is_important=abs(ch.get("dissonance_delta", 0)) >= 0.08,
                )
                # theory_of_change 模板
                score = ch.get("new_score", 0)
                if score >= 0.50 and not state.theory_of_change:
                    state.theory_of_change = (
                        f"开始怀疑「{protagonist_name}」是不是遇到了什么重大变故…"
                    )
                elif score >= 0.25 and not state.theory_of_change:
                    state.theory_of_change = (
                        f"最近总觉得「{protagonist_name}」有些不对劲…"
                    )

            propagator = SocialPropagator()
            social_graph = self._build_social_graph()
            if social_graph:
                propagator.propagate(dissonance_map, social_graph)



        # 添加叙事历史
        narrative_text = result.get("narrative_text", "") or ""
        summary = str(state_patch.get("narrative_summary", narrative_text[:100]))
        self.world_state.add_narrative_event(summary, f"beat_{self.beat_count:03d}")

        # 偏离度已在 apply_patch 中通过 divergence_delta 更新
        # 事件日志（保存全文，读档时仅渲染最后一条）
        self.event_log.append({
            "beat_id": f"beat_{self.beat_count:03d}",
            "time": self.world_state.game_time,
            "type": result.get("narrative_mode", "event"),
            "text": narrative_text,
        })

        # 自动存档
        if self.beat_count % self._auto_save_interval == 0:
            self.save_manager.save(0, self, "自动存档")

        # 确保 soul_decision 字段存在
        if not result.get("soul_decision"):
            result["soul_decision"] = self._get_default_choices()

        # 结局检测已移除（U6+：使用叙事张力驱动的动态演化，不再依赖固定偏离度阈值）
        return result

    async def stream_beat(
        self,
        player_action: str,
        send_chunk: Callable[[dict], Any],
        soul_choice: Optional[dict] = None,
    ) -> None:
        """流式执行节拍 — 分块推送叙事文本

        先批量调用 Pipeline（通过 progress_cb 在每层推送 agent_status），
        然后将 narrative_text 分块推送。

        Args:
            player_action: 玩家输入
            send_chunk: 异步回调，每块调用 send_chunk(chunk_dict)
        """
        # 从 session 属性读取 soul_choice（由 main.py 从 payload 提取后设置）
        if soul_choice is None:
            soul_choice = getattr(self, '_soul_choice', None)
            self._soul_choice = None  # ★ 消费后清除，防止跨 beat 泄漏
        # ── 构建 progress_cb，由 Pipeline 内部在各层推送 agent_status ──
        async def progress_cb(agent: str, label: str) -> None:
            await send_chunk({
                "type": "agent_status",
                "payload": {"agent": agent, "label": label},
            })

        result = await self.run_beat(player_action, progress_cb=progress_cb, soul_choice=soul_choice)
        self._last_pipeline_result = result  # 保存供 _get_present_character_ids 使用

        # 叙事文本 ID 审计
        if "narrative_text" in result and result["narrative_text"]:
            result["narrative_text"] = self._replace_ids_with_names(result["narrative_text"])

        if "error" in result:
            # 出错时清除 agent 状态
            await send_chunk({
                "type": "agent_status",
                "payload": {"agent": None, "label": ""},
            })
            await send_chunk({
                "type": "error",
                "payload": {"code": "PIPELINE_FAILED", "message": result["error"]},
            })
            return

        narrative_text: str = result.get("narrative_text", "") or ""
        action_hints: list = result.get("action_hints", []) or []
        ending_hook: str = result.get("ending_hook", "") or ""
        narrative_mode: str = result.get("narrative_mode", "event")
        deviation: float = self.world_state.world_divergence

        # ── 清除 agent 状态（Pipeline 已完成） ──
        await send_chunk({
            "type": "agent_status",
            "payload": {"agent": None, "label": ""},
        })

        # ── 流式分块缓冲配置 ──
        CHUNK_DELAY = 0.35     # 块间延迟 350ms（≈人类阅读节奏，略慢）
        BUFFER_CHUNKS = 3       # 最后 N 块合并为一个
        COMPLETION_PAUSE = 0.6  # narrative_complete 前停顿 600ms

        # 按句号/换行分块
        chunks = self._split_narrative(narrative_text)
        total = len(chunks)

        # 合并最后 BUFFER_CHUNKS 块（如果总数足够）
        if total > BUFFER_CHUNKS:
            buffer_part = "".join(chunks[-BUFFER_CHUNKS:])
            normal_chunks = chunks[:-BUFFER_CHUNKS]
        else:
            buffer_part = None
            normal_chunks = chunks

        # ── 发送普通块（带延迟） ──
        for i, chunk in enumerate(normal_chunks):
            if self._skip_typing:
                remaining = "".join(normal_chunks[i:])
                if buffer_part:
                    remaining += buffer_part
                await send_chunk({
                    "type": "narrative_chunk",
                    "payload": {
                        "text": remaining,
                        "chunk_index": total,
                        "is_complete": True,
                    },
                })
                break

            await send_chunk({
                "type": "narrative_chunk",
                "payload": {
                    "text": chunk,
                    "chunk_index": i,
                    "is_complete": False,
                },
            })
            await asyncio.sleep(CHUNK_DELAY)

        # ── 发送缓冲块 ──
        if buffer_part and not self._skip_typing:
            await send_chunk({
                "type": "narrative_chunk",
                "payload": {
                    "text": buffer_part,
                    "chunk_index": total - 1,
                    "is_complete": False,
                },
            })

        # ── 完成前停顿（给前端过渡动画时间） ──
        await asyncio.sleep(COMPLETION_PAUSE)

        # 叙事完成（始终发送 soul 状态/认知冲突）
        soul_decision = result.get("soul_decision", {})
        if not isinstance(soul_decision, dict) or not soul_decision.get("authentic"):
            # 从 Composer 的 choices 派生（场景感知的），差别的 hint 驱动叙事差异
            composer_choices = result.get("choices", []) or []
            if not isinstance(composer_choices, list):
                composer_choices = []
            auth_actions = [
                {"id": c.get("id", f"auth_{i}"), "text": c.get("text", ""),
                 "hint": "展现真实自我", "next_scene_hint": "本我行动"}
                for i, c in enumerate(composer_choices[:3]) if isinstance(c, dict)
            ]
            conf_actions = [
                {"id": c.get("id", f"conf_{i}"), "text": c.get("text", ""),
                 "hint": "维持原有身份", "next_scene_hint": "贴合角色"}
                for i, c in enumerate(composer_choices[:3]) if isinstance(c, dict)
            ]
            if not auth_actions:
                auth_actions = [
                    {"id": "auth_1", "text": "按自己的方式行动", "hint": "展现真实性格", "next_scene_hint": "本我行动"},
                    {"id": "auth_2", "text": "说出真心话", "hint": "不再伪装", "next_scene_hint": "真情流露"},
                ]
                conf_actions = [
                    {"id": "conf_1", "text": "模仿原主的口吻", "hint": "维持身份", "next_scene_hint": "维持身份"},
                    {"id": "conf_2", "text": "按原主的习惯行事", "hint": "不暴露异常", "next_scene_hint": "融入角色"},
                ]
            soul_decision = {
                "authentic": auth_actions,
                "conforming": conf_actions,
            }
        await send_chunk({
            "type": "narrative_complete",
            "payload": {
                "beat_id": f"beat_{self.beat_count:03d}",
                "narrative_text": narrative_text,
                "narrative_mode": narrative_mode,
                "ending_hook": ending_hook,
                "deviation": deviation,
                "characters_present": self._get_present_character_ids(),
                "state_patch_summary": self._get_state_summary(),
                "needs_soul_choice": self._needs_soul_choice(),
                "soul_decision": soul_decision,
                "soul_state": self._get_soul_state_payload(),
                "cognitive_dissonance": self._get_dissonance_summary(),
            },
        })

        # 偏离度更新
        await send_chunk({
            "type": "deviation_update",
            "payload": {"value": deviation, "delta": 0.0},
        })

        # 状态同步
        await send_chunk({
            "type": "state_sync",
            "payload": self.get_state_snapshot(),
        })

        # 灵魂附生状态同步（唯一模式，始终发送）
        await send_chunk({
            "type": "soul_state_update",
            "payload": self._get_soul_state_payload(),
        })

        # 结局处理已移除（U6+：不再依赖固定偏离度阈值触发结局，改为动态演化）

    def cancel_typing(self) -> None:
        """跳过当前打字机动画"""
        self._skip_typing = True

    # ────────────────────────────────────────────────
    # 分块策略
    # ────────────────────────────────────────────────

    @staticmethod
    def _split_narrative(text: str) -> list[str]:
        """按语义块分割叙事文本（段落 + 角色发言）

        分割规则：
        1. 空行作为主分块边界
        2. 如果空行分块后 < 3 块，则按行分割，角色头【角色名】触发新块
        3. 空文本至少返回一个块

        Args:
            text: 完整叙事文本

        Returns:
            语义块列表
        """
        # Step 1: 按空行分割
        raw_blocks = re.split(r'\n\s*\n', text.strip())

        chunks: list[str] = []
        for block in raw_blocks:
            block = block.strip()
            if not block:
                continue
            chunks.append(block)

        # Step 2: 如果空行分割块太少，按单行+语义分割（回退策略）
        if len(chunks) < 3:
            lines = text.strip().split('\n')
            chunks = []
            current: list[str] = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    if current:
                        chunks.append('\n'.join(current))
                        current = []
                    continue
                # 角色头部（如【伊琳娜·菲利亚德】）触发新块
                if stripped.startswith('【') and '】' in stripped:
                    if current:
                        chunks.append('\n'.join(current))
                    current = [stripped]
                else:
                    current.append(stripped)
            if current:
                chunks.append('\n'.join(current))

        if not chunks:
            chunks = [text]
        return chunks

    # ────────────────────────────────────────────────
    # 状态快照
    # ────────────────────────────────────────────────

    def get_config_info(self) -> dict:
        """获取当前配置信息（发送给前端预填设置面板）

        从 pipeline 的 MananaConfig 读取实际配置值，不受 config.yaml 键名语言影响。
        """
        result = {"providers": {}}

        # 优先从 pipeline 读取（支持中文/旧名双识别）
        if self.pipeline and hasattr(self.pipeline, '_config') and self.pipeline._config:
            mc = self.pipeline._config
            for tier in ("strong", "medium", "light"):
                try:
                    tc = mc.get_tier_config(tier)
                    ep = tc.get("endpoint", "")
                    # 去掉 runtime 拼接的后缀，前端显示裸地址
                    ep = ep.rstrip("/").replace("/api/chat", "").replace("/v1/chat/completions", "")
                    result["providers"][tier] = {
                        "type": tc.get("type", "ollama"),
                        "endpoint": ep,
                        "model": tc.get("model", ""),
                        "temperature": tc.get("temperature", 0.7),
                        "max_tokens": tc.get("max_tokens", 2048),
                        "timeout": tc.get("timeout", 120),
                        "api_key": tc.get("api_key", ""),
                    }
                except Exception:
                    result["providers"][tier] = {}
            result["api_key"] = ""
            if "strong" in result["providers"]:
                try:
                    tc = mc.get_tier_config("strong")
                    result["api_key"] = tc.get("api_key", "")
                except Exception:
                    _log.warning("获取 tier_config 失败，api_key 不可用")
                    pass
            result["available_models"] = getattr(self, '_available_models', [])
            return result

        # fallback: 从原始 yaml dict 读取（兼容中文/旧名两种键）
        cfg = self._config_yaml if hasattr(self, '_config_yaml') else {}
        providers = cfg.get("providers", {}) or {}

        # 将中文层名映射回内部名（用绝对导入，兼容 EXE 打包环境）
        try:
            from server.manana.config import resolve_tier
        except ImportError:
            # 回退：手动实现 resolve_tier
            def resolve_tier(name: str) -> str:
                m = {"导演层": "strong", "演员层": "medium", "动作层": "light",
                       "strong": "strong", "medium": "medium", "light": "light",
                       "director": "strong", "actor": "medium", "action": "light"}
                return m.get(name, name)
        tier_map = {}
        for k, v in providers.items():
            tier_map[resolve_tier(k)] = v

        for tier in ("strong", "medium", "light"):
            t = tier_map.get(tier, {}) or {}
            result["providers"][tier] = {
                "type": t.get("type", "ollama"),
                "endpoint": t.get("endpoint", ""),
                "model": t.get("model", ""),
                "temperature": t.get("temperature", 0.7),
                "max_tokens": t.get("max_tokens", 2048),
                "timeout": t.get("timeout", 120),
                "api_key": t.get("api_key", ""),
            }

        result["api_key"] = ""
        first = tier_map.get("strong", {}) or {}
        if first:
            result["api_key"] = first.get("api_key", "")
        return result

    def get_state_snapshot(self) -> dict:
        """获取当前状态快照（发送给前端）

        注意：canon 为空时返回空 dict，前端需处理 None 情况。
        protagonist 数据已与 player_profile/player_location 双向同步，
        characters_state 中包含主角完整运行时状态。
        """
        canon = self.world_state.canon or {}
        return {
            "characters_state": self.world_state.characters_state,
            "player_location": self.world_state.player_location,
            "game_time": self.world_state.game_time,
            "beat_count": self.beat_count,
            "event_log": self.event_log[-20:],  # 最近 20 条
            "divergence": self.world_state.world_divergence,
            "player_profile": self.world_state.player_profile,
            "player_reputation": self.world_state.player_reputation,
            "session_id": self.session_id,
            "novel_title": self.current_novel or "",
            "protagonist_id": getattr(self, "_soul_protagonist_id", ""),
            "canon_ready": bool(self.current_novel),
            "is_generating": self._generation_in_progress,
            "current_agent": self._current_agent or "",
            # F8 叙事线索（供前端 ThreadsRenderer 渲染）
            "narrative_threads": self.world_state.narrative_threads,
        }

    # ═══════════════════════════════════════════════════
    # 灵魂附生 — 状态负载
    # ═══════════════════════════════════════════════════

    def _get_soul_state_payload(self) -> dict:
        """构建灵魂附生状态的完整负载（发送给前端 soul-panel）

        Returns:
            {
                "game_mode": "soul_possession",
                "protagonist_id": "char_001",
                "soul": {
                    "player": {...},   # PlayerSoulProfile
                    "canon": {...},    # 原主人格概要
                    "blend_ratio": 0.5,
                    "inner_voice": "..." 或 None,
                },
                "npc_dissonance": {
                    "char_002": { "phase": "normal", "dissonance_score": 0.0, ... },
                }
            }
        """
        ws = self.world_state
        # 始终为 soul_possession 模式，直接返回灵魂状态
        soul_state = getattr(ws, 'soul_possession', None)
        dissonance_map = getattr(ws, 'cognitive_dissonance', {}) or {}
        protagonist_id = getattr(self, '_soul_protagonist_id', '')

        # 构建 NPC 认知冲突摘要
        npc_summary = {}
        for char_id, state in (dissonance_map or {}).items():
            if hasattr(state, 'to_dict'):
                state_dict = state.to_dict()
            elif isinstance(state, dict):
                state_dict = state
            else:
                continue
            npc_summary[char_id] = {
                "phase": state_dict.get("phase", "normal"),
                "dissonance_score": state_dict.get("dissonance_score", 0.0),
                "affinity": state_dict.get("affinity", 0.0),
                "credibility": state_dict.get("credibility", 100.0),
                "adaptation_progress": state_dict.get("adaptation_progress", 0.0),
            }

        # 构建灵魂面板数据
        soul_data = {}
        if soul_state:
            player_profile = getattr(soul_state, 'player_soul', None)
            canon_profile = getattr(soul_state, 'canon_soul', None)
            if player_profile and hasattr(player_profile, 'to_dict'):
                soul_data["player"] = player_profile.to_dict()
            if canon_profile:
                soul_data["canon"] = canon_profile if isinstance(canon_profile, dict) else canon_profile.to_dict()
            soul_data["blend_ratio"] = getattr(soul_state, 'blend_ratio', 0.5)
            soul_data["inner_voice"] = getattr(soul_state, 'last_inner_voice', None)

        # 检索最近记忆快照（供前端显示）
        mm = getattr(self.world_state, '_memory_manager', None)
        memory_snapshot = []
        if mm and mm.memory_stream:
            entries = []
            for agent_id, stream in mm.memory_stream.items():
                for entry in stream[-3:]:
                    entries.append(entry)
            entries.sort(key=lambda e: e.timestamp, reverse=True)
            for e in entries[:10]:
                memory_snapshot.append({
                    "agent_id": e.agent_id,
                    "content": e.content[:120],
                    "timestamp": e.timestamp,
                    "importance": e.importance,
                    "memory_type": e.memory_type,
                })

        return {
            "game_mode": "soul_possession",
            "protagonist_id": protagonist_id,
            "soul": soul_data,
            "npc_dissonance": npc_summary,
            "memory_snapshot": memory_snapshot,
        }

    def restore_state(self, save_data: dict) -> None:
        """从存档数据恢复状态

        Args:
            save_data: SaveManager.load() 返回的存档字典
        """
        ws_snapshot = save_data.get("world_state_snapshot", {})
        if ws_snapshot:
            self.world_state = WorldState.from_dict(ws_snapshot)

        # 恢复灵魂附生主角 ID
        self._soul_protagonist_id = str(
            save_data.get("soul_protagonist_id", "")
            or ws_snapshot.get("soul_protagonist_id", "")
        )

        self.beat_count = int(save_data.get("beat_count", 0))
        self.current_novel = str(save_data.get("novel_title", ""))
        self.event_log = list(save_data.get("event_log", []) or [])

        # ── 恢复运行 Canon ──
        novel_title = str(save_data.get("novel_title", ""))
        if novel_title:
            try:
                self.canon_manager.load_running_canon(novel_title)
                _log.info("从存档恢复了运行 Canon (目录结构): %s", novel_title)
            except Exception as exc:
                _log.warning("恢复运行 Canon 失败: %s", exc)

        _log.info("状态已恢复: session=%s, beat=%d", self.session_id, self.beat_count)

    # check_ending() 已移除（U6+：不再依赖固定偏离度阈值触发结局）

    # ────────────────────────────────────────────────
    # F6 设置面板：运行时更新配置
    # ────────────────────────────────────────────────

    async def update_config(
        self,
        providers: dict = None,
        api_key: str = "",
    ) -> None:
        """运行时更新 LLM 配置

        更新内存中的 _config_yaml dict 并写回 config.yaml。
        写盘前测试每个 provider 的连通性，任一端点不可达则拒绝应用。

        Args:
            providers: {"strong": {endpoint, model, temperature, max_tokens, ...},
                         "medium": {...}, "light": {...}}
                       也支持中文层名（"导演层"/"演员层"/"动作层"）
            api_key: API 密钥（三模型通用）
        """
        from server.manana.config import resolve_tier, display_tier, TIER_MAP

        # 1. 将 providers 的键名统一为内部标识
        normalized_providers = {}
        for k, v in (providers or {}).items():
            normalized_providers[resolve_tier(k)] = v

        # 2. 更新内存中的 YAML 配置（写入中文层名以匹配 config.yaml 格式）
        if not hasattr(self, '_config_yaml') or not self._config_yaml:
            self._config_yaml = {}
        cfg = self._config_yaml
        cfg_providers = cfg.setdefault("providers", {})

        # 确定写回时使用的键名（优先保留现有中文名，否则用旧名）
        existing_keys = list(cfg_providers.keys())
        key_mapping = {}
        for internal in ("strong", "medium", "light"):
            if existing_keys:
                # 找匹配的现有键（中文名优先）
                for ek in existing_keys:
                    if resolve_tier(ek) == internal:
                        key_mapping[internal] = ek
                        break
                if internal not in key_mapping:
                    key_mapping[internal] = internal  # fallback
            else:
                key_mapping[internal] = internal

        for internal_tier in ("strong", "medium", "light"):
            tier_cfg = normalized_providers.get(internal_tier, {})
            if not tier_cfg:
                continue
            yaml_key = key_mapping[internal_tier]
            prov = cfg_providers.setdefault(yaml_key, {})
            for key in ("endpoint", "model", "type"):
                if tier_cfg.get(key):
                    prov[key] = tier_cfg[key]
            if tier_cfg.get("temperature") is not None:
                try:
                    prov["temperature"] = float(tier_cfg["temperature"])
                except (ValueError, TypeError):
                    _log.warning("temperature 转换失败，值=%r", tier_cfg.get("temperature"))
                    pass
            if tier_cfg.get("max_tokens") is not None:
                try:
                    prov["max_tokens"] = int(tier_cfg["max_tokens"])
                except (ValueError, TypeError):
                    _log.warning("max_tokens 转换失败，值=%r", tier_cfg.get("max_tokens"))
                    pass
            if tier_cfg.get("api_key"):
                prov["api_key"] = tier_cfg["api_key"]
            if tier_cfg.get("timeout") is not None:
                try:
                    prov["timeout"] = int(tier_cfg["timeout"])
                except (ValueError, TypeError):
                    _log.warning("timeout 转换失败，值=%r", tier_cfg.get("timeout"))
                    pass

        # 2A. 连通性测试：只测试配置已更新的 provider
        from server.manana.providers import ProviderFactory
        failed_endpoints = []
        for internal_tier in ("strong", "medium", "light"):
            tier_cfg = normalized_providers.get(internal_tier, {})
            if not tier_cfg or not tier_cfg.get("endpoint"):
                continue  # 只测试配置已更新的 provider
            prov_type = tier_cfg.get("type", "ollama")
            try:
                test_prov = ProviderFactory.create(prov_type, tier_cfg)
                if test_prov:
                    ok, msg = await asyncio.wait_for(
                        test_prov.health_check(), timeout=8.0
                    )
                    if not ok:
                        failed_endpoints.append(f"{display_tier(internal_tier)}: {msg}")
                    await test_prov.cleanup()
            except asyncio.TimeoutError:
                failed_endpoints.append(f"{display_tier(internal_tier)}: 连接超时")
            except Exception as exc:
                failed_endpoints.append(f"{display_tier(internal_tier)}: {exc}")

        if failed_endpoints:
            raise RuntimeError(
                "以下端点不可达:\n" + "\n".join(f"  · {e}" for e in failed_endpoints)
                + "\n\n请检查 API 端点地址和网络连接后重试。"
            )

        # 2A2. 模型验证：Ollama 检查模型名是否已安装
        ollama_checked = {}  # endpoint → (models_list, error)
        failed_models = []
        all_available_models = []
        for internal_tier in ("strong", "medium", "light"):
            tier_cfg = normalized_providers.get(internal_tier, {})
            if not tier_cfg:
                continue
            prov_type = tier_cfg.get("type", "ollama")
            if prov_type != "ollama":
                continue
            model_name = tier_cfg.get("model", "")
            endpoint = tier_cfg.get("endpoint", "")
            if not model_name or not endpoint:
                continue

            # 同一 endpoint 只查询一次
            if endpoint not in ollama_checked:
                try:
                    test_prov = ProviderFactory.create(prov_type, tier_cfg)
                    models, err = await asyncio.wait_for(
                        test_prov.list_models(), timeout=8.0
                    )
                    ollama_checked[endpoint] = (models, err)
                    await test_prov.cleanup()
                except asyncio.TimeoutError:
                    ollama_checked[endpoint] = ([], "获取模型列表超时")
                except Exception as exc:
                    ollama_checked[endpoint] = ([], str(exc))

            models, err = ollama_checked[endpoint]
            if err:
                # 获取模型列表失败 → 降级跳过验证（不阻断）
                _log.warning("无法获取 %s 模型列表: %s", endpoint, err)
                continue

            if models:
                all_available_models = models
                # Ollama 模型名可能含 :latest 后缀，做模糊匹配
                if model_name not in models:
                    # 尝试去掉 :latest 后再匹配
                    model_clean = model_name.replace(":latest", "")
                    matched = any(m == model_clean or m == model_name for m in models)
                    if not matched:
                        failed_models.append(
                            f"{display_tier(internal_tier)}: 模型 '{model_name}' 未安装\n"
                            f"  已安装: {', '.join(models[:8])}"
                        )

        if failed_models:
            raise RuntimeError(
                "以下模型不存在于 Ollama:\n" + "\n".join(f"  · {e}" for e in failed_models)
                + "\n\n请在终端运行 ollama pull <模型名> 安装模型，或修改模型名后重试。"
            )

        # 缓存可用模型列表（供 config_updated 携带给前端）
        self._available_models = all_available_models

        # 2B. 写回 config.yaml
        config_path = Path(getattr(self, '_config_path', 'config.yaml'))
        # 写入前备份
        if config_path.is_file():
            try:
                shutil.copy(config_path, config_path.with_suffix('.yaml.bak'))
            except Exception:
                _log.warning("配置备份失败: %s", config_path)
                pass  # 备份失败不阻断主流程
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            _log.info("配置已写回 %s", config_path)
        except Exception as exc:
            _log.error("写 config.yaml 失败: %s", exc)
            # 不中断流程，内存配置仍然生效

        # _config_yaml 已在构造函数中设置，此处直接引用
        self._config_yaml = cfg  # 已有，同上

        # 3. 通知管线重置配置并热重连
        if self.pipeline:
            self.pipeline.reload_config(cfg)
        else:
            # Pipeline 此前为 None → 尝试用新配置重新创建
            try:
                from server.manana.pipeline import MananaPipeline
                self.pipeline = MananaPipeline(yaml_dict=cfg)
                await asyncio.wait_for(self.pipeline.initialize(), timeout=10.0)
                _log.info("Pipeline 从 F7 设置热重连创建成功: session=%s", self.session_id)
            except asyncio.TimeoutError:
                _log.warning("Pipeline 热重连创建超时（10s），保持回退模式")
                self.pipeline = None
            except Exception as exc:
                _log.error("Pipeline 热重连创建失败: %s", exc)
                self.pipeline = None

        _log.info("三级配置已更新并触发热重连")

    # ────────────────────────────────────────────────
    # 辅助方法
    # ────────────────────────────────────────────────

    def _get_present_character_ids(self) -> list[str]:
        """获取当前在场角色 ID 列表

        根据玩家当前位置 + Pipeline 提供的 featured_characters 确定"在场角色"。
        优先级:
          1. 优先使用 pipeline 输出的 featured_characters（Director 选定的出场角色）
          2. 若 pipeline 未指定，按玩家位置匹配同地点的角色
          3. 玩家位置未知时，仅返回 Canon 主要角色（上限 8 个）
             避免首拍将所有角色灌入 Director 上下文

        Returns:
            list[str]: 当前在场角色 ID 列表
        """
        # 优先使用 pipeline 输出的 featured_characters（由 Director 指定）
        if self._last_pipeline_result:
            featured = (self._last_pipeline_result.get("state_patch", {}) or {}).get("featured_characters", [])
            if featured:
                # 限制 Director 选定角色上限，防止上下文膨胀
                return featured[:12]

        player_loc = self.world_state.player_location
        present: list[str] = []

        if not player_loc:
            # 玩家位置未知 → 仅返回 Canon 主要角色（避免首拍将所有角色灌入上下文）
            canon = self.world_state.canon or {}
            canon_chars: list = canon.get("characters", []) or []
            # 筛选主要角色：role 包含"主"（主角/女主角）或"重要"（重要配角）
            for c in canon_chars:
                c = c if isinstance(c, dict) else {}
                cid = str(c.get("id", ""))
                if not cid:
                    continue
                if c.get("status") == "dead":
                    continue
                role = str(c.get("role", ""))
                if "主" in role or "重要" in role:
                    present.append(cid)
                if len(present) >= 8:
                    break
            # 保底：如果没有找到任何主要角色，取前 8 个存活角色
            if not present:
                for c in canon_chars:
                    c = c if isinstance(c, dict) else {}
                    cid = str(c.get("id", ""))
                    if not cid:
                        continue
                    if c.get("status") == "dead":
                        continue
                    present.append(cid)
                    if len(present) >= 8:
                        break
        else:
            # 玩家位置已知 → 匹配同位置角色（上限 8 个，防止上下文膨胀）
            for cid, cs in self.world_state.characters_state.items():
                if cs.get("status") == "dead":
                    continue
                if cs.get("location", "") == player_loc:
                    present.append(cid)
                    if len(present) >= 8:
                        break

        return present

    def _get_state_summary(self) -> dict:
        """获取状态变更摘要"""
        return {
            "location_changed": bool(self.world_state.player_location),
            "reputation_changes": {
                cid: round(val, 2)
                for cid, val in self.world_state.player_reputation.items()
            },
            "beat_count": self.beat_count,
        }

    # ────────────────────────────────────────────────
    # 灵魂附生辅助方法
    # ────────────────────────────────────────────────

    def _build_social_graph(self) -> dict[str, list[dict]]:
        """构建社交图结构，供 SocialPropagator.propagate() 使用。

        数据来源分两层：
        1. Canon relationships（直接映射 intensity → bond_strength）
        2. 位置邻近 NPC（top-3 补充，默认 bond_strength=0.3）

        Returns:
            {char_id: [{"target": char_id, "bond_strength": float}, ...]}
        """
        protagonist_id: str = getattr(self, "_soul_protagonist_id", "")
        social_graph: dict[str, list[dict]] = {}

        # ── 第一层：Canon relationships ──
        canon_chars: list = self.world_state.canon.get("characters", []) or []
        for c in canon_chars:
            c = c if isinstance(c, dict) else {}
            cid: str = str(c.get("id", ""))
            if not cid:
                continue
            if cid not in social_graph:
                social_graph[cid] = []
            for rel in c.get("relationships", []) or []:
                rel = rel if isinstance(rel, dict) else {}
                target: str = str(rel.get("target", ""))
                if not target:
                    continue
                bond_strength: float = float(rel.get("intensity", 0.0))
                social_graph[cid].append({
                    "target": target,
                    "bond_strength": bond_strength,
                })

        # ── 第二层：位置邻近 NPC（top-3 补充，按 canon 角色列表顺序） ──
        cs = self.world_state.characters_state or {}
        char_locations: dict[str, str] = {}
        for cid, state in cs.items():
            state = state if isinstance(state, dict) else {}
            loc: str = str(state.get("location", ""))
            if loc:
                char_locations[cid] = loc

        canon_char_ids: list[str] = []
        for c in canon_chars:
            c = c if isinstance(c, dict) else {}
            cid = str(c.get("id", ""))
            if cid:
                canon_char_ids.append(cid)

        for cid in canon_char_ids:
            if cid == protagonist_id:
                continue
            loc = char_locations.get(cid, "")
            if not loc:
                continue
            if cid not in social_graph:
                social_graph[cid] = []
            existing_targets = {edge["target"] for edge in social_graph[cid]}
            added = 0
            for other_cid in canon_char_ids:
                if other_cid == cid or other_cid == protagonist_id:
                    continue
                if other_cid in existing_targets:
                    continue
                if char_locations.get(other_cid, "") != loc:
                    continue
                social_graph[cid].append({
                    "target": other_cid,
                    "bond_strength": 0.3,
                })
                added += 1
                if added >= 3:
                    break

        return social_graph

    def _needs_soul_choice(self) -> bool:
        """当前 beat 是否需要玩家进行[本我/贴合]选择
        
        前 9 拍为 auto 人格积累期，第 10 拍首次弹出双选，
        之后每 3 拍弹出双选。
        """
        if self.beat_count < 10:
            return False
        if self.beat_count == 10:
            return True  # 积累期结束，首次弹出选择
        return (self.beat_count - 10) % 3 == 0

    def _get_dissonance_summary(self) -> dict:
        """返回认知冲突摘要（供前端使用）"""
        if not self.world_state.cognitive_dissonance:
            return {}
        return {
            cid: {
                "dissonance_score": round(s.dissonance_score, 2),
                "phase": s.phase,
                "affinity": s.affinity,
                "credibility": s.credibility,
                "theory_of_change": s.theory_of_change,
            }
            for cid, s in self.world_state.cognitive_dissonance.items()
        }
