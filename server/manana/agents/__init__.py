"""MaNA v4 Agent 模块 — 单文件结构。

每个 Agent 独立一个文件，从 `__init__.py` 统一重新导出。
外部代码仅需 `from .agents import 类名`，对文件结构无感知。
"""

from .scene_director import SceneDirector
from .scene_composer import SceneComposer
from .reflection_oracle import ReflectionOracle

from .motivation_engine import MotivationEngine
from .dialogue_weaver import DialogueWeaver
from .consistency_auditor import ConsistencyAuditor
from .thread_manager import ThreadManager
from .plan_synthesizer_agent import PlanSynthesizerAgent
from .continuity_checker import ContinuityChecker

from .action_director import ActionDirector
from .state_extractor import StateExtractor
from .plan_scorer_agent import PlanScorerAgent
from .role_reflector import RoleReflector
from .character_manager import CharacterManager
from .location_manager import LocationManager
from .micro_oracle_agent import MicroOracleAgent
from .soul_choice_generator import SoulChoiceGenerator

__all__ = [
    "SceneDirector", "SceneComposer", "ReflectionOracle",
    "MotivationEngine", "DialogueWeaver", "ConsistencyAuditor",
    "ThreadManager", "PlanSynthesizerAgent", "ContinuityChecker",
    "ActionDirector", "StateExtractor", "PlanScorerAgent",
    "RoleReflector", "CharacterManager", "LocationManager", "MicroOracleAgent",
    "SoulChoiceGenerator",
]
