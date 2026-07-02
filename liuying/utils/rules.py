from datetime import datetime
import re

from nonebot.adapters import Bot, Event
from nonebot.internal.rule import Rule
from nonebot.permission import SUPERUSER
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.ban_console import BanConsole
from liuying.models._group import GroupConsole
from liuying.models._user import UserLevel
from liuying.utils.platform import PlatformUtils


def ensure_group(session: Uninfo) -> bool:
    """是否在群聊中

    参数:
        session: Uninfo

    返回:
        bool: 是否在群聊中
    """
    return session.scene.is_group


def ensure_private(session: Uninfo) -> bool:
    """是否在私聊中

    参数:
        session: Uninfo

    返回:
        bool: 是否在私聊中
    """
    return session.scene.is_private


def ensure_guild(session: Uninfo) -> bool:
    """是否在频道中

    参数:
        session: Uninfo

    返回:
        bool: 是否在频道中
    """
    return session.scene.is_guild or session.scene.is_channel


def ensure_channel(session: Uninfo) -> bool:
    """是否在子频道中

    参数:
        session: Uninfo

    返回:
        bool: 是否在子频道中
    """
    return session.scene.is_channel


def admin_check(a: int | str, key: str | None = None) -> Rule:
    """管理员权限等级检查

    参数:
        a: 权限等级或配置项 module
        key: 配置项 key.

    返回:
        Rule: Rule
    """

    async def _rule(bot: Bot, event: Event, session: Uninfo) -> bool:
        if await SUPERUSER(bot, event):
            return True

        if PlatformUtils.is_qbot(session):
            return False

        group_id = session.group.id if session.group else None
        user_id = session.user.id

        level = a
        if isinstance(a, str) and key:
            level = Config.get_config(a, key)
        if level is None:
            return False

        user_level = await UserLevel.get_level(user_id, bot.self_id, group_id)
        return user_level >= int(level)

    return Rule(_rule)


def notice_rule(event_type: type | list[type]) -> Rule:
    """Notice限制

    参数:
        event_type: Event类型

    返回:
        Rule: Rule
    """

    async def _rule(event: Event) -> bool:
        types = event_type if isinstance(event_type, list) else (event_type,)
        return isinstance(event, tuple(types))

    return Rule(_rule)


def is_allowed_call() -> Rule:
    """是否允许调用插件"""

    async def _rule(session: Uninfo) -> bool:
        group_id = session.group.id if session.group else None
        if await BanConsole.is_ban(session.user.id, group_id):
            return False
        if group_id:
            if await BanConsole.is_ban(None, group_id):
                return False
            if g := await GroupConsole.get_group(group_id):
                if g.level < 0:
                    return False
        return True

    return Rule(_rule)


def time_range_rule(start: str, end: str) -> Rule:
    """时间段规则，仅在指定时间范围内允许执行

    参数:
        start: 开始时间 (HH:MM)
        end: 结束时间 (HH:MM)

    返回:
        Rule: Rule
    """

    async def _rule() -> bool:
        current_time = datetime.now().strftime("%H:%M")
        return start <= current_time <= end

    return Rule(_rule)


def is_night_time() -> Rule:
    """夜间规则（22:00-06:00）

    返回:
        Rule: Rule
    """

    async def _rule() -> bool:
        hour = datetime.now().hour
        return hour >= 22 or hour < 6

    return Rule(_rule)


def is_weekend() -> Rule:
    """周末规则

    返回:
        Rule: Rule
    """

    async def _rule() -> bool:
        return datetime.now().weekday() >= 5

    return Rule(_rule)


def match_regex(pattern: str, flags: int = 0) -> Rule:
    """正则匹配规则

    参数:
        pattern: 正则表达式
        flags: 正则标志

    返回:
        Rule: Rule
    """

    async def _rule(event: Event) -> bool:
        return bool(re.search(pattern, event.get_plaintext(), flags))

    return Rule(_rule)


def word_count_rule(min_count: int = 0, max_count: int = 999999) -> Rule:
    """字数限制规则

    参数:
        min_count: 最小字数
        max_count: 最大字数

    返回:
        Rule: Rule
    """

    async def _rule(event: Event) -> bool:
        return min_count <= len(event.get_plaintext().strip()) <= max_count

    return Rule(_rule)


def scope_in(*scopes: str) -> Rule:
    """作用域白名单规则

    参数:
        scopes: 允许的作用域列表

    返回:
        Rule: Rule
    """

    async def _rule(session: Uninfo) -> bool:
        return session.scope in scopes

    return Rule(_rule)


def scope_not_in(*scopes: str) -> Rule:
    """作用域黑名单规则

    参数:
        scopes: 禁止的作用域列表

    返回:
        Rule: Rule
    """

    async def _rule(session: Uninfo) -> bool:
        return session.scope not in scopes

    return Rule(_rule)


def adapter_in(*adapters: str) -> Rule:
    """适配器白名单规则

    参数:
        adapters: 允许的适配器列表

    返回:
        Rule: Rule
    """

    async def _rule(session: Uninfo) -> bool:
        return session.adapter in adapters

    return Rule(_rule)
