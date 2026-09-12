"""会话上下文存储

通过 contextvars 在单个回复回合内传递会话信息，供 Agent 工具读取。

会话来源：
- matcher 入口由 nonebot_plugin_uninfo 注入真实 Session（Uninfo 依赖注入），
  经 bind_session 绑定完整 Session 对象；
- 定时任务/主动行为等无事件上下文的后台路径，由 bind_session_context
  兜底写入 user_id/group_id/persona_name 字符串。
"""

from contextlib import contextmanager
from contextvars import ContextVar

from nonebot_plugin_uninfo import Session

_session_ctx: ContextVar[Session | None] = ContextVar("ai_session", default=None)
"""当前会话（uninfo Session 对象，无会话时为 None）"""

_user_id_ctx: ContextVar[str] = ContextVar("ai_session_user_id", default="")
"""兜底用户ID（无 Session 时使用）"""

_group_id_ctx: ContextVar[str] = ContextVar("ai_session_group_id", default="")
"""兜底群组ID（无 Session 时使用）"""

_persona_ctx: ContextVar[str] = ContextVar(
    "ai_session_persona_name", default="default"
)
"""bot人格名"""


def get_current_session() -> Session | None:
    """获取当前会话的 uninfo Session 对象

    返回:
        Session | None: 会话对象，后台任务等无会话上下文时返回 None
    """
    return _session_ctx.get()


def get_current_user_id() -> str:
    """获取当前会话用户ID

    已绑定 Session 时从 Session 读取，否则回退到兜底 user_id。

    返回:
        str: 用户ID
    """
    session = _session_ctx.get()
    if session is not None:
        return session.user.id
    return _user_id_ctx.get()


def get_current_group_id() -> str:
    """获取当前会话群组ID

    已绑定 Session 时从 Session 读取（非群聊场景返回空串），
    否则回退到兜底 group_id。

    返回:
        str: 群组ID，私聊或无群组时为空串
    """
    session = _session_ctx.get()
    if session is not None:
        return session.scene.id if session.scene.is_group else ""
    return _group_id_ctx.get()


def get_current_persona_name() -> str:
    """获取当前 bot 人格名

    返回:
        str: 人格名
    """
    return _persona_ctx.get()


def bind_session(session: Session) -> None:
    """绑定 uninfo 注入的真实会话

    在 matcher 入口（handle_chat_message 等）调用，
    将依赖注入得到的 Session 对象写入当前上下文，供本轮工具链统一读取。

    参数:
        session: nonebot_plugin_uninfo 的 Session 对象
    """
    _session_ctx.set(session)
    _user_id_ctx.set(session.user.id)
    _group_id_ctx.set(session.scene.id if session.scene.is_group else "")


@contextmanager
def bind_session_context(
    user_id: str = "",
    group_id: str | None = None,
    persona_name: str = "default",
):
    """绑定会话上下文

    Agent 执行入口调用。若上层已绑定真实 Session（bind_session 注入），
    仅更新人格名；否则写入 user_id/group_id 兜底值，供后台任务路径使用。
    退出时自动恢复原值。

    参数:
        user_id: 用户ID
        group_id: 群组ID，None视为空串
        persona_name: bot人格名
    """
    if _session_ctx.get() is not None:
        # 复用真实会话，仅更新人格名
        persona_token = _persona_ctx.set(persona_name or "default")
        try:
            yield
        finally:
            _persona_ctx.reset(persona_token)
        return

    user_token = _user_id_ctx.set(user_id or "")
    group_token = _group_id_ctx.set(group_id or "")
    persona_token = _persona_ctx.set(persona_name or "default")
    try:
        yield
    finally:
        _user_id_ctx.reset(user_token)
        _group_id_ctx.reset(group_token)
        _persona_ctx.reset(persona_token)


__all__ = [
    "bind_session",
    "bind_session_context",
    "get_current_group_id",
    "get_current_persona_name",
    "get_current_session",
    "get_current_user_id",
]
