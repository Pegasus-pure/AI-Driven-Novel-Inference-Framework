# -*- coding: utf-8 -*-
"""正则提取器 — 从小说文本中通过规则匹配提取 Canon

将原 novel_loader.py 中的 extract_canon_from_text() 逻辑封装为独立提取器。
不依赖 LLM，纯规则匹配，适合快速预览或 LLM 不可用时的回退方案。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from .base import CanonExtractor

_log = logging.getLogger("AINovelFramework.Extractors.Regex")


class RegexExtractor(CanonExtractor):
    """正则提取器

    使用正则表达式从小说文本中提取:
        - 角色名（基于对话模式、称呼模式）
        - 地点名（基于地名后缀）

    提取质量低于 LLM，但速度快、无外部依赖。
    """

    def __init__(self) -> None:
        """初始化正则提取器"""
        pass

    async def extract(
        self,
        text: str,
        filename: str,
        provider: Any = None,
    ) -> Optional[dict]:
        """从小说文本中提取 Canon 数据（规则匹配）

        Args:
            text: 小说全文
            filename: 原始文件名（用于推断标题）
            provider: 忽略（正则提取器不需要 LLM）

        Returns:
            Canon 字典 {"title": str, "characters": [...], "locations": [...]}
        """
        return self._extract_canon_from_text(text, filename)

    def _extract_canon_from_text(
        self,
        text: str,
        filename: str = "",
    ) -> Optional[dict]:
        """从小说文本中提取 Canon 数据（规则匹配）

        提取角色名、地点名等结构化信息。
        对于更精确的抽取，可以使用 LLM。

        Args:
            text: 小说全文
            filename: 原始文件名（用于推断标题）

        Returns:
            Canon 字典 {"title": str, "characters": [...], "locations": [...]}
        """
        text = text.strip()
        if not text:
            return None

        # 小说标题（从文件名推断）
        title = filename
        if title:
            # 去除扩展名和路径
            from pathlib import Path
            title = Path(title).stem
        else:
            # 尝试从文本首行获取
            first_line = text.split("\n")[0].strip()
            if first_line and len(first_line) < 100:
                title = first_line.lstrip("#").strip()

        # ── 角色抽取（基于常见模式）──
        characters: list[dict] = []
        # 匹配中文名（2-4字）+ 引号对话
        char_names: set[str] = set()
        name_pattern = re.compile(r'[\u4e00-\u9fff]{2,4}(?=说|道|问|答|喊|叫|笑|哭|叹|想|心中|低声|大声)')
        for match in name_pattern.finditer(text):
            char_names.add(match.group())

        # 匹配「某某」格式
        bracket_pattern = re.compile(r'「([\u4e00-\u9fff]{2,4})」')
        for match in bracket_pattern.finditer(text):
            char_names.add(match.group(1))

        for i, name in enumerate(list(char_names)[:20]):  # 最多 20 个角色
            # 在文本中查找更多上下文
            name_escaped = re.escape(name)
            contexts = re.findall(
                rf'.{{0,30}}{name_escaped}.{{0,30}}',
                text[:50000]
            )
            description = ""
            if contexts:
                description = contexts[0].strip()

            characters.append({
                "id": f"char_{i + 1:03d}",
                "name": name,
                "personality": "",
                "role": "疑似角色",
                "description": description[:200],
                "first_appearance": "",
                "key_traits": [],
                "anti_rules": [],
            })

        # ── 地点抽取 ──
        locations: list[dict] = []
        loc_names: set[str] = set()
        loc_patterns = [
            re.compile(r'[\u4e00-\u9fff]{2,6}(?:城|国|镇|村|庄|店|馆|院|阁|楼|塔|殿|宫|府|山|海|林|谷|原|野)'),
            re.compile(r'[\u4e00-\u9fff]{2,4}(?:酒馆|客栈|公会|广场|市场|学院|寺庙|教堂|城堡|森林|沙漠|草原)'),
        ]
        for pat in loc_patterns:
            for match in pat.finditer(text):
                loc_names.add(match.group())

        for i, name in enumerate(list(loc_names)[:15]):  # 最多 15 个地点
            locations.append({
                "id": f"loc_{i + 1:03d}",
                "name": name,
                "type": "未知",
                "description": "",
                "atmosphere": "",
            })

        from typing import Any
        canon: dict[str, Any] = {
            "title": title,
            "author": "",
            "characters": characters,
            "locations": locations,
            "world_rules": [],
            "timeline": [],
        }

        _log.info("Canon 抽取完成: %d 角色, %d 地点", len(characters), len(locations))
        return canon
