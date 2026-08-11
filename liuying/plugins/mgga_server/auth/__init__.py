"""auth —— 登录与账号系统模块。

协议：

* ``auth.register`` {username, password, name}   -> ``auth.result``
* ``auth.login``    {username, password}         -> ``auth.result``
* ``auth.token``    {token}                      -> ``auth.result``（免密重连）
* ``auth.logout``   {}                           -> ``auth.logout.ok``
* ``auth.rename``   {name}                       -> ``auth.profile``
* ``auth.profile``  {}                           -> ``auth.profile``

``auth.result`` 数据：``{"token": str, "profile": {...}}``
"""

from __future__ import annotations

import re

from nonebot import get_driver
from nonebot.log import logger

from ..core import Code, Packet, ProtocolError, Session, config, hub, on_packet
from .store import Account, AccountStore

__all__ = ["Account", "AccountStore", "store", "account_of"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
NICKNAME_MAX = 12

#: 账号库，在 driver 启动时按最终配置创建
store: AccountStore = None  # type: ignore[assignment]

_driver = get_driver()


@_driver.on_startup
async def _init_store() -> None:
    global store
    store = AccountStore(config.game_db_path)
    await store.init()
    logger.info(f"[猛鬼公寓] 账号库就绪：{store.path}")


def account_of(session: Session) -> Account:
    """取出会话绑定的账号；未登录时抛错。"""
    account = session.state.get("account")
    if not isinstance(account, Account):
        raise ProtocolError(Code.NOT_AUTHED, "请先登录")
    return account


# ---------------------------------------------------------------- 登录流程

async def _bind(session: Session, account: Account, token: str, seq: int | None) -> None:
    """把账号绑定到会话，顶掉同账号的旧连接，并回发结果。"""
    session.uid = account.uid
    session.username = account.username
    session.nickname = account.nickname
    session.state["account"] = account
    session.state["token"] = token

    old = hub.bind_uid(session)
    if old is not None:
        await old.send("auth.kicked", {"reason": "账号在别处登录"})
        await old.close("账号在别处登录")
        logger.info(f"[mgga_server] {account.username} 顶下线旧连接 #{old.sid}")

    await session.send("auth.result", {"token": token, "profile": account.profile()}, seq)
    logger.info(f"[mgga_server] {account.username}(uid={account.uid}) 登录成功")


@on_packet("auth.register", auth=False)
async def _handle_register(session: Session, packet: Packet) -> None:
    if session.authed:
        raise ProtocolError(Code.ALREADY_ONLINE, "当前连接已登录")
    username = packet.str_of("username", max_len=20)
    password = packet.str_of("password", max_len=64)
    nickname = packet.str_of("name", max_len=NICKNAME_MAX, required=False) or username

    if not USERNAME_RE.match(username):
        raise ProtocolError(Code.BAD_FIELD, "用户名需为 3~20 位字母、数字或下划线")
    if len(password) < 6:
        raise ProtocolError(Code.BAD_FIELD, "密码至少 6 位")

    account = await store.register(username, password, nickname)
    if account is None:
        raise ProtocolError(Code.NAME_TAKEN, "该用户名已被注册")

    token = await store.issue_token(account.uid, config.game_token_ttl)
    await _bind(session, account, token, packet.seq)


@on_packet("auth.login", auth=False)
async def _handle_login(session: Session, packet: Packet) -> None:
    if session.authed:
        raise ProtocolError(Code.ALREADY_ONLINE, "当前连接已登录")
    username = packet.str_of("username", max_len=20)
    password = packet.str_of("password", max_len=64)

    account = await store.verify(username, password)
    if account is None:
        raise ProtocolError(Code.AUTH_FAILED, "用户名或密码错误")

    token = await store.issue_token(account.uid, config.game_token_ttl)
    await _bind(session, account, token, packet.seq)


@on_packet("auth.token", auth=False)
async def _handle_token(session: Session, packet: Packet) -> None:
    """使用上次登录保存的令牌免密重连。"""
    if session.authed:
        raise ProtocolError(Code.ALREADY_ONLINE, "当前连接已登录")
    token = packet.str_of("token", max_len=128)
    account = await store.resolve_token(token)
    if account is None:
        raise ProtocolError(Code.AUTH_FAILED, "登录状态已过期，请重新登录")
    await _bind(session, account, token, packet.seq)


@on_packet("auth.logout")
async def _handle_logout(session: Session, packet: Packet) -> None:
    token = session.state.get("token")
    if isinstance(token, str):
        await store.revoke_token(token)
    await session.send("auth.logout.ok", {}, packet.seq)
    await session.close("已登出")


# ---------------------------------------------------------------- 个人资料

@on_packet("auth.rename")
async def _handle_rename(session: Session, packet: Packet) -> None:
    nickname = packet.str_of("name", max_len=NICKNAME_MAX)
    account = account_of(session)
    account.nickname = nickname
    session.nickname = nickname
    await store.rename(account.uid, nickname)
    await session.send("auth.profile", {"profile": account.profile()}, packet.seq)


@on_packet("auth.profile")
async def _handle_profile(session: Session, packet: Packet) -> None:
    await session.send("auth.profile", {"profile": account_of(session).profile()}, packet.seq)
