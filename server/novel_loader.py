# -*- coding: utf-8 -*-
"""小说加载器 — 文本解析 + Canon 抽取 / 预生成 Canon 加载

支持:
  - 纯文本 (.txt) 读取
  - EPUB (.epub) 解析（需要 ebooklib）
  - 预生成的 Canon JSON 文件直接加载（优先）
  - 从小说文本中规则匹配提取角色/地点（回退）
  - 扫描 novel/ 目录，列出可用的 .txt 和 canon_*.json
  - 导入外部 Canon JSON 文件

架构:
  - 此类作为 Facade，内部可委托给提取器（Extractor）
  - 提取器逻辑已拆分到 server/extractors/ 模块
  - LLM 抽取逻辑保持不变（在 extract_canon_with_llm() 中）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 导入提取器模块
from .extractors import get_extractor, register_extractor

_log = logging.getLogger("Rain.NovelLoader")


class NovelLoader:
    """小说加载器（Facade 模式）

    此类提供统一的 novel 加载和 Canon 抽取接口。
    内部可委托给提取器实现（可替换）。

    向后兼容:
        - 保留所有原有方法签名
        - LLM 抽取逻辑完全不改动
        - 新增提取器支持（通过构造函数或 set_extractor()）
    """

    SUPPORTED_EXTENSIONS: set[str] = {".txt", ".epub", ".json"}
    MAX_FILE_SIZE: int = 20 * 1024 * 1024  # 放宽到 20MB，支持大长篇
    CANON_PREFIX: str = "canon_"  # Canon JSON 文件前缀

    def __init__(
        self,
        extractor_name: str = "regex",
        llm_extractor_name: str = "llm",
    ) -> None:
        """初始化 NovelLoader

        Args:
            extractor_name: 默认提取器名称（用于 extract_canon_from_text）
            llm_extractor_name: LLM 提取器名称（用于 extract_canon_with_llm）
        """
        self._text_cache: str = ""
        self._canon_cache: dict[str, Any] = {}

    # ────────────────────────────────────────────────
    # 目录扫描（不变）
    # ────────────────────────────────────────────────

    def scan_novel_directory(self, novel_dir: str = "novel") -> dict:
        """扫描 novel/ 目录，返回所有可用的 txt 和 canon 文件

        这是新的入口方法，替代旧的 try_load_canon_json() 自动加载行为。
        只扫描不加载，将决策权交给用户/前端。

        检测运行 Canon：扫描 novel/*/meta.json 识别已存在的运行 Canon 目录。

        Args:
            novel_dir: 小说目录路径

        Returns:
            ScanResult 字典:
            {
                "txt_files": [{"name": "xxx.txt", "path": "novel/xxx.txt", "size": 12345}],
                "canons": [{"title": "xxx", "source_file": "novel/canon_xxx.json",
                            "char_count": 8, "loc_count": 5, "generated_at": "ISO8601"}],
                "has_existing_canon": bool,
                "has_txt_files": bool,
                "running_canons": [{"title": str, "dir": str, "char_count": int, "loc_count": int}],
                "has_running_canon": bool,
            }
        """
        txt_files = self.list_txt_files(novel_dir)
        canons = self.list_canon_jsons(novel_dir)
        running_canons = self._scan_running_canons(novel_dir)
        # 统计 conflict 总数
        total_conflicts = sum(
            rc.get("conflict_count", 0) for rc in running_canons
        )
        return {
            "txt_files": txt_files,
            "canons": canons,
            "has_existing_canon": len(canons) > 0,
            "has_txt_files": len(txt_files) > 0,
            "running_canons": running_canons,
            "has_running_canon": len(running_canons) > 0,
            "conflict_count": total_conflicts,
        }

    def _scan_running_canons(self, novel_dir: str = "novel") -> list[dict]:
        """扫描 novel/*/meta.json 识别已存在的运行 Canon 目录

        Args:
            novel_dir: 小说目录路径

        Returns:
            [{"title": str, "dir": str, "char_count": int, "loc_count": int}]
        """
        import json as _json_local
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
                    meta = _json_local.load(f)
            except Exception:
                continue

            if not isinstance(meta, dict):
                continue

            title = meta.get("title", subdir.name)
            # 统计角色和地点数量
            chars_dir = subdir / "characters"
            locs_dir = subdir / "locations"
            char_count = len(list(chars_dir.glob("*.json"))) if chars_dir.is_dir() else 0
            loc_count = len(list(locs_dir.glob("*.json"))) if locs_dir.is_dir() else 0
            # 统计冲突数量（从 canon.json timeline conflicts）
            canon_file = subdir / "canon.json"
            conflict_count = 0
            if canon_file.is_file():
                try:
                    with open(canon_file, "r", encoding="utf-8") as cf:
                        canon_data = _json_local.load(cf)
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

    def list_txt_files(self, novel_dir: str = "novel") -> list[dict]:
        """列出 novel/ 目录下所有 .txt 文件

        Args:
            novel_dir: 小说目录路径

        Returns:
            [{"name": "xxx.txt", "path": "novel/xxx.txt", "size": 12345}]
        """
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
        """列出 novel/ 目录下所有 canon_*.json 文件并提取摘要

        Args:
            novel_dir: 小说目录路径

        Returns:
            [{"title": "xxx", "source_file": "novel/canon_xxx.json",
              "char_count": 8, "loc_count": 5, "generated_at": "ISO8601"}]
        """
        novel_path = Path(novel_dir)
        if not novel_path.is_dir():
            return []

        result: list[dict] = []
        for cf in sorted(novel_path.glob(f"{self.CANON_PREFIX}*.json")):
            # 过滤子目录中的文件（只取 novel/ 根目录下的文件）
            if cf.parent != novel_path:
                continue
            # 过滤 _running.json 文件（运行 Canon，不在扫描列表中展示）
            if "_running.json" in cf.name or cf.stem.endswith("_running"):
                continue

            try:
                if cf.stat().st_size > self.MAX_FILE_SIZE:
                    _log.warning("Canon 文件过大，跳过: %s", cf.name)
                    continue

                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if not isinstance(data, dict):
                    _log.warning("Canon JSON 格式无效 (非字典): %s", cf.name)
                    continue

                # 提取摘要信息
                title = data.get("title", cf.stem.replace(self.CANON_PREFIX, "", 1))
                char_count = len(data.get("characters", []) or [])
                loc_count = len(data.get("locations", []) or [])
                generated_at = ""

                # 从 meta 或顶层字段获取生成时间
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
            except json.JSONDecodeError as exc:
                _log.warning("Canon JSON 解析失败: %s, error=%s", cf.name, exc)
            except Exception as exc:
                _log.error("读取 Canon JSON 失败: %s, error=%s", cf.name, exc)

        return result

    # ────────────────────────────────────────────────
    # 导入 Canon JSON（不变）
    # ────────────────────────────────────────────────

    def import_canon_from_json(self, json_str: str) -> Optional[dict]:
        """解析并验证 Canon JSON 字符串

        验证规则（宽松）：
          - JSON 解析成功
          - 是 dict 类型
          - 有 title 或 characters 字段

        Args:
            json_str: Canon JSON 字符串

        Returns:
            Canon 字典，或 None（验证失败时）
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            _log.warning("Canon JSON 解析失败: %s", exc)
            return None

        if not isinstance(data, dict):
            _log.warning("Canon JSON 不是字典类型")
            return None

        # 至少需要 title 或 characters 字段
        has_title = bool(data.get("title", ""))
        has_characters = bool(data.get("characters"))

        if not has_title and not has_characters:
            _log.warning("Canon JSON 缺少必要字段 (title 或 characters)")
            return None

        # 确保必要字段存在
        data.setdefault("title", "Untitled")
        data.setdefault("characters", [])
        data.setdefault("locations", [])
        data.setdefault("world_rules", [])
        data.setdefault("timeline", [])

        # 补齐 character id
        for i, c in enumerate(data.get("characters", []) or []):
            c = c if isinstance(c, dict) else {}
            if not c.get("id"):
                c["id"] = f"char_{i + 1:03d}"

        # 补齐 location id
        for i, loc in enumerate(data.get("locations", []) or []):
            loc = loc if isinstance(loc, dict) else {}
            if not loc.get("id"):
                loc["id"] = f"loc_{i + 1:03d}"

        # 添加时间戳
        if "meta" not in data:
            data["meta"] = {}
        data["meta"]["extraction_timestamp"] = datetime.now().isoformat()
        data["meta"]["extraction_confidence"] = 1.0  # 人工导入，置信度最高

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
    # 预生成 Canon JSON 加载（不变）
    # ────────────────────────────────────────────────

    def try_load_canon_json(self, novel_dir: str = "novel") -> Optional[dict]:
        """从 novel/ 目录搜索并加载预生成的 Canon JSON

        搜索规则：
          - 查找 novel/canon_*.json
          - 如果有多个，返回第一个有效的
          - 验证 JSON 结构包含必要字段

        Args:
            novel_dir: 小说目录路径

        Returns:
            Canon 字典或 None
        """
        novel_path = Path(novel_dir)
        if not novel_path.is_dir():
            _log.warning("小说目录不存在: %s", novel_dir)
            return None

        canon_files = sorted(novel_path.glob(f"{self.CANON_PREFIX}*.json"))
        if not canon_files:
            _log.info("未找到预生成 Canon JSON，将使用规则抽取")
            return None

        for cf in canon_files:
            try:
                if cf.stat().st_size > self.MAX_FILE_SIZE:
                    _log.warning("Canon 文件过大，跳过: %s", cf.name)
                    continue

                with open(cf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 验证必要字段
                if not isinstance(data, dict):
                    _log.warning("Canon JSON 格式无效 (非字典): %s", cf.name)
                    continue

                self._canon_cache = data
                self._canon_cache["_source_file"] = str(cf)

                char_count = len(data.get("characters", []) or [])
                loc_count = len(data.get("locations", []) or [])
                title = data.get("title", cf.stem)
                _log.info(
                    "预生成 Canon 加载成功: %s → %d 角色, %d 地点",
                    cf.name, char_count, loc_count
                )
                return data

            except json.JSONDecodeError as exc:
                _log.warning("Canon JSON 解析失败: %s, error=%s", cf.name, exc)
            except Exception as exc:
                _log.error("加载 Canon JSON 失败: %s, error=%s", cf.name, exc)

        _log.warning("所有预生成 Canon JSON 加载失败，将使用规则抽取")
        return None

    # ────────────────────────────────────────────────
    # 文件读取（不变）
    # ────────────────────────────────────────────────

    def load_file(self, filepath: str) -> Optional[str]:
        """加载小说文件

        Args:
            filepath: 小说文件路径

        Returns:
            纯文本内容，或 None（失败时）
        """
        path = Path(filepath)
        if not path.is_file():
            _log.error("文件不存在: %s", filepath)
            return None

        if path.stat().st_size > self.MAX_FILE_SIZE:
            _log.error("文件过大: %s (%d bytes)", filepath, path.stat().st_size)
            return None

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            _log.error("不支持的文件格式: %s", suffix)
            return None

        try:
            if suffix == ".txt":
                text = self._load_txt(path)
            elif suffix == ".epub":
                text = self._load_epub(path)
            else:
                return None

            self._text_cache = text
            _log.info("小说加载成功: %s (%d 字符)", filepath, len(text))
            return text
        except Exception as exc:
            _log.error("加载小说失败: %s, error=%s", filepath, exc)
            return None

    def _load_txt(self, path: Path) -> str:
        """加载纯文本文件"""
        # 尝试多种编码
        for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法识别文件编码: {path}")

    def _load_epub(self, path: Path) -> str:
        """加载 EPUB 文件（需要 ebooklib + beautifulsoup4）

        如果依赖未安装，返回友好的错误信息。
        """
        try:
            from ebooklib import epub
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "EPUB 支持需要安装 ebooklib 和 beautifulsoup4。\n"
                "运行: pip install ebooklib beautifulsoup4"
            )

        book = epub.read_epub(str(path))
        chapters: list[str] = []

        for item in book.get_items_of_type(9):  # ITEM_DOCUMENT
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text()
            if text.strip():
                chapters.append(text)

        return "\n\n".join(chapters)

    # ────────────────────────────────────────────────
    # Canon 抽取
    # ────────────────────────────────────────────────

    async def extract_canon_from_text(
        self,
        text: str,
        filename: str = "",
    ) -> Optional[dict]:
        """从小说文本中提取 Canon 数据（规则匹配）

        此方法使用 RegexExtractor 进行正则抽取。
        已改为 async，统一事件循环调用链。

        Args:
            text: 小说全文
            filename: 原始文件名（用于推断标题）

        Returns:
            Canon 字典 {"title": str, "characters": [...], "locations": [...]}
        """
        from server.extractors import get_extractor
        extractor = get_extractor("regex")
        return await extractor.extract(text, filename)

    async def extract_canon_with_llm(
        self,
        provider: Any,
        text: str,
        filename: str = "",
    ) -> Optional[dict]:
        """使用 LLM 从小说文本中提取高质量 Canon 数据

        ⚠️ 此方法包含 LLM 调用逻辑，完全不改动。
        
        参数:
            provider: BaseProvider 实例（已配置）
            text: 小说全文
            filename: 原始文件名
            
        返回:
            Canon 字典（含角色/地点/世界观/时间线），或 None
        """
        import json as _json
        from datetime import datetime
        
        # 1. 构建 LLM Prompt
        title = filename.rsplit(".", 1)[0] if filename else "未知小说"
        
        system_prompt = """你是一个专业的小说分析助手。请从中文小说中提取结构化的世界观数据。

输出格式必须是严格的 JSON，包含以下字段:
{
  "title": "小说标题",
  "characters": [
    {
      "id": "char_001",
      "name": "角色名",
      "aliases": ["别名1", "别名2"],
      "role": "主角|重要配角|次要角色",
      "personality": {
        "core_motivation": "核心动机",
        "strengths": ["优点1", "优点2"],
        "flaws": ["缺点1", "缺点2"],
        "traits": ["特质1", "特质2"]
      },
      "appearance": "外貌描述",
      "abilities": ["能力1", "能力2"],
      "relationships": [{"target": "char_002", "type": "朋友", "intensity": 80}],
      "starting_location": "起始地点",
      "first_appearance": "首次出现章节",
      "key_traits": ["关键特质1", "关键特质2"],
      "anti_rules": ["禁忌1", "禁忌2"],
      "status": "alive|dead",
      "death_location": "",
      "death_time": "",
      "death_cause": ""
    }
  ],
  "locations": [
    {
      "id": "loc_001",
      "name": "地点名",
      "type": "城市|村庄|建筑|区域",
      "parent": "上级地点",
      "description": "地点描述",
      "atmosphere": "氛围"
    }
  ],
  "world_rules": {
    "era": "时代背景",
    "magic_system": "魔法体系描述",
    "society": "社会结构描述",
    "species": ["种族1", "种族2"]
  },
  "timeline": []
}

重要规则:
1. 只输出 JSON，不要有任何其他文字
2. id 必须唯一，格式为 char_XXX 或 loc_XXX
3. 如果信息不足，可以留空或给合理推断
4. 确保输出是合法的 JSON"""

        _llm_trunc_limit = 15000  # LLM 抽取截断，可通过 config.yaml truncation.llm_extract 调整
        user_prompt = f"请从以下小说《{title}》的片段中提取世界观数据。\n\n小说内容:\n{text[:_llm_trunc_limit]}"

        try:
            # 2. 调用 LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            _log.info("开始 LLM Canon 抽取: %s", title)
            
            # 调用 provider（假设 provider 有 complete 方法）
            if hasattr(provider, 'complete'):
                response = await provider.complete(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4096
                )
            elif hasattr(provider, 'chat'):
                response = await provider.chat(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=4096
                )
            else:
                _log.error("Provider 不支持 complete 或 chat 方法")
                return None
            
            # 3. 解析响应
            content = ""
            if isinstance(response, dict):
                content = response.get("content", "") or response.get("text", "")
            elif isinstance(response, str):
                content = response
            else:
                content = str(response)
            
            # 提取 JSON（可能包含在 markdown 代码块中）
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
            if json_match:
                content = json_match.group(1)
            else:
                # 尝试直接解析
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    content = content[json_start:json_end]
            
            canon_data = _json.loads(content)
            
            # 4. 验证和清理
            if not isinstance(canon_data, dict):
                _log.error("LLM 返回的不是字典")
                return None
            
            # 确保必要字段
            canon_data.setdefault("title", title)
            canon_data.setdefault("characters", [])
            canon_data.setdefault("locations", [])
            canon_data.setdefault("world_rules", {})
            canon_data.setdefault("timeline", [])
            
            # 添加元数据
            if "meta" not in canon_data:
                canon_data["meta"] = {}
            canon_data["meta"]["extraction_timestamp"] = datetime.now().isoformat()
            canon_data["meta"]["extraction_method"] = "llm"
            canon_data["meta"]["extraction_confidence"] = 0.85
            
            _log.info(
                "LLM Canon 抽取成功: %s (%d 角色, %d 地点)",
                title,
                len(canon_data.get("characters", [])),
                len(canon_data.get("locations", []))
            )
            return canon_data
            
        except _json.JSONDecodeError as exc:
            _log.error("LLM 响应 JSON 解析失败: %s", exc)
            return None
        except Exception as exc:
            _log.error("LLM Canon 抽取异常: %s", exc)
            return None

    async def extract_canon_from_file(self, filepath: str) -> Optional[dict]:
        """从文件加载并抽取 Canon

        Args:
            filepath: 小说文件路径

        Returns:
            Canon 字典或 None
        """
        text = self.load_file(filepath)
        if text is None:
            return None

        filename = Path(filepath).name
        return await self.extract_canon_from_text(text, filename)

    # ────────────────────────────────────────────────
    # 持久化（不变）
    # ────────────────────────────────────────────────

    def save_canon_json(self, canon: dict, novel_title: str = "") -> Optional[str]:
        """将 Canon 字典保存为 novel/canon_{title}.json

        Args:
            canon: Canon 字典
            novel_title: 小说标题（用于生成文件名）

        Returns:
            保存成功的文件路径，或 None
        """
        title = novel_title or str(canon.get("title", "unknown"))
        # 清理文件名非法字符
        safe_title = "".join(c for c in title if c.isalnum() or c in "._- ()（）")
        if not safe_title:
            safe_title = "unknown"

        from server.paths import NOVEL_DIR
        out_dir = NOVEL_DIR
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{self.CANON_PREFIX}{safe_title}.json"

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(canon, f, ensure_ascii=False, indent=2)
            _log.info("Canon 已保存: %s", out_path)
            return str(out_path)
        except Exception as exc:
            _log.error("保存 Canon 失败: %s", exc)
            return None

    # ────────────────────────────────────────────────
    # 缓存（不变）
    # ────────────────────────────────────────────────

    def get_cached_canon(self) -> dict:
        """获取缓存的 Canon 数据"""
        return dict(self._canon_cache)

    def get_text_preview(self, max_chars: int = 500) -> str:
        """获取文本预览"""
        if not self._text_cache:
            return ""
        return self._text_cache[:max_chars]

    # ────────────────────────────────────────────────
    # 冲突种子提取（T02 新增）
    # ────────────────────────────────────────────────

    def load_conflicts_from_canon(self, canon_data: dict) -> list[dict]:
        """从 canon 的 timeline 中提取所有 conflicts 种子。

        遍历 timeline 数组中的每个事件，收集所有 conflicts 字段。
        每个 conflict 会被注入 _source_event_id 以追溯来源。

        Args:
            canon_data: Canon 字典（含 timeline 列表）

        Returns:
            冲突种子列表（已规范化）
        """
        timeline: list[dict] = canon_data.get("timeline", []) or []
        conflicts: list[dict] = []
        seen_ids: set[str] = set()

        for event in timeline:
            event = event if isinstance(event, dict) else {}
            event_id = str(event.get("id", ""))
            raw_conflicts: list[dict] = event.get("conflicts", []) or []
            for raw in raw_conflicts:
                raw = raw if isinstance(raw, dict) else {}
                seed_id = str(raw.get("id", ""))
                if seed_id in seen_ids:
                    continue
                if seed_id:
                    seen_ids.add(seed_id)
                seed = {
                    "id": seed_id,
                    "type": str(raw.get("type", "mystery")),
                    "description": str(raw.get("description", "")),
                    "involved_characters": list(raw.get("involved_characters", []) or []),
                    "involved_locations": list(raw.get("involved_locations", []) or []),
                    "intensity": float(raw.get("intensity", 0.5)),
                    "variants": list(raw.get("variants", []) or []),
                    "_source_event_id": event_id,
                }
                conflicts.append(seed)

        _log.info(
            "从 canon timeline 中提取了 %d 个冲突种子",
            len(conflicts),
        )
        return conflicts
