"""会话上下文本地存储

通过 contextvars 在单个回复回合内传递 user_id / group_id /
persona_name，供工具自行读取，避免执行器逐工具注入参数。
"""

from contextlib import contextmanager
from contextvars import ContextVar

_current_user_id: ContextVar[str] = ContextVar(
    "ai_session_user_id", default=""
)
_current_group_id: ContextVar[str] = ContextVar(
    "ai_session_group_id", default=""
)
_current_persona_name: ContextVar[str] = ContextVar(
    "ai_session_persona_name", default="default"
)


def get_current_user_id() -> str:
    """获取当前会话用户ID"""
    return _current_user_id.get()


def get_current_group_id() -> str:
    """获取当前会话群组ID"""
    return _current_group_id.get()


def get_current_persona_name() -> str:
    """获取当前会话人格名"""
    return _current_persona_name.get()


@contextmanager
def bind_session_context(
    user_id: str = "",
    group_id: str | None = None,
    persona_name: str = "default",
):
    """绑定会话上下文

    在 with 作用域内，工具可通过 get_current_* 读取会话上下文，
    退出时自动恢复原值。

    参数:
        user_id: 用户ID
        group_id: 群组ID，None视为空串
        persona_name: bot人格名
    """
    uid_token = _current_user_id.set(user_id or "")
    gid_token = _current_group_id.set(group_id or "")
    pid_token = _current_persona_name.set(persona_name or "default")
    try:
        yield
    finally:
        _current_user_id.reset(uid_token)
        _current_group_id.reset(gid_token)
        _current_persona_name.reset(pid_token)


__all__ = [
    "bind_session_context",
    "get_current_group_id",
    "get_current_persona_name",
    "get_current_user_id",
]
