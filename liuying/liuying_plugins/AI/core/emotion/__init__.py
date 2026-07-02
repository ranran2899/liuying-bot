"""情绪系统

管理用户情绪状态与内在状态衰减。
"""

from .inner_state import clip_relation_warmth, merge_state_with_decay
from .manager import EmotionManager, emotion_manager

__all__ = [
    "EmotionManager",
    "clip_relation_warmth",
    "emotion_manager",
    "merge_state_with_decay",
]
