"""auth —— 登录与账号系统模块。

协议：

* ``auth.register`` {username, password, name}   -> ``auth.result``
* ``auth.login``    {username, password}         -> ``auth.result``
* ``auth.token``    {token}                      -> ``auth.result``（免密重连）
* ``auth.logout``   {}                           -> ``auth.logout.ok``
* ``auth.rename``   {name}                       -> ``auth.profile``
* ``auth.profile``  {}                           -> ``auth.profile``

``auth.result`` 数据：``{"token": str, "profile": {...}}``

账号数据全部落在项目 ORM（见 ``..models``），不再自持 sqlite 连接。
"""

import re
import time

from liuying.utils.log import logger

from ..core import Code, Packet, ProtocolError, Session, config, hub, on_packet
from ..models import (
    NAME_MAX_LEN,
    NAME_MIN_LEN,
    PASSWORD_MAX_LEN,
    PASSWORD_MIN_LEN,
    GameAccount,
    GameToken,
)

__all__ = ["account_of", "uid_of"]

USERNAME_RE = re.compile(rf"^[A-Za-z0-9_]{{{NAME_MIN_LEN + 1},20}}$")
#: 昵称不允许出现控制字符与全角空格，避免客户端 UI 被刷屏
NICKNAME_RE = re.compile(rf"^[^\s\x00-\x1f\u3000]{{1,{NAME_MAX_LEN}}}$")

#: 同一用户名连续失败多少次后进入冷却
LOGIN_FAIL_LIMIT = 5
#: 冷却时长（秒）
LOGIN_COOLDOWN = 60.0
#: 失败记录表容量上限，超出后清理过期项，防止被随机用户名撑爆内存
FAIL_TABLE_MAX = 4096

#: username -> (失败次数, 最近失败时间)
_fails: dict[str, tuple[int, float]] = {}


def _check_throttle(username: str) -> None:
    """登录频率检查，防止在线暴力破解。

    参数:
        username: 登录名。

    抛出:
        ProtocolError: 处于冷却期内。
    """
    count, stamp = _fails.get(username, (0, 0.0))
    if count < LOGIN_FAIL_LIMIT:
        return
    if (left := LOGIN_COOLDOWN - (time.monotonic() - stamp)) > 0:
        raise ProtocolError(Code.RATE_LIMIT, f"尝试过于频繁，请 {left:.0f} 秒后再试")
    _fails.pop(username, None)


def _mark_fail(username: str) -> None:
    """记录一次登录失败。

    参数:
        username: 登录名。
    """
    now = time.monotonic()
    if len(_fails) >= FAIL_TABLE_MAX:
        for name, (_, stamp) in list(_fails.items()):
            if now - stamp > LOGIN_COOLDOWN:
                del _fails[name]
    count, _ = _fails.get(username, (0, 0.0))
    _fails[username] = (count + 1, now)


def uid_of(session: Session) -> int:
    """取会话绑定的玩家 ID；未登录时抛错。

    参数:
        session: 会话。

    返回:
        int: 玩家 ID。

    抛出:
        ProtocolError: 会话未登录。
    """
    if not session.authed:
        raise ProtocolError(Code.NOT_AUTHED, "请先登录")
    return session.uid


async def account_of(session: Session) -> GameAccount:
    """读取会话对应的账号。

    不在会话上缓存 ORM 实例，避免多连接并发下读到过期统计数据。

    参数:
        session: 会话。

    返回:
        GameAccount: 账号。

    抛出:
        ProtocolError: 未登录或账号已被删除。
    """
    account = await GameAccount.filter(uid=uid_of(session)).first()
    if account is None:
        raise ProtocolError(Code.NOT_AUTHED, "账号不存在，请重新登录")
    return account


# ---------------------------------------------------------------- 登录流程


async def _bind(
    session: Session, account: GameAccount, token: str, seq: int | None
) -> None:
    """把账号绑定到会话，顶掉同账号的旧连接，并回发结果。

    参数:
        session: 当前会话。
        account: 账号。
        token: 本次签发的令牌。
        seq: 请求序号。
    """
    session.uid = account.uid
    session.username = account.username
    session.nickname = account.nickname
    session.state["token"] = token

    if (old := hub.bind_uid(session)) is not None:
        await old.send("auth.kicked", {"reason": "账号在别处登录"})
        await old.close("账号在别处登录")
        logger.info(f"[mgga_server] {account.username} 顶下线旧连接 #{old.sid}")

    _fails.pop(account.username, None)
    await account.touch_login()
    await session.send(
        "auth.result", {"token": token, "profile": account.profile()}, seq
    )
    logger.info(f"[mgga_server] {account.username}(uid={account.uid}) 登录成功")


def _ensure_not_authed(session: Session) -> None:
    """确保当前连接尚未登录。

    参数:
        session: 会话。

    抛出:
        ProtocolError: 已登录。
    """
    if session.authed:
        raise ProtocolError(Code.ALREADY_ONLINE, "当前连接已登录")


def _ensure_usable(account: GameAccount) -> None:
    """确保账号未被封禁。

    参数:
        account: 账号。

    抛出:
        ProtocolError: 账号已封禁。
    """
    if account.banned:
        raise ProtocolError(Code.BANNED, "该账号已被封禁")


@on_packet("auth.register", auth=False)
async def _handle_register(session: Session, packet: Packet) -> None:
    """处理注册。

    参数:
        session: 会话。
        packet: 请求包。
    """
    _ensure_not_authed(session)
    username = packet.str_of("username", max_len=20)
    password = packet.str_of("password", max_len=PASSWORD_MAX_LEN)
    nickname = packet.str_of("name", max_len=NAME_MAX_LEN, required=False) or username

    if not USERNAME_RE.match(username):
        raise ProtocolError(Code.BAD_FIELD, "用户名需为 3~20 位字母、数字或下划线")
    if len(password) < PASSWORD_MIN_LEN:
        raise ProtocolError(Code.BAD_FIELD, f"密码至少 {PASSWORD_MIN_LEN} 位")
    if not NICKNAME_RE.match(nickname):
        raise ProtocolError(Code.BAD_FIELD, f"昵称需为 1~{NAME_MAX_LEN} 个非空白字符")

    account = await GameAccount.register(username, password, nickname)
    if account is None:
        raise ProtocolError(Code.NAME_TAKEN, "该用户名已被注册")

    token = await GameToken.issue(account.uid, config.game_token_ttl_days)
    await _bind(session, account, token, packet.seq)


@on_packet("auth.login", auth=False)
async def _handle_login(session: Session, packet: Packet) -> None:
    """处理密码登录。

    参数:
        session: 会话。
        packet: 请求包。
    """
    _ensure_not_authed(session)
    username = packet.str_of("username", max_len=20)
    password = packet.str_of("password", max_len=PASSWORD_MAX_LEN)
    _check_throttle(username)

    account = await GameAccount.verify(username, password)
    if account is None:
        _mark_fail(username)
        raise ProtocolError(Code.AUTH_FAILED, "用户名或密码错误")
    _ensure_usable(account)

    token = await GameToken.issue(account.uid, config.game_token_ttl_days)
    await _bind(session, account, token, packet.seq)


@on_packet("auth.token", auth=False)
async def _handle_token(session: Session, packet: Packet) -> None:
    """使用上次登录保存的令牌免密重连。

    参数:
        session: 会话。
        packet: 请求包。
    """
    _ensure_not_authed(session)
    token = packet.str_of("token", max_len=128)
    account = await GameToken.resolve(token)
    if account is None:
        raise ProtocolError(Code.AUTH_FAILED, "登录状态已过期，请重新登录")
    _ensure_usable(account)
    await _bind(session, account, token, packet.seq)


@on_packet("auth.logout")
async def _handle_logout(session: Session, packet: Packet) -> None:
    """处理登出，同时吊销令牌。

    参数:
        session: 会话。
        packet: 请求包。
    """
    await GameToken.revoke(session.uid)
    await session.send("auth.logout.ok", {}, packet.seq)
    await session.close("已登出")


# ---------------------------------------------------------------- 个人资料


@on_packet("auth.rename")
async def _handle_rename(session: Session, packet: Packet) -> None:
    """修改昵称。

    参数:
        session: 会话。
        packet: 请求包。
    """
    nickname = packet.str_of("name", max_len=NAME_MAX_LEN)
    if not NICKNAME_RE.match(nickname):
        raise ProtocolError(Code.BAD_FIELD, f"昵称需为 1~{NAME_MAX_LEN} 个非空白字符")

    account = await account_of(session)
    await account.rename(nickname)
    session.nickname = nickname
    await session.send("auth.profile", {"profile": account.profile()}, packet.seq)


@on_packet("auth.profile")
async def _handle_profile(session: Session, packet: Packet) -> None:
    """查询个人档案。

    参数:
        session: 会话。
        packet: 请求包。
    """
    account = await account_of(session)
    await session.send("auth.profile", {"profile": account.profile()}, packet.seq)
