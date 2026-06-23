# -*- coding: utf-8 -*-
"""灵魂附生模块 — 统一导出"""

from .soul_state import (
    PlayerSoulProfile,
    SoulPossessionState,
    NPCCognitiveDissonance,
    ObservationEntry,
)
from .arbiter import SoulDecisionArbiter
from .inner_voice import InnerVoiceGenerator
from .dissonance import DissonanceUpdater
from .scratchpad import ScratchpadManager
from .social_graph import SocialPropagator

__all__ = [
    "PlayerSoulProfile",
    "SoulPossessionState",
    "NPCCognitiveDissonance",
    "ObservationEntry",
    "SoulDecisionArbiter",
    "InnerVoiceGenerator",
    "DissonanceUpdater",
    "ScratchpadManager",
    "SocialPropagator",
]
