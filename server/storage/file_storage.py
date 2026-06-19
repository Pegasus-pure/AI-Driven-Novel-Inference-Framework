# -*- coding: utf-8 -*-
"""文件存储后端 — Canon 数据以目录结构存储

将原 canon_manager.py 中的文件操作逻辑封装为独立存储后端。
保持原有目录结构不变，确保向后兼容。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .base import CanonStorage

_log = logging.getLogger("AINovelFramework.Storage.File")


class FileStorage(CanonStorage):
    """文件系统存储后端

    目录结构:
        novel/{小说名}/
            meta.json                ← 小说元信息
            rules/
                world_rules.json     ← 世界观规则
            characters/
                char_001.json        ← 每个角色独立文件
            locations/
                loc_001.json         ← 每个地点独立文件
    """

    def __init__(self, novel_dir_root: str = "novel") -> None:
        """初始化文件存储后端

        Args:
            novel_dir_root: 小说根目录路径
        """
        self.novel_dir_root: str = novel_dir_root

    # ────────────────────────────────────────────────
    # CanonStorage 接口实现
    # ────────────────────────────────────────────────

    def create_running_canon(self, source_file: str) -> bool:
        """从初始 Canon JSON 创建运行目录结构

        如果运行目录已存在（meta.json 存在），则跳过（保留已有编辑）。
        向后兼容：如果存在旧的 canon_{title}_running.json 单文件，从它迁移。

        Args:
            source_file: 初始 Canon JSON 文件路径 (如 novel/canon_xxx.json)

        Returns:
            是否成功创建/已存在
        """
        title = self._extract_title_from_path(source_file)
        novel_dir = self._get_novel_dir(title)
        meta_path = self._get_meta_path(title)

        # 如果 meta.json 已存在，说明运行 Canon 已存在，跳过
        if meta_path.is_file():
            _log.info("运行 Canon 目录已存在: %s", novel_dir)
            return True

        # 向后兼容：检查旧的单文件运行 Canon
        old_running_path = Path(self.novel_dir_root) / f"canon_{title}_running.json"
        if old_running_path.is_file():
            _log.info("检测到旧格式运行 Canon，正在迁移: %s", old_running_path.name)
            try:
                with open(old_running_path, "r", encoding="utf-8") as f:
                    canon_data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                _log.error("读取旧运行 Canon 失败: %s, error=%s", old_running_path, exc)
                return False
        else:
            # 读取初始 Canon
            try:
                with open(source_file, "r", encoding="utf-8") as f:
                    canon_data = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                _log.error("读取初始 Canon 失败: %s, error=%s", source_file, exc)
                return False

        if not isinstance(canon_data, dict):
            _log.error("初始 Canon 格式无效 (非字典): %s", source_file)
            return False

        # 确保必要字段存在
        canon_data.setdefault("title", title)
        canon_data.setdefault("characters", [])
        canon_data.setdefault("locations", [])
        canon_data.setdefault("world_rules", {})
        canon_data.setdefault("timeline", [])
        canon_data.setdefault("meta", {})
        canon_data["_source"] = "running"
        canon_data["_initial_source"] = source_file

        # 写入目录结构
        try:
            self._write_directory_structure(title, canon_data)
            _log.info("运行 Canon 目录已创建: %s (来自 %s)", novel_dir, source_file)
        except OSError as exc:
            _log.error("写入运行 Canon 目录失败: %s, error=%s", novel_dir, exc)
            return False

        # 如果从旧格式迁移成功，删除旧文件
        if old_running_path.is_file():
            try:
                old_running_path.unlink()
                _log.info("已删除旧格式运行 Canon: %s", old_running_path.name)
            except OSError:
                pass

        return True

    def load_running_canon(self, title: str) -> Optional[dict]:
        """从目录结构加载运行 Canon

        Args:
            title: 小说标题

        Returns:
            运行 Canon 字典，或 None（不存在时）
        """
        novel_dir = self._get_novel_dir(title)
        meta_path = self._get_meta_path(title)

        if not meta_path.is_file():
            _log.info("运行 Canon 目录不存在: %s", novel_dir)
            return None

        try:
            canon_data = self._read_directory_structure(title)
        except Exception as exc:
            _log.error("读取运行 Canon 目录失败: %s, error=%s", novel_dir, exc)
            return None

        if not isinstance(canon_data, dict):
            _log.error("运行 Canon 格式无效 (非字典): %s", novel_dir)
            return None

        # 确保必要字段
        canon_data.setdefault("title", title)
        canon_data.setdefault("characters", [])
        canon_data.setdefault("locations", [])
        canon_data.setdefault("world_rules", {})
        canon_data.setdefault("timeline", [])
        canon_data.setdefault("meta", {})
        canon_data["_source"] = "running"

        _log.info(
            "运行 Canon 已加载: %s (%d 角色, %d 地点)",
            title,
            len(canon_data.get("characters", []) or []),
            len(canon_data.get("locations", []) or []),
        )
        return canon_data

    def save_running_canon(self, title: str, canon_data: dict) -> None:
        """将完整 Canon 数据写入目录结构

        Args:
            title: 小说标题
            canon_data: 完整 Canon 字典
        """
        self._write_directory_structure(title, canon_data)
        _log.debug("运行 Canon 目录结构已保存: %s", title)

    def save_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
        data: dict,
    ) -> bool:
        """保存单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations' | 'world_rules' | 'meta'
            entry_id: 条目 ID
            data: 条目数据

        Returns:
            是否保存成功
        """
        try:
            if section == "characters":
                file_path = self._get_character_path(title, entry_id)
            elif section == "locations":
                file_path = self._get_location_path(title, entry_id)
            elif section == "world_rules":
                file_path = self._get_rules_path(title)
            elif section == "meta":
                file_path = self._get_meta_path(title)
            else:
                _log.warning("未知分区: %s", section)
                return False

            self._write_json_file(file_path, data)
            return True
        except Exception as exc:
            _log.error("保存条目失败: %s/%s, error=%s", section, entry_id, exc)
            return False

    def load_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
    ) -> Optional[dict]:
        """加载单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'
            entry_id: 条目 ID

        Returns:
            条目数据字典，或 None（不存在时）
        """
        try:
            if section == "characters":
                file_path = self._get_character_path(title, entry_id)
            elif section == "locations":
                file_path = self._get_location_path(title, entry_id)
            else:
                _log.warning("load_entry 不支持分区: %s", section)
                return None

            if not file_path.is_file():
                return None

            return self._read_json_file(file_path)
        except Exception as exc:
            _log.error("加载条目失败: %s/%s, error=%s", section, entry_id, exc)
            return None

    def delete_entry(
        self,
        title: str,
        section: str,
        entry_id: str,
    ) -> bool:
        """删除单个条目

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'
            entry_id: 条目 ID

        Returns:
            是否删除成功
        """
        try:
            if section == "characters":
                file_path = self._get_character_path(title, entry_id)
            elif section == "locations":
                file_path = self._get_location_path(title, entry_id)
            else:
                _log.warning("delete_entry 不支持分区: %s", section)
                return False

            if file_path.is_file():
                file_path.unlink()
                _log.info("条目已删除: %s/%s", section, entry_id)
                return True
            else:
                _log.warning("条目文件不存在: %s/%s", section, entry_id)
                return False
        except Exception as exc:
            _log.error("删除条目失败: %s/%s, error=%s", section, entry_id, exc)
            return False

    def mark_character_dead(
        self,
        title: str,
        char_id: str,
        death_info: dict,
    ) -> bool:
        """标记角色死亡

        Args:
            title: 小说标题
            char_id: 角色 ID
            death_info: {"death_location": str, "death_time": str, "death_cause": str}

        Returns:
            是否标记成功
        """
        try:
            char_path = self._get_character_path(title, char_id)
            if not char_path.is_file():
                _log.warning("角色文件不存在: %s", char_id)
                return False

            char_data = self._read_json_file(char_path)

            # 标记死亡
            char_data["status"] = "dead"
            char_data["death_location"] = str(death_info.get("death_location", ""))
            char_data["death_time"] = str(death_info.get("death_time", ""))
            char_data["death_cause"] = str(death_info.get("death_cause", ""))

            # 写回文件
            self._write_json_file(char_path, char_data)

            _log.info(
                "角色已标记死亡: %s (地点=%s, 时间=%s, 原因=%s)",
                char_id,
                death_info.get("death_location", ""),
                death_info.get("death_time", ""),
                death_info.get("death_cause", ""),
            )
            return True
        except Exception as exc:
            _log.error("标记角色死亡失败: %s, error=%s", char_id, exc)
            return False

    def get_entry_count(self, title: str, section: str) -> int:
        """获取分区中条目数量

        Args:
            title: 小说标题
            section: 分区 — 'characters' | 'locations'

        Returns:
            条目数量
        """
        try:
            if section == "characters":
                target_dir = self._get_characters_dir(title)
                prefix = "char_"
            elif section == "locations":
                target_dir = self._get_locations_dir(title)
                prefix = "loc_"
            else:
                return 0

            max_idx = 0
            if target_dir.is_dir():
                for f in target_dir.glob("*.json"):
                    stem = f.stem
                    if stem.startswith(prefix):
                        try:
                            num_part = stem[len(prefix):]
                            idx = int(num_part)
                            if idx > max_idx:
                                max_idx = idx
                        except ValueError:
                            continue

            return max_idx
        except Exception as exc:
            _log.error("获取条目数量失败: %s/%s, error=%s", title, section, exc)
            return 0

    # ────────────────────────────────────────────────
    # 路径工具（原样从 canon_manager.py 搬来）
    # ────────────────────────────────────────────────

    @staticmethod
    def _extract_title_from_path(source_path: str) -> str:
        """从 canon 文件路径提取小说标题

        novel/canon_魔王去上學.json → 魔王去上學
        """
        stem = Path(source_path).stem  # canon_魔王去上學
        if stem.startswith("canon_"):
            return stem[len("canon_"):]
        return stem

    @staticmethod
    def _safe_title(title: str) -> str:
        """生成安全的文件/目录名"""
        safe = "".join(c for c in title if c.isalnum() or c in "._- ()（）")
        if not safe:
            safe = "unknown"
        return safe

    def _get_novel_dir(self, title: str) -> Path:
        """获取小说目录路径"""
        return Path(self.novel_dir_root) / self._safe_title(title)

    def _get_meta_path(self, title: str) -> Path:
        """获取 meta.json 路径"""
        return self._get_novel_dir(title) / "meta.json"

    def _get_rules_path(self, title: str) -> Path:
        """获取 rules/world_rules.json 路径"""
        return self._get_novel_dir(title) / "rules" / "world_rules.json"

    def _get_characters_dir(self, title: str) -> Path:
        """获取 characters/ 目录路径"""
        return self._get_novel_dir(title) / "characters"

    def _get_locations_dir(self, title: str) -> Path:
        """获取 locations/ 目录路径"""
        return self._get_novel_dir(title) / "locations"

    def _get_character_path(self, title: str, char_id: str) -> Path:
        """获取角色文件路径"""
        return self._get_characters_dir(title) / f"{char_id}.json"

    def _get_location_path(self, title: str, loc_id: str) -> Path:
        """获取地点文件路径"""
        return self._get_locations_dir(title) / f"{loc_id}.json"

    # ────────────────────────────────────────────────
    # 目录结构读写（原样从 canon_manager.py 搬来）
    # ────────────────────────────────────────────────

    def _write_directory_structure(self, title: str, canon_data: dict) -> None:
        """将 Canon 数据写入目录结构

        创建所有必要的目录和文件。

        Args:
            title: 小说标题
            canon_data: 完整 Canon 字典
        """
        novel_dir = self._get_novel_dir(title)

        # 创建目录
        novel_dir.mkdir(parents=True, exist_ok=True)
        (novel_dir / "rules").mkdir(exist_ok=True)
        (novel_dir / "characters").mkdir(exist_ok=True)
        (novel_dir / "locations").mkdir(exist_ok=True)

        # 写入 meta.json
        meta = canon_data.get("meta", {}) or {}
        if isinstance(meta, dict):
            meta.setdefault("title", title)
        self._write_json_file(self._get_meta_path(title), meta)

        # 写入 rules/world_rules.json
        world_rules = canon_data.get("world_rules", {}) or {}
        self._write_json_file(self._get_rules_path(title), world_rules)

        # 写入 characters/*.json — 先清理旧文件避免遗留
        chars_dir = self._get_characters_dir(title)
        for old_file in chars_dir.glob("*.json"):
            try:
                old_file.unlink()
            except OSError:
                pass
        for c in (canon_data.get("characters", []) or []):
            c = c if isinstance(c, dict) else {}
            cid = c.get("id", "")
            if cid:
                self._write_json_file(chars_dir / f"{cid}.json", c)

        # 写入 locations/*.json — 先清理旧文件避免遗留
        locs_dir = self._get_locations_dir(title)
        for old_file in locs_dir.glob("*.json"):
            try:
                old_file.unlink()
            except OSError:
                pass
        for loc in (canon_data.get("locations", []) or []):
            loc = loc if isinstance(loc, dict) else {}
            lid = loc.get("id", "")
            if lid:
                self._write_json_file(locs_dir / f"{lid}.json", loc)

    def _read_directory_structure(self, title: str) -> dict:
        """从目录结构读取 Canon 数据并合并为完整 dict

        返回格式与之前的单文件兼容，前端不变。

        Args:
            title: 小说标题

        Returns:
            完整 Canon 字典
        """
        canon_data: dict[str, Any] = {"title": title}

        # 读取 meta.json
        meta_path = self._get_meta_path(title)
        if meta_path.is_file():
            canon_data["meta"] = self._read_json_file(meta_path)
        else:
            canon_data["meta"] = {}

        # 读取 rules/world_rules.json
        rules_path = self._get_rules_path(title)
        if rules_path.is_file():
            canon_data["world_rules"] = self._read_json_file(rules_path)
        else:
            canon_data["world_rules"] = {}

        # 读取 characters/*.json → 合并为 characters 数组
        chars_dir = self._get_characters_dir(title)
        characters: list[dict] = []
        if chars_dir.is_dir():
            for cf in sorted(chars_dir.glob("*.json")):
                try:
                    char_data = self._read_json_file(cf)
                    if isinstance(char_data, dict):
                        characters.append(char_data)
                except Exception as exc:
                    _log.warning("读取角色文件失败: %s, error=%s", cf.name, exc)
        canon_data["characters"] = characters

        # 读取 locations/*.json → 合并为 locations 数组
        locs_dir = self._get_locations_dir(title)
        locations: list[dict] = []
        if locs_dir.is_dir():
            for lf in sorted(locs_dir.glob("*.json")):
                try:
                    loc_data = self._read_json_file(lf)
                    if isinstance(loc_data, dict):
                        locations.append(loc_data)
                except Exception as exc:
                    _log.warning("读取地点文件失败: %s, error=%s", lf.name, exc)
        canon_data["locations"] = locations

        # 确保 timeline 字段存在（前端需要）
        canon_data.setdefault("timeline", [])

        return canon_data

    @staticmethod
    def _write_json_file(filepath: Path, data: Any) -> None:
        """写入 JSON 文件（确保父目录存在）"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json_file(filepath: Path) -> Any:
        """读取 JSON 文件"""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
