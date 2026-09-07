"""回复回合追踪

用 contextvars 追踪每个回复回合的阶段（start_trace/
record_stage/finish_trace），记录到内存缓存用于诊断。
重启后缓存清空，重新积累。

数据流：
- handle 开始时 start_trace 创建追踪
- 各阶段 record_stage 记录耗时和状态
- handle 结束时 finish_trace 记录最终结果
"""

import contextvars
import threading
import time
from typing import Any
import uuid

__all__ = [
    "ReplyTurnTrace",
    "reply_turn_trace",
]


_CURRENT_TRACE_ID: contextvars.ContextVar[str] = (
    contextvars.ContextVar(
        "ai_reply_trace_id", default=""
    )
)
"""当前回合追踪ID的上下文变量"""

_MAX_STAGES = 80
"""单回合最大阶段记录数"""

_MAX_ENTRIES = 2000
"""最大追踪记录数"""

_DETAIL_LIMIT = 1000
"""详情文本长度限制"""


class ReplyTurnTrace:
    """回复回合追踪器

    用 contextvars 追踪每个回复回合的阶段，记录到内存缓存。
    所有方法支持失败安全（异常吞掉不影响主流程）。

    追踪流程：
    1. start_trace: 创建追踪ID，记录初始信息
    2. record_stage: 记录各阶段（如 load_history/generate_reply
       /review/humanize等）的耗时和状态
    3. finish_trace: 记录最终结果（success/silence/error等）
    """

    def __init__(self) -> None:
        """初始化追踪器"""
        self._entries: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def new_trace_id() -> str:
        """生成新的追踪ID

        返回:
            str: 16位十六进制追踪ID
        """
        return uuid.uuid4().hex[:16]

    @staticmethod
    def current_trace_id() -> str:
        """获取当前上下文的追踪ID

        返回:
            str: 追踪ID，无追踪时返回空串
        """
        return str(_CURRENT_TRACE_ID.get("") or "")

    @staticmethod
    def set_current_trace_id(
        trace_id: str,
    ) -> contextvars.ContextVar[str]:
        """设置当前上下文的追踪ID

        参数:
            trace_id: 追踪ID

        返回:
            Token: 用于reset的token
        """
        return _CURRENT_TRACE_ID.set(
            str(trace_id or "")
        )

    def start_trace(
        self,
        *,
        trace_id: str = "",
        session_type: str = "",
        group_id: str = "",
        user_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> str:
        """开始一个回合追踪

        参数:
            trace_id: 追踪ID，空串时自动生成
            session_type: 会话类型
            group_id: 群组ID
            user_id: 用户ID
            detail: 初始详情

        返回:
            str: 追踪ID
        """
        trace = str(trace_id or "").strip() or (
            ReplyTurnTrace.new_trace_id()
        )
        with self._lock:
            self._entries[trace] = {
                "trace_id": trace,
                "ts": time.time(),
                "session_type": str(session_type or "")[
                    :24
                ],
                "group_id": str(group_id or "")[:32],
                "user_id": str(user_id or "")[:32],
                "stages": [],
                "outcome": "",
                "diagnosis_code": "",
                "detail": dict(detail or {}),
            }
            self._prune_old_entries()
        return trace

    def record_stage(
        self,
        *,
        trace_id: str = "",
        key: str,
        label: str = "",
        status: str = "info",
        detail: Any = "",
    ) -> None:
        """记录一个阶段

        参数:
            trace_id: 追踪ID，空串用当前上下文
            key: 阶段键名
            label: 阶段标签
            status: 状态（info/warn/error）
            detail: 详情
        """
        trace = str(
            trace_id
            or ReplyTurnTrace.current_trace_id()
            or ""
        ).strip()
        if not trace:
            return
        stage = {
            "ts": time.time(),
            "key": str(key or "")[:64],
            "label": str(label or key or "")[:80],
            "status": str(status or "info")[:16],
            "detail": str(detail or "")[:_DETAIL_LIMIT],
        }
        with self._lock:
            entry = self._entries.get(trace)
            if entry is None:
                return
            stages = entry.get("stages", [])
            stages.append(stage)
            if len(stages) > _MAX_STAGES:
                stages = stages[-_MAX_STAGES:]
            entry["stages"] = stages
            entry["ts"] = time.time()

    def finish_trace(
        self,
        *,
        trace_id: str = "",
        outcome: str,
        diagnosis_code: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        """完成一个回合追踪

        参数:
            trace_id: 追踪ID，空串用当前上下文
            outcome: 结果（success/silence/error等）
            diagnosis_code: 诊断码
            detail: 结果详情
        """
        trace = str(
            trace_id
            or ReplyTurnTrace.current_trace_id()
            or ""
        ).strip()
        if not trace:
            return
        with self._lock:
            entry = self._entries.get(trace)
            if entry is None:
                return
            entry["ts"] = time.time()
            entry["outcome"] = str(outcome or "")[:32]
            entry["diagnosis_code"] = str(
                diagnosis_code or ""
            )[:64]
            if detail:
                entry["detail"].update(detail)

    def _prune_old_entries(self) -> None:
        """清理过期记录"""
        if len(self._entries) <= _MAX_ENTRIES:
            return
        sorted_items = sorted(
            self._entries.items(),
            key=lambda kv: kv[1].get("ts", 0),
            reverse=True,
        )
        self._entries = dict(
            sorted_items[:_MAX_ENTRIES]
        )


reply_turn_trace = ReplyTurnTrace()
"""回复回合追踪器单例"""
