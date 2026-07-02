"""上下文管理

提供群上下文管理、上下文压缩/控制策略、上下文清理、
会话存储与时间上下文感知。
"""

from .cleanup import ContextCleaner, context_cleaner
from .manager import ContextManager, context_manager
from .policy import (
    build_anti_loop_hint,
    compress_context_if_needed,
    estimate_chunk_tokens,
    has_silence_control_marker,
    strip_response_control_markers,
)
from .session_store import SessionStore, session_store
from .time_ctx import TimeContext, time_context

__all__ = [
    "ContextCleaner",
    "ContextManager",
    "SessionStore",
    "TimeContext",
    "build_anti_loop_hint",
    "compress_context_if_needed",
    "context_cleaner",
    "context_manager",
    "estimate_chunk_tokens",
    "has_silence_control_marker",
    "session_store",
    "strip_response_control_markers",
    "time_context",
]
