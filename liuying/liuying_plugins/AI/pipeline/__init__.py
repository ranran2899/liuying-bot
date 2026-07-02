"""对话处理管线

包含拟人化发送层、贴纸选择、回复处理主流程。
"""

from .humanize import (
    compute_gap_delay,
    compute_typing_delay,
    maybe_inject_typo,
)
from .processor import ReplyProcessor, reply_processor
from .sticker import StickerManager, sticker_manager

__all__ = [
    "ReplyProcessor",
    "StickerManager",
    "compute_gap_delay",
    "compute_typing_delay",
    "maybe_inject_typo",
    "reply_processor",
    "sticker_manager",
]
