# -*- coding: utf-8 -*-
"""小说加载器 — Canon JSON 加载 + 角色选择 + 目录扫描

支持:
  - 预生成的 Canon JSON 文件加载
  - 外部 Canon JSON 导入
  - novel/ 目录扫描（canon_*.json + 运行 Canon 目录）
  - 灵魂附生角色选择数据
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from server.config.paths import NOVEL_DIR

_log = logging.getLogger("Rain.NovelLoader")


class NovelLoader:
    """小说加载器 — 提供 Canon 加载、扫描、角色选择接口。"""

    CANON_PREFIX: str = "canon_"

    def __init__(self) -> None:
        self._canon_cache: dict[str, Any] = {}
        self._novel_dir_root: str = "novel"

    # ────────────────────────────────────────────────
    # 目录扫描
    # ────────────────────────────────────────────────

    def scan_novel_directory(self, novel_dir: str = "novel") -> dict:
        self._novel_dir_root = novel_dir
        txt_files = self.list_txt_files(novel_dir)
        canons = self.list_canon_jsons(novel_dir)
        running_canons = self._scan_running_canons(novel_dir)
        total_conflicts = sum(
            rc.get("conflict_count", 0) for rc in running_canons
        )
        return {
            "txt_files": txt_files,
            "canons": canons,
            "has_existing_canon": len(canons) > 0 or len(running_canons) > 0,
            "has_txt_files": len(txt_files) > 0,
            "running_canons": running_canons,
            "has_running_canon": len(running_canons) > 0,
            "conflict_count": total_conflicts,
        }

    def list_txt_files(self, novel_dir: str = "novel") -> list[dict]:
        novel_path = Path(novel_dir)
        if not novel_path.is_dir():
            return []
        result: list[dict] = []
        for f in sorted(novel_path.glob("*.txt")):
            try:
                stat = f.stat()
                result.append({
                    "name": f.name,
                    "path": str(f).replace("\\", "/"),
                    "size": stat.st_size,
                })
            except OSError:
                continue
        return result

    def list_canon_jsons(self, novel_dir: str = "novel") -> list[dict]:
        novel_path = Path(novel_dir)
        if not novel_path.is_dir():
            return []
        result: list[dict] = []
        for cf in sorted(novel_path.glob(f"{self.CANON_PREFIX}*.json")):
            if cf.parent != novel_path:
                continue
            if "_running.json" in cf.name or cf.stem.endswith("_running"):
                continue
            try:
                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                title = data.get("title", cf.stem.replace(self.CANON_PREFIX, "", 1))
                # ★ 如果已存在同名 running canon 目录，跳过 canon JSON（优先目录）
                if self._has_running_canon(title):
                    continue
                char_count = len(data.get("characters", []) or [])
                loc_count = len(data.get("locations", []) or [])
                meta = data.get("meta", {}) or {}
                generated_at = str(
                    meta.get("extraction_timestamp", "")
                    or meta.get("generated_at", "")
                    or data.get("extraction_timestamp", "")
                    or data.get("generated_at", "")
                    or ""
                )
                result.append({
                    "title": title,
                    "source_file": str(cf).replace("\\", "/"),
                    "char_count": char_count,
                    "loc_count": loc_count,
                    "generated_at": generated_at,
                })
            except (json.JSONDecodeError, Exception):
                continue
        return result

    def _scan_running_canons(self, novel_dir: str = "novel") -> list[dict]:
        novel_path = Path(novel_dir)
        if not novel_path.is_dir():
            return []
        result: list[dict] = []
        for subdir in sorted(novel_path.iterdir()):
            if not subdir.is_dir():
                continue
            meta_file = subdir / "meta.json"
            if not meta_file.is_file():
                continue
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            title = meta.get("title", subdir.name)
            chars_dir = subdir / "characters"
            locs_dir = subdir / "locations"
            char_count = len(list(chars_dir.glob("*.json"))) if chars_dir.is_dir() else 0
            loc_count = len(list(locs_dir.glob("*.json"))) if locs_dir.is_dir() else 0
            canon_file = subdir / "canon.json"
            conflict_count = 0
            if canon_file.is_file():
                try:
                    with open(canon_file, "r", encoding="utf-8") as cf:
                        canon_data = json.load(cf)
                    conflict_count = sum(
                        len(e.get("conflicts", []) or [])
                        for e in (canon_data.get("timeline", []) or [])
                        if isinstance(e, dict)
                    )
                except Exception:
                    pass
            result.append({
                "title": title,
                "dir": str(subdir).replace("\\", "/"),
                "char_count": char_count,
                "loc_count": loc_count,
                "conflict_count": conflict_count,
            })
        return result

    def _has_running_canon(self, title: str) -> bool:
        """检查是否已存在运行 Canon 目录"""
        novel_dir = Path(self._novel_dir_root) / title
        return (novel_dir / "meta.json").is_file()

    # ────────────────────────────────────────────────
    # 导入 Canon JSON
    # ────────────────────────────────────────────────

    def import_canon_from_json(self, json_str: str) -> Optional[dict]:
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        has_title = bool(data.get("title", ""))
        has_characters = bool(data.get("characters"))
        if not has_title and not has_characters:
            return None
        data.setdefault("title", "Untitled")
        data.setdefault("characters", [])
        data.setdefault("locations", [])
        data.setdefault("world_rules", [])
        data.setdefault("timeline", [])
        for i, c in enumerate(data.get("characters", []) or []):
            c = c if isinstance(c, dict) else {}
            if not c.get("id"):
                c["id"] = f"char_{i + 1:03d}"
        for i, loc in enumerate(data.get("locations", []) or []):
            loc = loc if isinstance(loc, dict) else {}
            if not loc.get("id"):
                loc["id"] = f"loc_{i + 1:03d}"
        if "meta" not in data:
            data["meta"] = {}
        data["meta"]["extraction_timestamp"] = datetime.now().isoformat()
        data["meta"]["extraction_confidence"] = 1.0
        self._canon_cache = data
        title = data.get("title", "Untitled")
        _log.info(
            "Canon JSON 导入成功: %s (%d 角色, %d 地点)",
            title,
            len(data.get("characters", []) or []),
            len(data.get("locations", []) or []),
        )
        return data

    # ────────────────────────────────────────────────
    # 灵魂附生 — 角色选择
    # ────────────────────────────────────────────────

    def get_character_list_for_selection(self, canon_data: dict) -> list[dict]:
        characters: list[dict] = canon_data.get("characters", []) or []
        locations: list[dict] = canon_data.get("locations", []) or []
        loc_map = {loc.get("id", ""): loc.get("name", "") for loc in locations}
        result: list[dict] = []
        for c in characters:
            if not isinstance(c, dict):
                continue
            personality = c.get("personality", {}) or {}
            traits = personality.get("traits", []) if isinstance(personality, dict) else []
            if isinstance(traits, list):
                traits = [str(t) for t in traits if t]
            else:
                traits = []
            start_loc_id = c.get("starting_location", "")
            start_loc_name = loc_map.get(start_loc_id, start_loc_id)
            relationships = c.get("key_relationships", []) or c.get("npc_relationships", []) or []
            rel_count = len(relationships)
            result.append({
                "id": c.get("id", ""),
                "name": c.get("name", "??"),
                "role": c.get("role", ""),
                "personality_traits": traits[:5],
                "appearance": (c.get("appearance", "") or "")[:120],
                "starting_location": start_loc_name,
                "memory_of_protagonist": c.get("memory_of_protagonist"),
                "relationship_count": rel_count,
            })
        return result

    def load_canon_with_memory(self, canon_data: dict) -> dict:
        characters: list[dict] = canon_data.get("characters", []) or []
        for c in characters:
            if not isinstance(c, dict):
                continue
            if "memory_of_protagonist" not in c:
                c["memory_of_protagonist"] = {}
        return canon_data
