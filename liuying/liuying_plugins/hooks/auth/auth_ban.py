import asyncio
from dataclasses import dataclass
import time

from nonebot.adapters import Bot
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import At
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.ban_console import BanConsole
from liuying.models.plugin_info import PluginInfo
from liuying.services.data_access import DataAccess
from liuying.utils.enum import PluginType
from liuying.utils.log import logger

from .config import LOGGER_COMMAND, WARNING_THRESHOLD
from .exception import SkipPluginException
from .utils import get_group_channel_ids, send_message

Config.add_plugin_config(
    "hook",
    "BAN_RESULT",
    "才不会给你发消息.",
    help="对被ban用户发送的消息",
)

DB_TIMEOUT = 5.0
_flmt_global = None


def _get_flmt():
    """延迟初始化频率限制器"""
    global _flmt_global
    if _flmt_global is None:
        from liuying.models.extra.limit import FreqLimiter
        _flmt_global = FreqLimiter(300)
    return _flmt_global


@dataclass(slots=True)
class BanTimeResult:
    """Ban时间结果"""
    is_banned: bool
    time_value: int


async def calculate_ban_time(ban_record: BanConsole | None) -> int:
    """根据ban记录计算剩余ban时间

    参数:
        ban_record: BanConsole记录

    返回:
        int: ban剩余时长，-1时为永久ban，0表示未被ban
    """
    if not ban_record:
        return 0

    if ban_record.duration == -1:
        return -1

    _time = time.time() - (ban_record.ban_time + ban_record.duration)
    if _time < 0:
        return int(abs(_time))
    await ban_record.delete()
    return 0


async def is_ban(user_id: str | None, group_id: str | None) -> int:
    """检查用户或群组是否被ban

    参数:
        user_id: 用户ID
        group_id: 群组ID

    返回:
        int: ban的剩余时间，0表示未被ban
    """
    if not user_id and not group_id:
        return 0

    start_time = time.time()
    ban_dao = DataAccess(BanConsole)

    try:
        tasks = []
        if user_id and group_id:
            tasks.append(ban_dao.safe_get_or_none(user_id=user_id, group_id=group_id))
        if user_id:
            tasks.append(
                ban_dao.safe_get_or_none(user_id=user_id, group_id=None)
            )

        if not tasks:
            return 0

        try:
            ban_records = await asyncio.wait_for(
                asyncio.gather(*tasks), timeout=DB_TIMEOUT
            )
            match len(ban_records):
                case 2:
                    group_user, user = ban_records
                case 1:
                    group_user = ban_records[0] if user_id and group_id else None
                    user = ban_records[0] if not (user_id and group_id) else None
                case _:
                    group_user, user = None, None
        except TimeoutError:
            logger.error(
                f"查询ban记录超时: user_id={user_id}, group_id={group_id}",
                LOGGER_COMMAND,
            )
            return 0

        results = [r for r in (group_user, user) if r]

        if not results:
            return 0

        logger.debug(f"查询到的ban记录: {results}", LOGGER_COMMAND)
        max_ban_time: int = 0
        for result in results:
            if result.duration != 0:
                ban_time = await calculate_ban_time(result)
                if ban_time == -1 or ban_time > max_ban_time:
                    max_ban_time = ban_time

        return max_ban_time
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"is_ban 耗时: {elapsed:.3f}s",
                LOGGER_COMMAND,
                session=user_id,
                group_id=group_id,
            )


def check_plugin_type(matcher: Matcher) -> bool:
    """判断插件类型是否是隐藏插件

    参数:
        matcher: Matcher

    返回:
        bool: 是否为隐藏插件
    """
    if plugin := matcher.plugin:
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra.get("plugin_type") == PluginType.HIDDEN:
                return False
    return True


def format_time(time_val: float) -> str:
    """格式化时间

    参数:
        time_val: ban时长

    返回:
        str: 格式化时间文本
    """
    if time_val == -1:
        return "∞"
    time_val = abs(int(time_val))
    match time_val:
        case t if t < 60:
            return f"{t} 秒"
        case t if t < 3600:
            minute = t // 60
            return f"{minute} 分钟"
        case _:
            hours = time_val // 3600
            minute = (time_val % 3600) // 60
            return f"{hours} 小时 {minute}分钟"


async def group_handle(group_id: str) -> None:
    """群组ban检查

    参数:
        group_id: 群组id

    异常:
        SkipPluginException: 群组处于黑名单
    """
    start_time = time.time()
    try:
        if await is_ban(None, group_id):
            raise SkipPluginException("群组处于黑名单中...")
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"group_handle 耗时: {elapsed:.3f}s",
                LOGGER_COMMAND,
                group_id=group_id,
            )


async def user_handle(
    plugin: PluginInfo, user_id: str, group_id: str | None, session: Uninfo
) -> None:
    """用户ban检查

    参数:
        plugin: PluginInfo
        user_id: 用户id
        group_id: 群组id
        session: Uninfo

    异常:
        SkipPluginException: 用户处于黑名单
    """
    start_time = time.time()
    try:
        ban_result = Config.get_config("hook", "BAN_RESULT")
        time_val = await is_ban(user_id, group_id)
        if not time_val:
            return
        time_str = format_time(time_val)

        if (
            plugin
            and time_val != -1
            and ban_result
            and _get_flmt().check(user_id)
        ):
            try:
                await asyncio.wait_for(
                    send_message(
                        session,
                        [
                            At(flag="user", target=user_id),
                            f"{ban_result}\n在..在 {time_str} 后才会理你喔",
                        ],
                        user_id,
                    ),
                    timeout=DB_TIMEOUT,
                )
                _get_flmt().start_cd(user_id)
            except TimeoutError:
                logger.error(f"发送消息超时: {user_id}", LOGGER_COMMAND)
        raise SkipPluginException("用户处于黑名单中...")
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"user_handle 耗时: {elapsed:.3f}s",
                LOGGER_COMMAND,
                session=session,
            )


async def auth_ban(
    matcher: Matcher, bot: Bot, session: Uninfo, plugin: PluginInfo
) -> None:
    """权限检查 - ban 检查

    参数:
        matcher: Matcher
        bot: Bot
        session: Uninfo
        plugin: PluginInfo
    """
    start_time = time.time()
    try:
        if not check_plugin_type(matcher):
            return
        if not matcher.plugin_name:
            return

        user_id = session.user.id
        ids = get_group_channel_ids(session)

        if user_id in bot.config.superusers:
            return

        if ids.group_id:
            try:
                await asyncio.wait_for(
                    group_handle(ids.group_id), timeout=DB_TIMEOUT
                )
            except TimeoutError:
                logger.error(f"群组ban检查超时: {ids.group_id}", LOGGER_COMMAND)

        if user_id:
            try:
                await asyncio.wait_for(
                    user_handle(plugin, user_id, ids.group_id, session),
                    timeout=DB_TIMEOUT,
                )
            except TimeoutError:
                logger.error(f"用户ban检查超时: {user_id}", LOGGER_COMMAND)
    finally:
        elapsed = time.time() - start_time
        if elapsed > WARNING_THRESHOLD:
            logger.warning(
                f"auth_ban 总耗时: {elapsed:.3f}s, plugin={matcher.plugin_name}",
                LOGGER_COMMAND,
                session=session,
            )
