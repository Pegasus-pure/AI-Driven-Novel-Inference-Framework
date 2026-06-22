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
import shutil
import time
import yaml
from pathlib import Path
from typing import Any, Callable, Optional

from .world_state import WorldState
from .save_manager import SaveManager
from .canon_manager import CanonManager

# 导入提取器和存储后端
from .extractors import get_extractor
from .storage import get_storage

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
        extractor_name: str = "llm",
        fallback_extractor_name: str = "regex",
        storage_name: str = "file",
        **kwargs: Any,
    ) -> None:
        """初始化游戏会话

        Args:
            session_id: 会话 ID
            extractor_name: LLM 提取器名称（默认 "llm"）
            fallback_extractor_name: 回退提取器名称（默认 "regex"）
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

        # 提取器配置
        self._extractor_name: str = extractor_name
        self._fallback_extractor_name: str = fallback_extractor_name
        self._extractor = None
        self._fallback_extractor = None

        self._config_path: str = ""
        self._auto_save_interval: int = 10
        # 结局阈值已移除（U6+ 使用叙事张力驱动的动态演化）
        self._skip_typing: bool = False

        # ── 新增：小说选择流程状态 ──
        self._generation_in_progress: bool = False
        self._generation_task: Optional[asyncio.Task] = None
        self._current_agent: Optional[str] = None  # 当前正在执行的 agent
        self._last_scan_result: dict = {}
        self._generation_start_time: float = 0.0  # time.time() 生成开始时间戳
        self._last_pipeline_result: dict = {}  # 上一拍的 pipeline 完整结果（供在场角色判定等使用）

    # ── 默认 Choices ──

    @staticmethod
    def _get_default_choices() -> list[dict]:
        """返回默认 choices，统一从 manana/defaults.py 获取。"""
        from server.manana.defaults import get_default_choices
        return get_default_choices(3)

    # ────────────────────────────────────────────────
    # 提取器懒加载
    # ────────────────────────────────────────────────

    def _get_extractor(self):
        """获取 LLM 提取器（懒加载）"""
        if self._extractor is None:
            self._extractor = get_extractor(self._extractor_name)
        return self._extractor

    def _get_fallback_extractor(self):
        """获取回退提取器（懒加载）"""
        if self._fallback_extractor is None:
            self._fallback_extractor = get_extractor(self._fallback_extractor_name)
        return self._fallback_extractor

    def set_extractor(self, name: str, **kwargs: Any) -> None:
        """设置 LLM 提取器

        Args:
            name: 提取器名称
            **kwargs: 传递给提取器构造函数的参数
        """
        self._extractor_name = name
        self._extractor = get_extractor(name, **kwargs)

    def set_fallback_extractor(self, name: str, **kwargs: Any) -> None:
        """设置回退提取器

        Args:
            name: 提取器名称
            **kwargs: 传递给提取器构造函数的参数
        """
        self._fallback_extractor_name = name
        self._fallback_extractor = get_extractor(name, **kwargs)

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
        self._config_cache = cfg
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
            from server.novel_loader import NovelLoader
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

        # 2. 创建运行 Canon 副本
        title = str(initial_canon.get("title", source_path.stem.replace("canon_", "", 1)))
        ok = self.canon_manager.create_running_canon(str(source_file))
        if not ok:
            _log.error("创建运行 Canon 失败: %s", source_file)
            return False

        # 3. 加载运行 Canon
        running_canon = self.canon_manager.load_running_canon(title)
        if running_canon is None:
            _log.error("加载运行 Canon 失败: %s", title)
            return False

        # 4. 应用到 world_state
        running_canon["_source_file"] = str(source_file)
        self._apply_canon_to_world_state(running_canon)
        self.current_novel = title
        _log.info(
            "Canon 已加载 (目录结构模式): %s → novel/%s/ (source=%s)",
            source_file,
            title,
            "running",
        )
        return True

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

        Returns:
            canon_ready payload 字典
        """
        canon = self.world_state.canon or {}
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

    async def start_llm_generation_with_progress(
        self,
        txt_path: str = "",
        content: str = "",
        progress_cb: Any = None,
    ) -> None:
        """异步 LLM Canon 生成，通过回调推送进度

        支持两种输入：
          - txt_path: 从 existing .txt 文件加载
          - content: 从上传的内容加载

        LLM 失败时自动回退到正则抽取，通过 progress_cb 通知前端。

        Args:
            txt_path: .txt 文件路径
            content: 小说文本内容（上传时）
            progress_cb: 异步回调函数 async def cb(status_dict)
        """
        if self._generation_in_progress:
            _log.warning("LLM 生成已在进行中，忽略重复请求")
            return

        self._generation_in_progress = True
        self._generation_start_time = time.time()
        start_time = asyncio.get_event_loop().time()

        async def _send_progress(status: str, message: str) -> None:
            """发送进度回调"""
            if progress_cb:
                elapsed = asyncio.get_event_loop().time() - start_time
                try:
                    await progress_cb({
                        "status": status,
                        "message": message,
                        "elapsed_seconds": round(elapsed, 1),
                    })
                except Exception as exc:
                    _log.warning("进度回调失败: %s", exc)

        async def _generation_worker() -> None:
            """实际生成任务"""
            from server.novel_loader import NovelLoader
            loader = NovelLoader()

            try:
                # 每 3 秒推送一次进度
                progress_messages = [
                    "正在读取小说内容...",
                    "正在分析小说角色...",
                    "正在提取世界观信息...",
                    "正在整理地点与事件...",
                    "正在生成结构化数据...",
                    "正在验证数据完整性...",
                ]
                msg_index = 0

                async def _periodic_progress() -> None:
                    nonlocal msg_index
                    while self._generation_in_progress:
                        await asyncio.sleep(3.0)
                        if not self._generation_in_progress:
                            break
                        msg = progress_messages[min(msg_index, len(progress_messages) - 1)]
                        msg_index += 1
                        await _send_progress("generating", msg)

                # 启动周期性进度推送
                progress_task = asyncio.create_task(_periodic_progress())

                # ── 加载文本 ──
                text = ""
                filename = "unknown.txt"
                if txt_path:
                    await _send_progress("generating", "正在读取小说文件...")
                    text = loader.load_file(txt_path) or ""
                    filename = Path(txt_path).name
                elif content:
                    await _send_progress("generating", "正在处理上传的小说内容...")
                    text = content
                    filename = "uploaded.txt"
                else:
                    await _send_progress("error", "未提供小说文本")
                    self._generation_in_progress = False
                    progress_task.cancel()
                    return

                if not text.strip():
                    await _send_progress("error", "小说文本为空")
                    self._generation_in_progress = False
                    progress_task.cancel()
                    return

                # ── LLM 抽取 ──
                canon_data: Optional[dict] = None
                used_llm = False

                if self.pipeline:
                    try:
                        provider = self.pipeline._get_provider_for_tier("medium")
                    except Exception:
                        provider = None

                    if provider:
                        await _send_progress("generating", "正在调用 AI 分析小说...")
                        try:
                            # 使用提取器模式
                            extractor = self._get_extractor()
                            canon_data = await extractor.extract(
                                text, filename, provider
                            )
                            used_llm = True
                        except Exception as exc:
                            _log.warning("LLM 抽取异常: %s", exc)
                            canon_data = None
                    else:
                        await _send_progress("generating", "AI 模型未配置，使用规则抽取...")
                else:
                    await _send_progress("generating", "管线未初始化，使用规则抽取...")

                # ── 回退正则抽取 ──
                if canon_data is None:
                    await _send_progress("generating", "正在使用规则抽取角色和地点...")
                    fallback = self._get_fallback_extractor()
                    canon_data = await fallback.extract(text, filename)

                # 取消进度任务
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass

                if canon_data is None:
                    await _send_progress("error", "Canon 生成完全失败，请检查小说文本格式")
                    self._generation_in_progress = False
                    return

                # ── 持久化 ──
                novel_title = canon_data.get("title", filename.rsplit(".", 1)[0])
                loader.save_canon_json(canon_data, novel_title)

                # ── 应用到 world_state ──
                self._apply_canon_to_world_state(canon_data)
                self.current_novel = novel_title

                # ── 最终状态 ──
                if used_llm:
                    await _send_progress("completed", "AI 世界观数据生成完成")
                else:
                    await _send_progress(
                        "fallback",
                        "LLM 不可达，已使用规则抽取。建议手动补充角色和地点信息。"
                    )

                _log.info(
                    "Canon 生成完成: %s (%s)",
                    novel_title,
                    "LLM" if used_llm else "回退正则"
                )

            except Exception as exc:
                _log.error("Canon 生成异常: %s", exc)
                await _send_progress("error", f"生成失败: {exc}")
            finally:
                self._generation_in_progress = False

        # 启动异步生成任务（不阻塞当前消息循环）
        self._generation_task = asyncio.create_task(_generation_worker())

    def import_canon_json(self, json_content: str, filename: str = "") -> tuple:
        """验证并导入 Canon JSON 内容

        Args:
            json_content: JSON 字符串
            filename: 原始文件名（用于日志和保存）

        Returns:
            (success: bool, message: str)
        """
        from server.novel_loader import NovelLoader
        loader = NovelLoader()

        canon_data = loader.import_canon_from_json(json_content)
        if canon_data is None:
            return (False, "JSON 解析失败或缺少必要字段（需要 title 或 characters）")

        # 保存 JSON 到 novel/ 目录
        title = canon_data.get("title", filename.rsplit(".", 1)[0] if filename else "imported")
        safe_name = "".join(c for c in title if c.isalnum() or c in "._- ()（）")
        if not safe_name:
            safe_name = "imported"

        from server.paths import NOVEL_DIR
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
                    "reputation": 0.0,
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
        return (True, "")

    async def cleanup(self) -> None:
        """清理资源"""
        if self._generation_task and not self._generation_task.done():
            self._generation_task.cancel()
            try:
                await self._generation_task
            except asyncio.CancelledError:
                pass
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

    async def run_beat(self, player_action: str, progress_cb=None) -> dict:
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
            result = await self.pipeline.run_beat(player_action, self.world_state, progress_cb=progress_cb)
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

        # 叙事文本 ID 审计
        if "narrative_text" in result and result["narrative_text"]:
            result["narrative_text"] = self._replace_ids_with_names(result["narrative_text"])

        # 确保 choices 字段存在
        choices = result.get("choices", [])
        if not choices:
            choices = self._get_default_choices()
            result["choices"] = choices

        # 结局检测已移除（U6+：使用叙事张力驱动的动态演化，不再依赖固定偏离度阈值）
        return result

    async def stream_beat(
        self,
        player_action: str,
        send_chunk: Callable[[dict], Any],
    ) -> None:
        """流式执行节拍 — 分块推送叙事文本

        先批量调用 Pipeline（通过 progress_cb 在每层推送 agent_status），
        然后将 narrative_text 分块推送。

        Args:
            player_action: 玩家输入
            send_chunk: 异步回调，每块调用 send_chunk(chunk_dict)
        """
        # ── 构建 progress_cb，由 Pipeline 内部在各层推送 agent_status ──
        async def progress_cb(agent: str, label: str) -> None:
            await send_chunk({
                "type": "agent_status",
                "payload": {"agent": agent, "label": label},
            })

        result = await self.run_beat(player_action, progress_cb=progress_cb)
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
        # ── Choices 处理 ──
        choices: list = result.get("choices", []) or []
        if not choices:
            choices = self._get_default_choices()
        # 确保 choices 中的 choice 包含必要字段
        valid_choices = []
        for c in choices:
            if isinstance(c, dict) and all(k in c for k in ("id", "text", "hint", "next_scene_hint")):
                valid_choices.append(c)
        if len(valid_choices) < 2:
            valid_choices = self._get_default_choices()
        choices = valid_choices[:4]

        # ── 清除 agent 状态（Pipeline 已完成） ──
        await send_chunk({
            "type": "agent_status",
            "payload": {"agent": None, "label": ""},
        })

        # 按句号/换行分块
        chunks = self._split_narrative(narrative_text)
        total_chunks = len(chunks)

        for i, chunk in enumerate(chunks):
            if self._skip_typing:
                # 跳过打字机：一次性发送剩余文本
                remaining = "".join(chunks[i:])
                await send_chunk({
                    "type": "narrative_chunk",
                    "payload": {
                        "text": remaining,
                        "chunk_index": total_chunks,
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

        # 叙事完成（含 narrative_mode + choices）
        await send_chunk({
            "type": "narrative_complete",
            "payload": {
                "beat_id": f"beat_{self.beat_count:03d}",
                "narrative_text": narrative_text,
                "action_hints": action_hints,
                "narrative_mode": narrative_mode,
                "ending_hook": ending_hook,
                "choices": choices,
                "deviation": deviation,
                "characters_present": self._get_present_character_ids(),
                "state_patch_summary": self._get_state_summary(),
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

        # 结局处理已移除（U6+：不再依赖固定偏离度阈值触发结局，改为动态演化）

    def cancel_typing(self) -> None:
        """跳过当前打字机动画"""
        self._skip_typing = True

    # ────────────────────────────────────────────────
    # 分块策略
    # ────────────────────────────────────────────────

    @staticmethod
    def _split_narrative(text: str, chunk_size: int = 30) -> list[str]:
        """将叙事文本分割为适合流式传输的块

        按句号和逗号自然断句，每块约 chunk_size 字符。

        Args:
            text: 完整叙事文本
            chunk_size: 每块目标字符数

        Returns:
            文本块列表
        """
        chunks: list[str] = []

        # 按分隔符拆分
        import re
        sentences = re.split(r'(?<=[。！？…」】\n])', text)

        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) > chunk_size and current:
                chunks.append(current)
                current = sentence
            else:
                current += sentence

        if current:
            chunks.append(current)

        # 如果没有生成块（空文本），至少返回一个空块
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
                        "endpoint": ep,
                        "model": tc.get("model", ""),
                        "temperature": tc.get("temperature", 0.7),
                        "max_tokens": tc.get("max_tokens", 2048),
                    }
                except Exception:
                    result["providers"][tier] = {}
            result["api_key"] = ""
            if "strong" in result["providers"]:
                try:
                    tc = mc.get_tier_config("strong")
                    result["api_key"] = tc.get("api_key", "")
                except Exception:
                    pass
            result["available_models"] = getattr(self, '_available_models', [])
            return result

        # fallback: 从原始 yaml dict 读取（兼容中文/旧名两种键）
        cfg = self._config_cache if hasattr(self, '_config_cache') else {}
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
                "endpoint": t.get("endpoint", ""),
                "model": t.get("model", ""),
                "temperature": t.get("temperature", 0.7),
                "max_tokens": t.get("max_tokens", 2048),
            }

        result["api_key"] = ""
        first = tier_map.get("strong", {}) or {}
        if first:
            result["api_key"] = first.get("api_key", "")
        return result

    def get_state_snapshot(self) -> dict:
        """获取当前状态快照（发送给前端）

        注意：canon 为空时返回空 dict，前端需处理 None 情况。
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
            "session_id": self.session_id,
            "novel_title": self.current_novel or "",
            "canon_ready": bool(self.current_novel),
            "is_generating": self._generation_in_progress,
            "current_agent": self._current_agent or "",
            # F8 叙事线索（供前端 ThreadsRenderer 渲染）
            "narrative_threads": self.world_state.narrative_threads,
        }

    def restore_state(self, save_data: dict) -> None:
        """从存档数据恢复状态

        Args:
            save_data: SaveManager.load() 返回的存档字典
        """
        ws_snapshot = save_data.get("world_state_snapshot", {})
        if ws_snapshot:
            self.world_state = WorldState.from_dict(ws_snapshot)

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
                    pass
            if tier_cfg.get("max_tokens") is not None:
                try:
                    prov["max_tokens"] = int(tier_cfg["max_tokens"])
                except (ValueError, TypeError):
                    pass
            if tier_cfg.get("api_key"):
                prov["api_key"] = tier_cfg["api_key"]

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
                pass  # 备份失败不阻断主流程
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            _log.info("配置已写回 %s", config_path)
        except Exception as exc:
            _log.error("写 config.yaml 失败: %s", exc)
            # 不中断流程，内存配置仍然生效

        # 同步 _config_cache 供 get_config_info 回退使用
        self._config_cache = cfg

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
          3. 玩家位置未知时，返回所有存活角色（首次叙事节拍时使用）

        Returns:
            list[str]: 当前在场角色 ID 列表
        """
        # 优先使用 pipeline 输出的 featured_characters（由 Director 指定）
        if self._last_pipeline_result:
            featured = (self._last_pipeline_result.get("state_patch", {}) or {}).get("featured_characters", [])
            if featured:
                return featured

        player_loc = self.world_state.player_location
        present: list[str] = []

        for cid, cs in self.world_state.characters_state.items():
            # 跳过死亡角色
            if cs.get("status") == "dead":
                continue

            if not player_loc:
                # 玩家位置未知 → 返回所有存活角色（首次叙事节拍回退）
                present.append(cid)
            elif cs.get("location", "") == player_loc:
                # 玩家位置已知 → 匹配同位置角色
                present.append(cid)

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
