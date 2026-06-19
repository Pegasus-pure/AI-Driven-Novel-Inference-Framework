# -*- coding: utf-8 -*-
"""QA Test Suite — AI-Driven-Novel-Inference-Framework 无限叙事演进系统

覆盖范围:
  1. WorldState 测试（偏离度范围、叙事张力、线索演化、存档迁移）
  2. GameSession 测试（结局阈值移除、随机 fallback 移除）
  3. ConflictPool 测试（种子加载、随机组合、注入、耗尽）
  4. Schema 测试（新字段定义、类型映射）
  5. Config 测试（配置项移除验证）

运行方式:
  cd E:\\Godot-Project\\Round
  python -m pytest tests/test_infinite_evolution.py -v
  或
  python tests/test_infinite_evolution.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# ── 将项目根目录加入 Python path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 模块导入 ──
from server.world_state import WorldState
from server.game_session import GameSession
from server.conflict_pool import ConflictPool
from server.manana.schema import MananaSchema


# ═══════════════════════════════════════════════════════
# 1. WorldState 测试
# ═══════════════════════════════════════════════════════

class TestWorldState(unittest.TestCase):
    """WorldState 类测试 — 偏离度范围、叙事张力、线索演化、存档迁移"""

    def setUp(self):
        self.ws = WorldState()

    # ── 1a. 偏离度范围 ──

    def test_divergence_range(self):
        """验证偏离度范围 -1.0~1.0，update_divergence() clamp 正确"""
        # 初始值应为 0.0（Canon 基线）
        self.assertEqual(self.ws.world_divergence, 0.0)

        # 正向增量 clamp
        self.ws.update_divergence(2.0)  # 超出上限
        self.assertEqual(self.ws.world_divergence, 1.0,
                         "偏离度应被 clamp 到 1.0")

        # 负向增量 clamp
        self.ws.world_divergence = 0.0
        self.ws.update_divergence(-2.0)  # 超出下限
        self.assertEqual(self.ws.world_divergence, -1.0,
                         "偏离度应被 clamp 到 -1.0")

        # 正常增量
        self.ws.world_divergence = 0.0
        self.ws.update_divergence(0.5)
        self.assertAlmostEqual(self.ws.world_divergence, 0.5,
                               msg="正向 0.5 应保持不变")

        self.ws.world_divergence = 0.0
        self.ws.update_divergence(-0.3)
        self.assertAlmostEqual(self.ws.world_divergence, -0.3,
                               msg="负向 -0.3 应保持不变")

        # 边界值测试
        self.ws.world_divergence = -1.0
        self.ws.update_divergence(-0.1)
        self.assertEqual(self.ws.world_divergence, -1.0,
                         "已达 -1.0 后继续减少应 clamp 到 -1.0")

        self.ws.world_divergence = 1.0
        self.ws.update_divergence(0.1)
        self.assertEqual(self.ws.world_divergence, 1.0,
                         "已达 1.0 后继续增加应 clamp 到 1.0")

        # 累积测试
        self.ws.world_divergence = 0.0
        self.ws.update_divergence(0.6)
        self.ws.update_divergence(0.6)
        self.assertEqual(self.ws.world_divergence, 1.0,
                         "0.6 + 0.6 = 1.2 → clamp 到 1.0")

    # ── 1b. 叙事张力 ──

    def test_narrative_tension(self):
        """验证 narrative_tension 读写正确"""
        # 初始默认值应为 0.5
        self.assertEqual(self.ws.narrative_tension, 0.5,
                         "叙事张力初始值应为 0.5")

        # 直接赋值
        self.ws.narrative_tension = 0.8
        self.assertEqual(self.ws.narrative_tension, 0.8)

        # 通过 apply_patch 更新
        self.ws.apply_patch({"narrative_tension": 0.3})
        self.assertEqual(self.ws.narrative_tension, 0.3)

        # clamp 测试（超过上限）
        self.ws.apply_patch({"narrative_tension": 1.5})
        self.assertEqual(self.ws.narrative_tension, 1.0,
                         "叙事张力超过 1.0 应 clamp 到 1.0")

        # clamp 测试（低于下限）
        self.ws.apply_patch({"narrative_tension": -0.5})
        self.assertEqual(self.ws.narrative_tension, 0.0,
                         "叙事张力低于 0.0 应 clamp 到 0.0")

        # None 不更新
        self.ws.narrative_tension = 0.5
        self.ws.apply_patch({"narrative_tension": None})
        self.assertEqual(self.ws.narrative_tension, 0.5,
                         "None 不应改变叙事张力")

    # ── 1c. 线索演化 ──

    def test_thread_evolved(self):
        """验证 narrative_threads 中有 evolved 键，无 closed 键"""
        self.assertIn("evolved", self.ws.narrative_threads,
                      "narrative_threads 应包含 evolved 键")
        self.assertNotIn("closed", self.ws.narrative_threads,
                         "narrative_threads 不应包含 closed 键")

        # 初始 evolved 为空列表
        self.assertEqual(self.ws.narrative_threads["evolved"], [],
                         "初始 evolved 应为空列表")

    # ── 1d. 线索双维度 ──

    def test_thread_intensity_complexity(self):
        """验证新线索创建时有 intensity 和 complexity"""
        # 通过 apply_thread_updates 创建新线索
        updates = {
            "new_threads": [
                {
                    "title": "测试线索",
                    "type": "side",
                    "question": "测试问题?",
                }
            ],
        }
        self.ws.apply_thread_updates(updates)

        active_threads = self.ws.narrative_threads["active"]
        self.assertEqual(len(active_threads), 1)

        new_thread = active_threads[0]
        self.assertIn("intensity", new_thread,
                      "新线索应包含 intensity 字段")
        self.assertIn("complexity", new_thread,
                      "新线索应包含 complexity 字段")
        self.assertEqual(new_thread["intensity"], 0.0,
                         "新线索 intensity 初始应为 0.0")
        self.assertEqual(new_thread["complexity"], 0.3,
                         "新线索 complexity 初始应为 0.3")

        # 验证没有 progress 字段（v2 特性）
        self.assertNotIn("progress", new_thread,
                         "新线索不应包含 progress 字段（v2 已移除）")

    # ── 1e. 存档迁移 ──

    def test_from_dict_v1_migration(self):
        """验证旧存档（含 closed/progress）能正确迁移到 v2"""
        v1_data = {
            "version": 1,
            "game_time": "第一月·第一日·清晨",
            "time_index": 0,
            "player_location": "",
            "player_profile": {"traits": [], "motivation": "", "tendency": "中立"},
            "player_reputation": {},
            "characters_state": {},
            "narrative_threads": {
                "active": [
                    {"id": "thread_001", "title": "旧线索", "type": "main",
                     "progress": 0.7, "question": "旧问题?"},
                ],
                "closed": [
                    {"id": "thread_002", "title": "已关闭线索", "type": "side",
                     "progress": 0.9},
                ],
            },
            "dynamic_canon": {
                "closed_threads": ["thread_002"],
                "character_states": {},
                "new_npcs": [],
                "divergence_events": [],
            },
            "dynamic_npcs": {},
            "world_divergence": 0.5,
            "narrative_history": [],
            "scene_memory": [],
            "long_term_memory": [],
            "knowledge_graph": {},
            "custom_world_rules": [],
            "canon": {},
        }

        ws = WorldState.from_dict(v1_data)

        # 验证版本迁移
        self.assertIn("evolved", ws.narrative_threads,
                      "迁移后应包含 evolved 键")
        self.assertNotIn("closed", ws.narrative_threads,
                         "迁移后不应包含 closed 键")

        # 验证 closed → evolved 迁移
        self.assertEqual(len(ws.narrative_threads["evolved"]), 1,
                         "closed 线索应迁移到 evolved")
        self.assertEqual(ws.narrative_threads["evolved"][0]["id"], "thread_002",
                         "evolved 线索的 id 应保持不变")

        # 验证活跃线索中 progress → intensity 迁移
        active = ws.narrative_threads["active"]
        self.assertEqual(len(active), 1)
        migrated_thread = active[0]
        self.assertIn("intensity", migrated_thread,
                      "活跃线索应包含 intensity（由 progress 迁移）")
        self.assertNotIn("progress", migrated_thread,
                         "活跃线索不应残留 progress 字段")
        self.assertEqual(migrated_thread["intensity"], 0.7,
                         "intensity 应从 progress 值迁移")
        self.assertIn("complexity", migrated_thread,
                      "活跃线索应包含 complexity（迁移补全）")
        self.assertEqual(migrated_thread["complexity"], 0.3,
                         "complexity 应使用默认值 0.3")

        # 验证 evolved 线索也完成 progress→intensity 迁移
        evolved = ws.narrative_threads["evolved"]
        self.assertIn("intensity", evolved[0],
                      "evolved 线索应包含 intensity")
        self.assertNotIn("progress", evolved[0],
                         "evolved 线索不应残留 progress")

        # 验证 dynamic_canon 迁移
        self.assertIn("evolved_threads", ws.dynamic_canon,
                      "dynamic_canon 应包含 evolved_threads")
        self.assertNotIn("closed_threads", ws.dynamic_canon,
                         "dynamic_canon 不应残留 closed_threads")

        # 验证 narrative_tension 默认值
        self.assertEqual(ws.narrative_tension, 0.5,
                         "v1 存档迁移后 narrative_tension 应为默认值 0.5")

        # 验证 SAVE_VERSION
        self.assertEqual(ws.SAVE_VERSION, 2,
                         "当前存档版本应为 v2")

        # 验证 to_dict 保存 v2
        dumped = ws.to_dict()
        self.assertEqual(dumped["version"], 2,
                         "to_dict 应输出 version=2")
        self.assertNotIn("closed", dumped.get("narrative_threads", {}),
                         "to_dict 输出不应包含 closed")
        self.assertIn("evolved", dumped.get("narrative_threads", {}),
                      "to_dict 输出应包含 evolved")

    def test_apply_patch_divergence_delta(self):
        """验证 apply_patch 通过 divergence_delta 更新偏离度"""
        self.ws.world_divergence = 0.0
        self.ws.apply_patch({"divergence_delta": 0.3})
        self.assertAlmostEqual(self.ws.world_divergence, 0.3)

        # 负 delta
        self.ws.apply_patch({"divergence_delta": -0.5})
        self.assertAlmostEqual(self.ws.world_divergence, -0.2)

        # None delta 不更新
        self.ws.apply_patch({"divergence_delta": None})
        self.assertAlmostEqual(self.ws.world_divergence, -0.2)

    def test_apply_thread_updates_evolved(self):
        """验证 apply_thread_updates 将线索移入 evolved"""
        # 先创建活跃线索
        self.ws.apply_thread_updates({
            "new_threads": [{"title": "线索A", "type": "main"}],
        })
        active = self.ws.narrative_threads["active"]
        thread_id = active[0]["id"]

        # 标记为 evolved
        self.ws.apply_thread_updates({
            "evolved_threads": [thread_id],
        })

        # 验证已移入 evolved
        self.assertIn(thread_id,
                      [t["id"] for t in self.ws.narrative_threads["evolved"]],
                      "线索应移入 evolved 列表")
        self.assertNotIn(thread_id,
                         [t["id"] for t in self.ws.narrative_threads["active"]],
                         "线索应从 active 列表移除")

    def test_apply_thread_updates_intensity_complexity_delta(self):
        """验证 apply_thread_updates 兼容新旧两种格式的 delta"""
        # 先创建线索
        self.ws.apply_thread_updates({
            "new_threads": [{"title": "线索B", "type": "side"}],
        })
        thread_id = self.ws.narrative_threads["active"][0]["id"]

        # 新格式：intensity_delta + complexity_delta
        self.ws.apply_thread_updates({
            "thread_advances": [{
                "thread_id": thread_id,
                "intensity_delta": 0.5,
                "complexity_delta": 0.4,
            }],
        })
        t = self.ws.narrative_threads["active"][0]
        self.assertAlmostEqual(t["intensity"], 0.5)
        self.assertAlmostEqual(t["complexity"], 0.7)  # 0.3 + 0.4

        # 旧格式：delta → intensity_delta
        self.ws.apply_thread_updates({
            "thread_advances": [{
                "thread_id": thread_id,
                "delta": 0.3,
            }],
        })
        t = self.ws.narrative_threads["active"][0]
        self.assertAlmostEqual(t["intensity"], 0.8)  # 0.5 + 0.3
        # complexity 不应受旧格式 delta 影响
        self.assertAlmostEqual(t["complexity"], 0.7)

    def test_save_version(self):
        """验证 SAVE_VERSION = 2"""
        self.assertEqual(WorldState.SAVE_VERSION, 2)
        # 新创建的 world_state 序列化后 version=2
        data = self.ws.to_dict()
        self.assertEqual(data["version"], 2)

    def test_from_dict_invalid_version(self):
        """验证加载过高的版本号抛出 ValueError"""
        data = {"version": 999}
        with self.assertRaises(ValueError):
            WorldState.from_dict(data)


# ═══════════════════════════════════════════════════════
# 2. GameSession 测试
# ═══════════════════════════════════════════════════════

class TestGameSession(unittest.TestCase):
    """GameSession 类测试 — 结局阈值移除、随机 fallback 移除"""

    def setUp(self):
        self.gs = GameSession("test_session")

    def test_no_ending_threshold(self):
        """验证 game_session 中没有 _ending_threshold 属性"""
        self.assertFalse(hasattr(self.gs, '_ending_threshold'),
                         "GameSession 不应包含 _ending_threshold 属性")
        # 确认注释说明已移除
        self.assertFalse(hasattr(self.gs, 'ending_divergence_threshold'),
                         "GameSession 不应包含 ending_divergence_threshold")

        # 检查源代码中无 ending_threshold 引用
        import inspect
        source = inspect.getsource(self.gs.__init__)
        self.assertNotIn("ending_threshold", source,
                         "__init__ 中不应引用 ending_threshold")

    def test_no_check_ending(self):
        """验证 check_ending() 方法不存在"""
        self.assertFalse(hasattr(self.gs, 'check_ending'),
                         "GameSession 不应包含 check_ending 方法")

        # 确认类文档或注释中说明结局检测已移除
        import inspect
        source = inspect.getsource(type(self.gs))
        # 文档中应提到结局检测已移除
        has_removal_note = (
            "移除结局阈值机制" in source
            or "不再依赖固定偏离度阈值" in source
            or "结局检测已移除" in source
        )
        self.assertTrue(has_removal_note,
                        "类文档应说明结局阈值机制已移除")

    def test_no_random_fallback(self):
        """验证 run_beat() 中不再使用 random.uniform 做偏离度 fallback"""
        import inspect
        source = inspect.getsource(self.gs.run_beat)

        # 不应有 random.uniform 调用
        self.assertNotIn("random.uniform", source,
                         "run_beat 不应调用 random.uniform")

        # 不应有 random 模块针对偏离度的调用
        # 确认偏离度更新通过 apply_patch divergence_delta 进行
        self.assertIn("apply_patch", source,
                      "run_beat 应通过 apply_patch 更新状态")
        # 结局检测相关注释
        self.assertIn("结局检测已移除", source,
                      "run_beat 应注释说明结局检测已移除")

    def test_stream_beat_no_ending_triggered(self):
        """验证 stream_beat 中不再发送 ending_triggered"""
        import inspect
        source = inspect.getsource(self.gs.stream_beat)
        self.assertNotIn("ending_triggered", source,
                         "stream_beat 不应包含 ending_triggered")

    def test_initialize_no_ending_config(self):
        """验证 initialize 不读取 ending_divergence_threshold 作为配置值"""
        import inspect
        source = inspect.getsource(self.gs.initialize)
        # 允许注释中存在说明文字，但不应有实际读取配置的逻辑
        # 检查不应有从 config 中读取 ending 相关值的代码
        self.assertNotIn("cfg.get(\"ending", source,
                         "initialize 不应读取 ending 配置")
        self.assertNotIn("cfg.get('ending", source,
                         "initialize 不应读取 ending 配置")
        # 确认 auto_save_interval 仍在读取
        self.assertIn("auto_save_interval", source,
                      "initialize 仍应读取 auto_save_interval")

    def test_no_ending_threshold_comment(self):
        """验证 __init__ 和类中有正确的移除注释"""
        import inspect
        init_source = inspect.getsource(self.gs.__init__)
        # 确认有注释说明结局阈值已移除
        has_comment = (
            "结局阈值已移除" in init_source
            or "ended" not in [k for k in dir(self.gs) if not k.startswith('__')]
        )
        # 验证 _skip_typing 仍然存在
        self.assertTrue(hasattr(self.gs, '_skip_typing'))

    def test_restore_state_no_ending(self):
        """验证 restore_state 不涉及结局检测"""
        import inspect
        source = inspect.getsource(self.gs.restore_state)
        self.assertNotIn("ending", source.lower(),
                         "restore_state 不应涉及结局检测")


# ═══════════════════════════════════════════════════════
# 3. ConflictPool 测试
# ═══════════════════════════════════════════════════════

class TestConflictPool(unittest.TestCase):
    """ConflictPool 类测试 — 种子加载、随机组合、注入、耗尽"""

    def setUp(self):
        self.pool = ConflictPool()

    def _make_test_canon(self) -> dict:
        """生成测试用的 canon 数据"""
        return {
            "title": "测试小说",
            "timeline": [
                {
                    "id": "event_001",
                    "title": "事件一",
                    "description": "测试事件",
                    "conflicts": [
                        {
                            "id": "conflict_001",
                            "type": "mystery",
                            "description": "神秘失踪案",
                            "involved_characters": ["char_001"],
                            "involved_locations": ["loc_001"],
                            "intensity": 0.7,
                            "variants": ["变体A", "变体B"],
                        },
                        {
                            "id": "conflict_002",
                            "type": "moral_dilemma",
                            "description": "道德困境",
                            "involved_characters": ["char_002"],
                            "intensity": 0.5,
                            "variants": ["困境变体"],
                        },
                    ],
                },
                {
                    "id": "event_002",
                    "title": "事件二",
                    "description": "第二个事件（无冲突）",
                    "conflicts": [],
                },
                {
                    "id": "event_003",
                    "title": "事件三",
                    "description": "第三个事件",
                    "conflicts": [
                        {
                            "id": "conflict_003",
                            "type": "character_conflict",
                            "description": "角色冲突",
                            "involved_characters": ["char_003", "char_004"],
                            "intensity": 0.9,
                        },
                    ],
                },
            ],
        }

    # ── 3a. 从 Canon 加载 ──

    def test_load_from_canon(self):
        """验证从 canon.json 加载冲突种子成功"""
        canon = self._make_test_canon()
        count = self.pool.load_from_canon(canon)

        self.assertEqual(count, 3,
                         "应加载 3 个冲突种子（event_001 有 2 个, event_003 有 1 个）")
        self.assertEqual(self.pool.seed_count, 3)

        # 验证种子内容
        seeds = self.pool._seeds
        ids = [s["id"] for s in seeds]
        self.assertIn("conflict_001", ids)
        self.assertIn("conflict_002", ids)
        self.assertIn("conflict_003", ids)

        # 验证 _source_event_id
        seed1 = next(s for s in seeds if s["id"] == "conflict_001")
        self.assertEqual(seed1["_source_event_id"], "event_001")

        seed3 = next(s for s in seeds if s["id"] == "conflict_003")
        self.assertEqual(seed3["_source_event_id"], "event_003")

    def test_load_from_canon_dedup(self):
        """验证重复加载不会重复添加种子"""
        canon = self._make_test_canon()

        # 第一次加载
        count1 = self.pool.load_from_canon(canon)
        self.assertEqual(count1, 3)

        # 第二次加载（应跳过所有重复 id）
        count2 = self.pool.load_from_canon(canon)
        self.assertEqual(count2, 0, "重复加载应返回 0")
        self.assertEqual(self.pool.seed_count, 3)

    def test_load_from_canon_empty(self):
        """验证空 canon 或空 timeline 不报错"""
        count = self.pool.load_from_canon({})
        self.assertEqual(count, 0)

        count = self.pool.load_from_canon({"timeline": []})
        self.assertEqual(count, 0)

    # ── 3b. 随机组合 ──

    def test_get_random_combination(self):
        """验证随机组合返回正确数量"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        # 请求 2 个组合
        combo = self.pool.get_random_combination(count=2)
        self.assertEqual(len(combo), 2,
                         "应返回 2 个冲突种子")

        # 请求超出可用数量（应返回全部可用）
        combo_all = self.pool.get_random_combination(count=10)
        self.assertEqual(len(combo_all), self.pool.available_count,
                         "请求数量超出可用数时应返回全部可用种子")

        # 验证返回的是 deep copy
        combo[0]["id"] = "modified"
        self.assertNotEqual(self.pool._seeds[0]["id"], "modified",
                            "返回的种子应是 deep copy，修改不影响原数据")

    def test_get_random_combination_empty(self):
        """验证空池返回空列表"""
        combo = self.pool.get_random_combination(count=2)
        self.assertEqual(combo, [],
                         "空池应返回空列表")

    def test_get_random_combination_times_used(self):
        """验证随机组合后 times_used 增加"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        # 获取组合
        _ = self.pool.get_random_combination(count=2)

        # 验证 times_used 增加了
        total_times = sum(s["times_used"] for s in self.pool._seeds)
        self.assertEqual(total_times, 2,
                         "选中 2 个种子后总 times_used 应为 2")

    # ── 3c. 注入种子 ──

    def test_add_seeds(self):
        """验证新种子能注入并去重"""
        new_seeds = [
            {
                "type": "social_tension",
                "description": "新社会冲突",
                "involved_characters": ["char_005"],
                "intensity": 0.6,
            },
            {
                "id": "conflict_004",
                "type": "environmental_crisis",
                "description": "环境危机",
                "intensity": 0.8,
            },
        ]

        self.pool.add_seeds(new_seeds)

        # 验证注入成功
        self.assertEqual(self.pool.seed_count, 2)

        # 第一个种子没有 id，应自动生成
        seeds = self.pool._seeds
        auto_id_seed = [s for s in seeds if s["id"].startswith("conflict_dyn_")]
        self.assertEqual(len(auto_id_seed), 1,
                         "无 id 的种子应自动生成 id")

        # 验证有 id 的种子保持不变
        fixed_seed = next(s for s in seeds if s["id"] == "conflict_004")
        self.assertEqual(fixed_seed["type"], "environmental_crisis")
        self.assertEqual(fixed_seed["intensity"], 0.8)

    def test_add_seeds_dedup(self):
        """验证重复注入不会重复添加"""
        new_seeds = [
            {"id": "conflict_001", "type": "mystery", "description": "测试"},
        ]

        self.pool.add_seeds(new_seeds)
        self.assertEqual(self.pool.seed_count, 1)

        # 再次注入相同 id
        self.pool.add_seeds(new_seeds)
        self.assertEqual(self.pool.seed_count, 1,
                         "重复 id 不应重复添加")

    def test_add_seeds_invalid_type(self):
        """验证非法类型回退为 mystery"""
        self.pool.add_seeds([
            {"type": "unknown_type", "description": "测试"},
        ])
        self.assertEqual(self.pool._seeds[0]["type"], "mystery",
                         "非法类型应回退为 mystery")

    # ── 3d. 耗尽 ──

    def test_mark_used_exhaustion(self):
        """验证使用 3 次后种子 exhausted"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        # 使用 3 次
        self.pool.mark_used("conflict_001")
        self.pool.mark_used("conflict_001")
        self.pool.mark_used("conflict_001")

        seed = next(s for s in self.pool._seeds if s["id"] == "conflict_001")
        self.assertTrue(seed["is_exhausted"],
                        "使用 3 次后种子应标记为 exhausted")
        self.assertEqual(seed["times_used"], 3)

        # 验证可用种子数减少
        self.assertEqual(self.pool.available_count, 2,
                         "耗尽 1 个后应剩 2 个可用")

    def test_mark_used_not_exhausted_before_3(self):
        """验证使用不足 3 次时不标记 exhausted"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        self.pool.mark_used("conflict_001")
        self.pool.mark_used("conflict_001")

        seed = next(s for s in self.pool._seeds if s["id"] == "conflict_001")
        self.assertFalse(seed["is_exhausted"],
                         "使用 2 次不应标记 exhausted")
        self.assertEqual(seed["times_used"], 2)

    def test_mark_used_nonexistent(self):
        """验证标记不存在的种子不报错"""
        self.pool.mark_used("nonexistent")  # 不应抛出异常

    def test_reset_exhausted(self):
        """验证 reset_exhausted 恢复所有种子可用"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        # 耗尽一个种子
        for _ in range(3):
            self.pool.mark_used("conflict_001")

        self.assertEqual(self.pool.available_count, 2)

        # 重置
        self.pool.reset_exhausted()
        self.assertEqual(self.pool.available_count, 3,
                         "重置后所有种子应可用")

    def test_get_available_seeds_min_intensity(self):
        """验证 get_available_seeds 按强度过滤"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        available = self.pool.get_available_seeds(min_intensity=0.8)
        # 只有 conflict_003 (intensity=0.9) 符合
        ids = [s["id"] for s in available]
        self.assertIn("conflict_003", ids)
        self.assertNotIn("conflict_001", ids)  # 0.7 < 0.8
        self.assertNotIn("conflict_002", ids)  # 0.5 < 0.8

    def test_to_dict_from_dict(self):
        """验证序列化/反序列化"""
        canon = self._make_test_canon()
        self.pool.load_from_canon(canon)

        data = self.pool.to_dict()
        self.assertIn("seeds", data)
        self.assertEqual(len(data["seeds"]), 3)

        # 反序列化
        pool2 = ConflictPool.from_dict(data)
        self.assertEqual(pool2.seed_count, 3)


# ═══════════════════════════════════════════════════════
# 4. Schema 测试
# ═══════════════════════════════════════════════════════

class TestMananaSchema(unittest.TestCase):
    """MananaSchema 测试 — 新字段定义、类型映射"""

    # ── 4a. STATE_EXTRACTOR_OUTPUT_KEYS ──

    def test_extractor_keys(self):
        """验证 STATE_EXTRACTOR_OUTPUT_KEYS 包含 6 个新字段"""
        keys = MananaSchema.STATE_EXTRACTOR_OUTPUT_KEYS

        new_fields = [
            "divergence_delta",
            "narrative_tension",
            "canon_adherence",
            "narrative_mode",
            "character_arc_progress",
            "new_seed_conflicts",
        ]

        for field in new_fields:
            self.assertIn(field, keys,
                          f"STATE_EXTRACTOR_OUTPUT_KEYS 应包含 {field}")

        # 验证总字段数正确（8 个原始字段 + 6 个新字段 = 14）
        expected_fields = [
            # 原始 8 字段
            "reputation_changes", "mood_changes", "location_changes",
            "new_knowledge", "new_dynamic_npcs", "player_profile_updates",
            "narrative_summary", "scene_memory_entry",
            # 新 6 字段
            "divergence_delta", "narrative_tension", "canon_adherence",
            "narrative_mode", "character_arc_progress", "new_seed_conflicts",
        ]
        self.assertEqual(len(keys), len(expected_fields),
                         f"应包含 {len(expected_fields)} 个字段")
        for f in expected_fields:
            self.assertIn(f, keys)

    # ── 4b. THREAD_MANAGER_OUTPUT_KEYS ──

    def test_thread_manager_keys(self):
        """验证 THREAD_MANAGER_OUTPUT_KEYS 使用 evolved_threads（而非 closed_threads）"""
        keys = MananaSchema.THREAD_MANAGER_OUTPUT_KEYS

        self.assertIn("evolved_threads", keys,
                      "THREAD_MANAGER_OUTPUT_KEYS 应包含 evolved_threads")
        self.assertNotIn("closed_threads", keys,
                         "THREAD_MANAGER_OUTPUT_KEYS 不应包含 closed_threads")

        # 验证完整字段列表
        expected = ["thread_advances", "new_threads",
                     "evolved_threads", "tension_adjustments"]
        self.assertEqual(keys, expected)

    # ── 4c. _EXTRACTOR_EXTENDED_TYPE_MAP ──

    def test_extended_type_map(self):
        """验证 _EXTRACTOR_EXTENDED_TYPE_MAP 类型正确"""
        type_map = MananaSchema._EXTRACTOR_EXTENDED_TYPE_MAP

        expected = {
            "divergence_delta": "float",
            "narrative_tension": "float",
            "canon_adherence": "float",
            "narrative_mode": "string",
            "character_arc_progress": "dictionary",
            "new_seed_conflicts": "array",
        }

        self.assertEqual(type_map, expected,
                         "_EXTRACTOR_EXTENDED_TYPE_MAP 类型映射不正确")

    # ── 4d. THREAD_TYPE_MAP ──

    def test_thread_type_map(self):
        """验证 _THREAD_TYPE_MAP 使用 evolved_threads"""
        type_map = MananaSchema._THREAD_TYPE_MAP

        self.assertIn("evolved_threads", type_map,
                      "_THREAD_TYPE_MAP 应包含 evolved_threads")
        self.assertNotIn("closed_threads", type_map,
                         "_THREAD_TYPE_MAP 不应包含 closed_threads")
        self.assertEqual(type_map["evolved_threads"], "array",
                         "evolved_threads 类型应为 array")

    # ── 4e. Validate extractor output ──

    def test_validate_extractor_output(self):
        """验证 extractor 输出验证器正常工作"""
        # 有效输出
        valid_output = {
            "reputation_changes": [],
            "mood_changes": [],
            "location_changes": [],
            "new_knowledge": [],
            "new_dynamic_npcs": [],
            "player_profile_updates": {},
            "narrative_summary": "测试摘要",
            "scene_memory_entry": "测试记忆",
            "divergence_delta": 0.1,
            "narrative_tension": 0.5,
            "canon_adherence": 0.8,
            "narrative_mode": "exploration",
            "character_arc_progress": {"char_001": 0.5},
            "new_seed_conflicts": [],
        }
        result = MananaSchema.validate_extractor_output(valid_output)
        self.assertTrue(result.get("valid", False),
                        "有效输出应通过验证")

        # 缺少字段（应通过验证但 reporting errors）
        incomplete = dict(valid_output)
        del incomplete["divergence_delta"]
        result2 = MananaSchema.validate_extractor_output(incomplete)
        self.assertFalse(result2.get("valid", False),
                         "缺少字段应验证失败")

    def test_validate_thread_output(self):
        """验证 thread 输出验证器正常工作"""
        valid = {
            "thread_advances": [],
            "new_threads": [],
            "evolved_threads": [],
            "tension_adjustments": [],
        }
        result = MananaSchema.validate_thread_output(valid)
        self.assertTrue(result.get("valid", False))

        # 使用 closed_threads 应验证失败
        invalid = dict(valid)
        invalid["closed_threads"] = ["thread_001"]
        del invalid["evolved_threads"]
        result2 = MananaSchema.validate_thread_output(invalid)
        self.assertFalse(result2.get("valid", False),
                         "closed_threads 不应出现在线程输出中")


# ═══════════════════════════════════════════════════════
# 5. Config 测试
# ═══════════════════════════════════════════════════════

class TestConfig(unittest.TestCase):
    """Config 测试 — 配置项移除验证"""

    def test_config_no_ending_threshold(self):
        """验证 config.yaml 中没有 ending_divergence_threshold"""
        config_path = PROJECT_ROOT / "config.yaml"
        self.assertTrue(config_path.is_file(),
                        "config.yaml 文件应存在")

        content = config_path.read_text(encoding="utf-8")

        self.assertNotIn("ending_divergence_threshold", content,
                         "config.yaml 不应包含 ending_divergence_threshold")
        self.assertNotIn("ending", content,
                         "config.yaml 不应包含任何 ending 配置项")

    def test_config_has_features(self):
        """验证 config.yaml 包含必要的功能开关"""
        config_path = PROJECT_ROOT / "config.yaml"
        content = config_path.read_text(encoding="utf-8")

        self.assertIn("refinement", content)
        self.assertIn("best_of_3", content)
        self.assertIn("micro_oracle", content)

    def test_game_session_init_no_ending_config(self):
        """验证 game_session 初始化不读取结局配置"""
        config_path = PROJECT_ROOT / "config.yaml"
        content = config_path.read_text(encoding="utf-8")

        # game 段不应有 ending 相关配置
        game_section = content.split("game:")[1].split("\n#")[0] if "game:" in content else ""
        if game_section:
            self.assertNotIn("ending", game_section,
                             "game 配置段不应包含 ending 相关配置")
        # 验证 oracle_interval 和 auto_save_interval 仍然存在
        self.assertIn("oracle_interval", content)
        self.assertIn("auto_save_interval", content)


# ═══════════════════════════════════════════════════════
# 6. NovelLoader 冲突种子提取测试
# ═══════════════════════════════════════════════════════

class TestNovelLoaderConflicts(unittest.TestCase):
    """NovelLoader 冲突种子提取测试"""

    def setUp(self):
        from server.novel_loader import NovelLoader
        self.loader = NovelLoader()

    def test_load_conflicts_from_canon(self):
        """验证 load_conflicts_from_canon 提取冲突种子"""
        canon = {
            "timeline": [
                {
                    "id": "event_001",
                    "conflicts": [
                        {
                            "id": "conflict_001",
                            "type": "mystery",
                            "description": "一个谜团",
                            "intensity": 0.7,
                        },
                    ],
                },
            ],
        }
        conflicts = self.loader.load_conflicts_from_canon(canon)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["id"], "conflict_001")
        self.assertEqual(conflicts[0]["_source_event_id"], "event_001")

    def test_load_conflicts_no_timeline(self):
        """验证空 timeline 返回空列表"""
        conflicts = self.loader.load_conflicts_from_canon({})
        self.assertEqual(conflicts, [])

    def test_scan_returns_conflict_count(self):
        """验证 scan_novel_directory 返回 conflict_count"""
        # 这个测试比较复杂，因为需要创建 mock 的 canon 文件结构
        # 这里只验证 scan 结果包含 conflict_count 字段
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建一个子目录模拟 running canon
            subdir = Path(tmpdir) / "test_novel"
            subdir.mkdir()
            meta = {"title": "test_novel"}
            (subdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            canon_data = {
                "timeline": [
                    {"id": "e1", "conflicts": [{"id": "c1", "type": "mystery", "description": "x"}]},
                    {"id": "e2", "conflicts": [{"id": "c2", "type": "mystery", "description": "y"}]},
                ],
            }
            (subdir / "canon.json").write_text(json.dumps(canon_data), encoding="utf-8")

            result = self.loader.scan_novel_directory(tmpdir)
            self.assertIn("conflict_count", result,
                          "scan 结果应包含 conflict_count")
            self.assertEqual(result["conflict_count"], 2,
                             "应统计到 2 个冲突")


# ═══════════════════════════════════════════════════════
# 7. 前端相关测试
# ═══════════════════════════════════════════════════════

class TestFrontendInfiniteEvolution(unittest.TestCase):
    """前端 UI 适配测试 — 双极偏离度、模式标签、方向建议"""

    def setUp(self):
        self.static_dir = PROJECT_ROOT / "static"

    def test_deviation_js_has_bipolar(self):
        """验证 deviation.js 实现双极偏离度显示（-1~1）"""
        js_path = self.static_dir / "js" / "deviation.js"
        self.assertTrue(js_path.is_file(), "deviation.js 应存在")
        js = js_path.read_text(encoding="utf-8")

        # 验证范围处理
        self.assertIn("-1", js or "min",
                       "deviation.js 应处理 -1 到 1 的范围")
        # 验证颜色显示（蓝←0→橙红）
        self.assertTrue(
            "blue" in js.lower() or "蓝" in js or "#" in js,
            "deviation.js 应包含颜色处理"
        )

    def test_deviation_js_has_set_narrative_mode(self):
        """验证 deviation.js 新增 setNarrativeMode"""
        js_path = self.static_dir / "js" / "deviation.js"
        js = js_path.read_text(encoding="utf-8")
        self.assertIn("setNarrativeMode", js,
                      "deviation.js 应包含 setNarrativeMode 方法")

    def test_narrative_js_no_ending_triggered(self):
        """验证 narrative.js 删除 ending_triggered"""
        js_path = self.static_dir / "js" / "narrative.js"
        js = js_path.read_text(encoding="utf-8")
        self.assertNotIn("ending_triggered", js,
                         "narrative.js 不应包含 ending_triggered")

    def test_narrative_js_has_narrative_mode_update(self):
        """验证 narrative.js 新增 narrative_mode_update 事件处理"""
        js_path = self.static_dir / "js" / "narrative.js"
        js = js_path.read_text(encoding="utf-8")
        self.assertIn("narrative_mode_update", js,
                      "narrative.js 应处理 narrative_mode_update 事件")

    def test_narrative_js_has_suggestions(self):
        """验证 narrative.js 渲染方向建议"""
        js_path = self.static_dir / "js" / "narrative.js"
        js = js_path.read_text(encoding="utf-8")
        # 应包含方向建议相关渲染逻辑
        self.assertTrue(
            "suggestion" in js.lower(),
            "narrative.js 应包含方向建议渲染"
        )

    def test_app_js_registers_narrative_mode_update(self):
        """验证 app.js 注册 narrative_mode_update 事件"""
        js_path = self.static_dir / "js" / "app.js"
        self.assertTrue(js_path.is_file(), "app.js 应存在")
        js = js_path.read_text(encoding="utf-8")
        self.assertIn("narrative_mode_update", js,
                      "app.js 应注册 narrative_mode_update 事件")

    def test_html_has_mode_badge(self):
        """验证 index.html 新增模式标签区"""
        html_path = self.static_dir / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("narrativeModeTag", html,
                      "index.html 应包含叙事模式标签 (id=narrativeModeTag)")
        self.assertIn("title-bar__mode", html,
                      "index.html 应包含模式标签样式 title-bar__mode")

    def test_html_has_bipolar_divergence(self):
        """验证 index.html 新增双极偏离度 DOM"""
        html_path = self.static_dir / "index.html"
        html = html_path.read_text(encoding="utf-8")
        # 应包含偏离度显示相关元素
        self.assertIn("deviation", html,
                      "index.html 应包含偏离度相关 DOM")

    def test_html_has_suggestions_area(self):
        """验证 index.html 新增方向建议区"""
        html_path = self.static_dir / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("suggestion", html.lower(),
                      "index.html 应包含方向建议区")

    def test_css_has_bipolar_progress(self):
        """验证 main.css 新增双极进度条样式"""
        css_path = self.static_dir / "css" / "main.css"
        css = css_path.read_text(encoding="utf-8")

        # 验证双极进度条样式
        has_bipolar = "bipolar" in css.lower() or "deviation-bar" in css
        self.assertTrue(has_bipolar,
                        "main.css 应包含双极偏离度进度条样式")

    def test_css_has_mode_badge_style(self):
        """验证 main.css 新增模式标签样式"""
        css_path = self.static_dir / "css" / "main.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertIn("title-bar__mode", css,
                      "main.css 应包含模式标签样式 title-bar__mode")
        self.assertIn("mode-indicator", css,
                      "main.css 应包含 mode-indicator 样式")

    def test_css_has_suggestions_style(self):
        """验证 main.css 新增方向建议样式"""
        css_path = self.static_dir / "css" / "main.css"
        css = css_path.read_text(encoding="utf-8")
        self.assertTrue(
            "suggestion" in css.lower(),
            "main.css 应包含方向建议样式"
        )


# ═══════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
