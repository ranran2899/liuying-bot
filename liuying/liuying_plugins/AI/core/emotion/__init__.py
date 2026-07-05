"""情绪系统

管理用户情绪状态与内在状态衰减。
"""

from .inner_state import InnerStateHelper
from .manager import EmotionManager, emotion_manager

__all__ = [
    "EmotionManager",
    "InnerStateHelper",
    "emotion_manager",
]
