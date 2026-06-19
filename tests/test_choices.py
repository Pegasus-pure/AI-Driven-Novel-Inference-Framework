# -*- coding: utf-8 -*-
"""QA Test Suite — Choice-Driven Interaction System

覆盖范围:
  1. MananaSchema.validate_choices — choices 验证逻辑
  2. SceneComposer.run() — choices 兜底和补齐逻辑
  3. GameSession — _get_default_choices()、stream_beat choices 透传、run_beat choices 处理
  4. main.py — player_action 中 choice_id 提取

运行方式:
  cd E:\\Godot-Project\\Round
  python -m pytest tests/test_choices.py -v
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path

# ── 将项目根目录加入 Python path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


# ═══════════════════════════════════════════════════════
# 1. MananaSchema.validate_choices 测试
# ═══════════════════════════════════════════════════════

class TestValidateChoices(unittest.TestCase):
    """MananaSchema.validate_choices 方法测试"""

    def setUp(self):
        from server.manana.schema import MananaSchema
        self.schema = MananaSchema

    def test_valid_choices(self):
        """合法的 choices 列表应返回 valid=True"""
        choices = [
            {"id": "c1", "text": "仔细观察周围环境", "hint": "了解你身处何方", "next_scene_hint": "observe"},
            {"id": "c2", "text": "检查自己的状态", "hint": "弄清楚你是谁", "next_scene_hint": "examine"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_valid_choices_single(self):
        """只有 1 个 choice 也应合法（校验格式，不校验数量）"""
        choices = [
            {"id": "c1", "text": "向前探索", "hint": "前进", "next_scene_hint": "forward"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertTrue(result["valid"])

    def test_valid_choices_four(self):
        """4 个 choice 也应合法"""
        choices = [
            {"id": f"c{i}", "text": f"选项{i}", "hint": f"提示{i}", "next_scene_hint": f"hint_{i}"}
            for i in range(1, 5)
        ]
        result = self.schema.validate_choices(choices)
        self.assertTrue(result["valid"])

    def test_invalid_not_a_list(self):
        """非列表输入应返回 valid=False"""
        result = self.schema.validate_choices("not a list")
        self.assertFalse(result["valid"])
        self.assertIn("choices must be a list", result["errors"][0])

        result = self.schema.validate_choices({})
        self.assertFalse(result["valid"])

        result = self.schema.validate_choices(None)
        self.assertFalse(result["valid"])

    def test_missing_id_field(self):
        """缺少 id 字段应返回错误"""
        choices = [
            {"text": "选项一", "hint": "提示", "next_scene_hint": "hint1"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("missing required field: 'id'" in e for e in result["errors"]))

    def test_missing_text_field(self):
        """缺少 text 字段应返回错误"""
        choices = [
            {"id": "c1", "hint": "提示", "next_scene_hint": "hint1"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("missing required field: 'text'" in e for e in result["errors"]))

    def test_missing_hint_field(self):
        """缺少 hint 字段应返回错误"""
        choices = [
            {"id": "c1", "text": "选项一", "next_scene_hint": "hint1"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("missing required field: 'hint'" in e for e in result["errors"]))

    def test_missing_next_scene_hint_field(self):
        """缺少 next_scene_hint 字段应返回错误"""
        choices = [
            {"id": "c1", "text": "选项一", "hint": "提示"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("missing required field: 'next_scene_hint'" in e for e in result["errors"]))

    def test_missing_all_fields(self):
        """choice 为空 dict 应返回 4 个错误"""
        choices = [
            {},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["errors"]), 4)

    def test_choice_not_a_dict(self):
        """choices 中的元素不是 dict 应报错"""
        choices = [
            "c1",
            {"id": "c2", "text": "选项", "hint": "提示", "next_scene_hint": "hint"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("expected dict" in e for e in result["errors"]))

    def test_field_type_validation(self):
        """字段类型错误应报错（id 必须是 str）"""
        choices = [
            {"id": 123, "text": "选项", "hint": "提示", "next_scene_hint": "hint"},
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        self.assertTrue(any("id" in e and "str" in e for e in result["errors"]))

    def test_mixed_valid_and_invalid(self):
        """混合有效和无效 choices"""
        choices = [
            {"id": "c1", "text": "有效选项", "hint": "提示", "next_scene_hint": "hint1"},
            {"id": "c2"},  # 缺 text/hint/next_scene_hint
        ]
        result = self.schema.validate_choices(choices)
        self.assertFalse(result["valid"])
        missing_count = sum(1 for e in result["errors"] if "missing required field" in e)
        self.assertEqual(missing_count, 3)

    def test_empty_choices_list(self):
        """空列表应视为合法（空列表也是 list）"""
        result = self.schema.validate_choices([])
        self.assertTrue(result["valid"])

    def test_validate_composer_output_with_valid_choices(self):
        """validate_composer_output 在 choices 合法时应通过"""
        data = {
            "ending_hook": "hook",
            "action_hints": ["hint1"],
            "music_mood": "神秘",
            "choices": [
                {"id": "c1", "text": "选项一", "hint": "提示", "next_scene_hint": "hint1"},
            ],
        }
        result = self.schema.validate_composer_output(data)
        self.assertTrue(result["valid"])

    def test_validate_composer_output_with_invalid_choices(self):
        """validate_composer_output 在 choices 非法时应携带 choices 的错误"""
        data = {
            "ending_hook": "hook",
            "action_hints": ["hint1"],
            "music_mood": "神秘",
            "choices": [
                {"id": "c1"},  # 缺少 text/hint/next_scene_hint
            ],
        }
        result = self.schema.validate_composer_output(data)
        self.assertFalse(result["valid"])
        self.assertTrue(any("choices[0]" in e for e in result["errors"]))

    def test_validate_composer_output_without_choices(self):
        """validate_composer_output 在没有 choices 字段时不应报 choices 的错误，
        但应报 Missing required key 错误（choices 是 COMPOSER_OUTPUT_KEYS 必填）"""
        data = {
            "ending_hook": "hook",
            "action_hints": ["hint1"],
            "music_mood": "神秘",
        }
        result = self.schema.validate_composer_output(data)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Missing required key: 'choices'" in e for e in result["errors"]))


# ═══════════════════════════════════════════════════════
# 2. SceneComposer.run() choices 处理测试（同步包装）
# ═══════════════════════════════════════════════════════

class TestSceneComposerChoices(unittest.TestCase):
    """SceneComposer.run() 中 choices 兜底逻辑测试"""

    @classmethod
    def setUpClass(cls):
        from server.manana.agents import SceneComposer
        cls.SceneComposer = SceneComposer

    def setUp(self):
        self.composer = self.SceneComposer()

    def _make_composer_result(self, raw: dict) -> dict:
        return {
            "ok": True,
            "content": "叙事文本...\n---JSON---\n" + json.dumps(raw, ensure_ascii=False),
            "raw": raw,
        }

    def _run_async(self, coro):
        """同步运行协程"""
        return asyncio.run(coro)

    def test_no_choices_uses_defaults(self):
        """raw 中没有 choices 时自动生成兜底 choices（2 个）"""
        raw_no_choices = {
            "ending_hook": "测试钩子",
            "action_hints": ["测试提示"],
            "music_mood": "神秘",
        }

        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = self._make_composer_result(raw_no_choices)
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        self.assertTrue(result["ok"])
        choices = result["raw"].get("choices", [])
        self.assertIsInstance(choices, list)
        self.assertGreaterEqual(len(choices), 2)
        for c in choices[:2]:
            self.assertIn("id", c)
            self.assertIn("text", c)
            self.assertIn("hint", c)
            self.assertIn("next_scene_hint", c)

    def test_choices_less_than_2_padded(self):
        """choices 少于 2 个时补齐到 2 个"""
        raw_one_choice = {
            "ending_hook": "钩子",
            "action_hints": ["提示"],
            "music_mood": "神秘",
            "choices": [
                {"id": "c1", "text": "唯一选项", "hint": "唯一提示", "next_scene_hint": "only"},
            ],
        }

        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = self._make_composer_result(raw_one_choice)
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        choices = result["raw"].get("choices", [])
        self.assertGreaterEqual(len(choices), 2)
        self.assertEqual(choices[0]["id"], "c1")
        self.assertEqual(choices[0]["text"], "唯一选项")

    def test_choices_more_than_4_capped(self):
        """超过 4 个 choices 时截断到 4 个"""
        many_choices = [
            {"id": f"c{i}", "text": f"选项{i}", "hint": f"提示{i}", "next_scene_hint": f"hint{i}"}
            for i in range(1, 7)
        ]
        raw = {
            "ending_hook": "钩子",
            "action_hints": ["提示"],
            "music_mood": "神秘",
            "choices": many_choices,
        }

        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = self._make_composer_result(raw)
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        choices = result["raw"].get("choices", [])
        self.assertLessEqual(len(choices), 4)

    def test_invalid_choices_filtered_and_padded(self):
        """包含无效字段的 choices 被过滤后如果少于 2 个，补齐到 2 个"""
        raw = {
            "ending_hook": "钩子",
            "action_hints": ["提示"],
            "music_mood": "神秘",
            "choices": [
                {"id": "c1"},  # 缺少 text/hint/next_scene_hint
                {"id": "c2", "text": "有效选项", "hint": "提示", "next_scene_hint": "valid"},
            ],
        }

        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = self._make_composer_result(raw)
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        choices = result["raw"].get("choices", [])
        self.assertGreaterEqual(len(choices), 2)
        c_ids = [c["id"] for c in choices]
        self.assertNotIn("c1", c_ids)
        self.assertIn("c2", c_ids)

    def test_llm_failure_returns_error(self):
        """LLM 调用失败时返回错误，不处理 choices"""
        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = {"ok": False, "content": "", "raw": {}, "error": "LLM call failed"}
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_choices_all_invalid_filtered_and_use_defaults(self):
        """所有 choices 都无效时，全部过滤并使用默认 choices"""
        raw = {
            "ending_hook": "钩子",
            "action_hints": ["提示"],
            "music_mood": "神秘",
            "choices": [
                {"id": "c1"},  # 缺字段
                {},           # 空
                "not a dict", # 非 dict
            ],
        }

        with patch.object(self.composer, '_call_llm', new_callable=AsyncMock) as mock_call_llm:
            mock_call_llm.return_value = self._make_composer_result(raw)
            result = self._run_async(self.composer.run({
                "director_output": {},
                "character_outputs": [],
                "scene_context_summary": {},
            }))

        choices = result["raw"].get("choices", [])
        self.assertGreaterEqual(len(choices), 2)
        self.assertEqual(choices[0]["id"], "c1")
        self.assertEqual(choices[0]["text"], "仔细观察周围环境")


# ═══════════════════════════════════════════════════════
# 3. GameSession choices 处理测试
# ═══════════════════════════════════════════════════════

class TestGameSessionChoices(unittest.TestCase):
    """GameSession 中 choices 相关方法测试"""

    def setUp(self):
        from server.game_session import GameSession, _DEFAULT_CHOICES
        self.gs = GameSession("test_session")
        self.defaults = _DEFAULT_CHOICES

    def test_default_choices_constant_exists(self):
        """_DEFAULT_CHOICES 常量存在且结构正确"""
        from server.game_session import _DEFAULT_CHOICES
        self.assertIsInstance(_DEFAULT_CHOICES, list)
        self.assertGreaterEqual(len(_DEFAULT_CHOICES), 2)
        for c in _DEFAULT_CHOICES:
            self.assertIn("id", c)
            self.assertIn("text", c)
            self.assertIn("hint", c)
            self.assertIn("next_scene_hint", c)

    def test_default_choices_has_three_items(self):
        """_DEFAULT_CHOICES 有 3 个默认选项"""
        from server.game_session import _DEFAULT_CHOICES
        self.assertEqual(len(_DEFAULT_CHOICES), 3)

    def test_get_default_choices_returns_deep_copy(self):
        """_get_default_choices() 返回深拷贝，修改不影响原数据"""
        choices = self.gs._get_default_choices()
        self.assertEqual(len(choices), len(self.defaults))
        choices[0]["id"] = "modified"
        from server.game_session import _DEFAULT_CHOICES
        self.assertEqual(_DEFAULT_CHOICES[0]["id"], "c1")

    def test_get_default_choices_structure(self):
        """_get_default_choices() 返回正确结构"""
        choices = self.gs._get_default_choices()
        for c in choices:
            self.assertIn("id", c)
            self.assertIn("text", c)
            self.assertIn("hint", c)
            self.assertIn("next_scene_hint", c)
            self.assertIsInstance(c["id"], str)
            self.assertIsInstance(c["text"], str)
            self.assertIsInstance(c["hint"], str)
            self.assertIsInstance(c["next_scene_hint"], str)

    def test_run_beat_ensures_choices(self):
        """run_beat 返回结果中包含 choices 字段且确保非空"""
        import inspect
        source = inspect.getsource(self.gs.run_beat)
        self.assertIn("choices", source)
        self.assertIn("_get_default_choices", source)

    def test_stream_beat_narrative_complete_has_choices(self):
        """stream_beat 的 narrative_complete 消息包含 choices 字段"""
        import inspect
        source = inspect.getsource(self.gs.stream_beat)
        self.assertIn("choices", source)
        self.assertIn("narrative_complete", source)

    def test_stream_beat_choices_capped_at_4(self):
        """stream_beat 中的 choices 最多 4 个"""
        import inspect
        source = inspect.getsource(self.gs.stream_beat)
        self.assertIn("[:4]", source)

    def _run_async(self, coro):
        return asyncio.run(coro)

    def test_stream_beat_empty_choices_uses_defaults(self):
        """stream_beat 中 choices 为空时使用默认 choices"""
        from server.game_session import _DEFAULT_CHOICES

        with patch.object(self.gs, '_split_narrative', return_value=["叙事文本"]):
            with patch.object(self.gs, '_get_default_choices', return_value=copy.deepcopy(_DEFAULT_CHOICES)):
                self.gs.run_beat = AsyncMock(return_value={
                    "narrative_text": "测试叙事",
                    "narrative_mode": "exploration",
                    "action_hints": ["提示1"],
                    "ending_hook": "钩子",
                    "choices": [],
                })

                sent_chunks = []

                async def send_chunk(chunk):
                    sent_chunks.append(chunk)

                self.gs.world_state.world_divergence = 0.0
                self.gs.beat_count = 1
                self.gs.world_state.player_location = ""
                self.gs.world_state.characters_state = {}
                self.gs.world_state.player_reputation = {}

                self._run_async(self.gs.stream_beat("测试动作", send_chunk))

        complete_chunks = [c for c in sent_chunks if c.get("type") == "narrative_complete"]
        self.assertEqual(len(complete_chunks), 1)
        payload = complete_chunks[0]["payload"]
        self.assertIn("choices", payload)
        self.assertEqual(len(payload["choices"]), 3)

    def test_stream_beat_valid_choices_preserved(self):
        """stream_beat 中有效 choices 被透传"""
        valid_choices = [
            {"id": "c1", "text": "探索洞穴", "hint": "深入调查", "next_scene_hint": "cave"},
            {"id": "c2", "text": "返回村庄", "hint": "寻求帮助", "next_scene_hint": "village"},
        ]

        with patch.object(self.gs, '_split_narrative', return_value=["叙事文本"]):
            self.gs.run_beat = AsyncMock(return_value={
                "narrative_text": "测试叙事",
                "narrative_mode": "exploration",
                "action_hints": ["提示1"],
                "ending_hook": "钩子",
                "choices": valid_choices,
            })

            sent_chunks = []

            async def send_chunk(chunk):
                sent_chunks.append(chunk)

            self.gs.world_state.world_divergence = 0.0
            self.gs.beat_count = 1
            self.gs.world_state.player_location = ""
            self.gs.world_state.characters_state = {}
            self.gs.world_state.player_reputation = {}

            self._run_async(self.gs.stream_beat("测试动作", send_chunk))

        complete_chunks = [c for c in sent_chunks if c.get("type") == "narrative_complete"]
        self.assertEqual(len(complete_chunks), 1)
        payload = complete_chunks[0]["payload"]
        self.assertEqual(len(payload["choices"]), 2)
        self.assertEqual(payload["choices"][0]["text"], "探索洞穴")
        self.assertEqual(payload["choices"][1]["text"], "返回村庄")

    def test_stream_beat_invalid_choices_filtered_with_default_fallback(self):
        """stream_beat 中缺字段的 choices 被过滤，不足 2 个时用默认补齐"""
        from server.game_session import _DEFAULT_CHOICES

        with patch.object(self.gs, '_split_narrative', return_value=["叙事文本"]):
            with patch.object(self.gs, '_get_default_choices', return_value=copy.deepcopy(_DEFAULT_CHOICES)):
                self.gs.run_beat = AsyncMock(return_value={
                    "narrative_text": "测试叙事",
                    "narrative_mode": "exploration",
                    "action_hints": ["提示1"],
                    "ending_hook": "钩子",
                    "choices": [
                        {"id": "c1"},  # 缺字段
                        {"id": "c2", "text": "有效选项", "hint": "提示", "next_scene_hint": "valid"},
                    ],
                })

                sent_chunks = []

                async def send_chunk(chunk):
                    sent_chunks.append(chunk)

                self.gs.world_state.world_divergence = 0.0
                self.gs.beat_count = 1
                self.gs.world_state.player_location = ""
                self.gs.world_state.characters_state = {}
                self.gs.world_state.player_reputation = {}

                self._run_async(self.gs.stream_beat("测试动作", send_chunk))

        complete_chunks = [c for c in sent_chunks if c.get("type") == "narrative_complete"]
        self.assertEqual(len(complete_chunks), 1)
        payload = complete_chunks[0]["payload"]
        choices = payload["choices"]
        # 有效 choices 不足 2 个，应使用默认补齐
        self.assertGreaterEqual(len(choices), 2)
        c_ids = [c["id"] for c in choices]
        self.assertIn("c2", c_ids)

    def test_stream_beat_all_invalid_uses_defaults(self):
        """stream_beat 中所有 choices 都无效时使用默认 choices"""
        from server.game_session import _DEFAULT_CHOICES

        with patch.object(self.gs, '_split_narrative', return_value=["叙事文本"]):
            with patch.object(self.gs, '_get_default_choices', return_value=copy.deepcopy(_DEFAULT_CHOICES)):
                self.gs.run_beat = AsyncMock(return_value={
                    "narrative_text": "测试叙事",
                    "narrative_mode": "exploration",
                    "action_hints": ["提示1"],
                    "ending_hook": "钩子",
                    "choices": [
                        {"id": "c1"},
                        {},
                    ],
                })

                sent_chunks = []

                async def send_chunk(chunk):
                    sent_chunks.append(chunk)

                self.gs.world_state.world_divergence = 0.0
                self.gs.beat_count = 1
                self.gs.world_state.player_location = ""
                self.gs.world_state.characters_state = {}
                self.gs.world_state.player_reputation = {}

                self._run_async(self.gs.stream_beat("测试动作", send_chunk))

        complete_chunks = [c for c in sent_chunks if c.get("type") == "narrative_complete"]
        self.assertEqual(len(complete_chunks), 1)
        payload = complete_chunks[0]["payload"]
        choices = payload["choices"]
        self.assertGreaterEqual(len(choices), 2)


# ═══════════════════════════════════════════════════════
# 4. main.py player_action 处理测试
# ═══════════════════════════════════════════════════════

class TestMainPlayerAction(unittest.TestCase):
    """main.py 中 player_action 消息处理测试"""

    def test_choice_id_extraction(self):
        """验证 player_action 处理中提取 choice_id"""
        main_path = Path(__file__).resolve().parent.parent / "server" / "main.py"
        main_code = main_path.read_text(encoding="utf-8")
        self.assertIn("choice_id", main_code)
        self.assertIn("stream_beat", main_code)

    def test_player_action_with_choice_id(self):
        """验证带 choice_id 的 player_action 消息处理路径"""
        main_path = Path(__file__).resolve().parent.parent / "server" / "main.py"
        main_code = main_path.read_text(encoding="utf-8")
        self.assertIn('payload.get("choice_id"', main_code)
        self.assertIn("玩家选择: choice_id=", main_code)

    def test_player_action_without_text_still_works(self):
        """验证不带 text 但有 choice_id 的 player_action 不报错"""
        main_path = Path(__file__).resolve().parent.parent / "server" / "main.py"
        main_code = main_path.read_text(encoding="utf-8")
        # text 为空但 choice_id 有时也允许
        self.assertIn("if not text.strip() and not choice_id:", main_code)


# ═══════════════════════════════════════════════════════
# 5. 前端 review 测试（静态分析）
# ═══════════════════════════════════════════════════════

class TestFrontendChoices(unittest.TestCase):
    """前端 choices 相关静态检查"""

    def setUp(self):
        self.static_dir = PROJECT_ROOT / "static"
        self.js_dir = self.static_dir / "js"

    # ── 5a. choices.js import/export ──

    def test_choices_js_export_ChoicePanel(self):
        """choices.js export 了 ChoicePanel 类"""
        js = (self.js_dir / "choices.js").read_text(encoding="utf-8")
        self.assertIn("export class ChoicePanel", js)

    def test_choices_js_import_from_app(self):
        """choices.js 从 app.js import App"""
        js = (self.js_dir / "choices.js").read_text(encoding="utf-8")
        self.assertIn("import { App } from './app.js'", js)

    def test_app_js_import_ChoicePanel(self):
        """app.js import 了 ChoicePanel"""
        js = (self.js_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("import { ChoicePanel } from './choices.js'", js)

    def test_app_js_instantiates_ChoicePanel(self):
        """app.js 实例化了 ChoicePanel"""
        js = (self.js_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("new ChoicePanel()", js)
        self.assertIn("App.choices", js)

    def test_app_js_isChoosing_state(self):
        """app.js state 包含 isChoosing 字段"""
        js = (self.js_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("isChoosing", js)

    def test_app_js_choices_ready_forwarding(self):
        """app.js 中 narrative_complete 转发 choices 作为 choices_ready 事件"""
        js = (self.js_dir / "app.js").read_text(encoding="utf-8")
        self.assertIn("choices_ready", js)
        self.assertIn("narrative_complete", js)

    # ── 5b. narrative.js 无 action_hints 💡 显示行 ──

    def test_narrative_js_no_action_hints_emoji_display(self):
        """narrative.js 中 action_hints 不再作为系统消息行显示"""
        js = (self.js_dir / "narrative.js").read_text(encoding="utf-8")
        # 确认有注释说明 action_hints 不再以 💡 行显示
        self.assertIn("移除 action_hints", js)
        # 确认 oracle suggestions 的 💡 仍然存在（这是不同功能）
        self.assertIn("suggestion", js)

    # ── 5c. input.js 输入框永久禁用 ──

    def test_input_js_permanently_disabled(self):
        """input.js 中输入框永久禁用"""
        js = (self.js_dir / "input.js").read_text(encoding="utf-8")
        self.assertIn("this._inputEl.disabled = true", js)
        self.assertIn("请从上方选择", js)

    def test_input_js_choice_selected_handler(self):
        """input.js 监听 choice_selected 事件"""
        js = (self.js_dir / "input.js").read_text(encoding="utf-8")
        self.assertIn("choice_selected", js)

    def test_input_js_sends_choice_id(self):
        """input.js 中 choice_selected 发送包含 choice_id 的消息"""
        js = (self.js_dir / "input.js").read_text(encoding="utf-8")
        self.assertIn("choice_id", js)

    # ── 5d. CSS 动画 ──

    def test_css_choice_btn_selected_exists(self):
        """CSS 中 .choice-btn--selected 样式存在"""
        css = (self.static_dir / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".choice-btn--selected", css)

    def test_css_choice_highlight_fade_keyframes(self):
        """CSS 中 @keyframes choice-highlight-fade 存在"""
        css = (self.static_dir / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn("choice-highlight-fade", css)

    def test_css_choice_panel_exists(self):
        """CSS 中 .choice-panel 样式存在"""
        css = (self.static_dir / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".choice-panel", css)

    def test_css_choice_btn_exists(self):
        """CSS 中 .choice-btn 样式存在"""
        css = (self.static_dir / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".choice-btn", css)

    def test_css_choice_btn_hint_exists(self):
        """CSS 中 .choice-btn__hint 样式存在"""
        css = (self.static_dir / "css" / "main.css").read_text(encoding="utf-8")
        self.assertIn(".choice-btn__hint", css)

    # ── 5e. HTML 容器 ──

    def test_html_choice_panel_exists(self):
        """HTML 中 .choice-panel#choicePanel 容器存在"""
        html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="choicePanel"', html)
        self.assertIn("choice-panel", html)

    def test_html_input_disabled(self):
        """HTML 中输入框带有 disabled 属性"""
        html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        # 找到 <input ... disabled> 模式
        input_tag = html.split('id="playerInput"')[1].split(">")[0] if 'id="playerInput"' in html else ""
        self.assertIn("disabled", input_tag)


# ═══════════════════════════════════════════════════════
# 运行入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
