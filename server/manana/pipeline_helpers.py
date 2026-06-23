# -*- coding: utf-8 -*-
"""Pipeline 工具函数模块

包含：
  - replace_ids_with_names: 安全替换 ID 占位符为可读名称
  - NarrativeSplitter: 叙事文本智能分块策略
"""

from __future__ import annotations

import re
from typing import Any


# ═══════════════════════════════════════════════════════
# P2-F: ID 替换安全化
# ═══════════════════════════════════════════════════════

def replace_ids_with_names(text: str, id_map: dict[str, str]) -> str:
    """安全替换 ID → 名称，避免子串误匹配。

    使用正则确保只替换完整 ID（前后为单词边界或非字母数字）。
    按 ID 长度降序替换（先替换长 ID 避免部分匹配）。

    Args:
        text: 包含 ID 占位符的文本
        id_map: {id: name} 映射表

    Returns:
        替换后的文本
    """
    if not id_map:
        return text

    # 按 ID 长度降序（先替换长 ID，避免子串冲突）
    sorted_ids = sorted(id_map.keys(), key=len, reverse=True)

    for old_id in sorted_ids:
        new_name = id_map[old_id]
        escaped = re.escape(str(old_id))
        text = re.sub(rf'(?<!\w){escaped}(?!\w)', str(new_name), text)

    return text


# ═══════════════════════════════════════════════════════
# P2-C: 叙事文本智能分块
# ═══════════════════════════════════════════════════════

class NarrativeSplitter:
    """叙事文本智能分块策略。

    根据叙事整体长度动态选择分块策略：

      短叙事 (< 100字符):  整段发送或 2-3 大块
      中篇叙事 (100-500):   按段落分块
      长叙事 (> 500):       先按段落，再按语义断句

    目标块大小（按叙事长度动态调整）：
      MIN_CHUNK_SIZE = 30
      IDEAL_CHUNK_SIZE = 80
      MAX_CHUNK_SIZE = 150
    """

    MIN_CHUNK_SIZE = 30
    IDEAL_CHUNK_SIZE = 80
    MAX_CHUNK_SIZE = 150

    @classmethod
    def split(cls, text: str) -> list[str]:
        """根据叙事长度动态选择分块策略。"""
        total_len = len(text)

        if total_len < 100:
            return cls._short_split(text)
        elif total_len < 500:
            return cls._paragraph_split(text)
        else:
            return cls._semantic_split(text)

    @classmethod
    def _paragraph_split(cls, text: str) -> list[str]:
        """按段落分块。"""
        paragraphs = re.split(r'\n\s*\n', text.strip())
        chunks: list[str] = []
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) > cls.IDEAL_CHUNK_SIZE and buffer:
                chunks.append(buffer.strip())
                buffer = ""
            buffer += para + "\n\n"
        if buffer.strip():
            chunks.append(buffer.strip())
        return chunks if chunks else [text]

    @classmethod
    def _semantic_split(cls, text: str) -> list[str]:
        """长叙事：按语义断句（段落 + 长句内按标点）。"""
        chunks: list[str] = []
        paragraphs = text.strip().split('\n\n')
        for para in paragraphs:
            if len(para) <= cls.IDEAL_CHUNK_SIZE:
                chunks.append(para)
            else:
                chunks.extend(cls._sentence_split(para))
        return chunks

    @classmethod
    def _short_split(cls, text: str) -> list[str]:
        """短叙事：按标点分成 2-3 个大块。"""
        sentences = re.split(r'(?<=[。！？\n])', text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) <= 2:
            return sentences if sentences else [text]
        return cls._merge_sentences(sentences, cls.IDEAL_CHUNK_SIZE)

    @classmethod
    def _sentence_split(cls, text: str) -> list[str]:
        """长段落内按句号/问号/感叹号/分号分割。"""
        parts = re.split(r'(?<=[。！？；;])', text)
        return [p.strip() for p in parts if p.strip()]

    @classmethod
    def _merge_sentences(cls, sentences: list[str], target_size: int) -> list[str]:
        """合并短句使每块接近目标大小。"""
        chunks: list[str] = []
        buffer = ""
        for s in sentences:
            if len(buffer) + len(s) > target_size and buffer:
                chunks.append(buffer.strip())
                buffer = s
            else:
                buffer += s
        if buffer.strip():
            chunks.append(buffer.strip())
        return chunks


def split_narrative(text: str) -> list[str]:
    """便捷函数：对叙事文本执行智能分块。

    Args:
        text: 叙事文本

    Returns:
        分块列表
    """
    return NarrativeSplitter.split(text)
