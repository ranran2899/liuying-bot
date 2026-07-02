import asyncio
from contextlib import suppress
from dataclasses import dataclass
import time

from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import UniMsg
from nonebot_plugin_uninfo import Uninfo
from sqlalchemy.exc import IntegrityError

from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.models.user_console import UserConsole
from liuying.services.data_access import DataAccess
from liuying.services.log import logger
from liuying.utils.enum import PluginType
from liuying.utils.exception import InsufficientGold
from liuying.utils.platform import PlatformUtils
from liuying.utils.utils import get_entity_ids

from .auth.auth_admin import auth_admin
from .auth.auth_ban import auth_ban
from .auth.auth_bot import auth_bot
from .auth.auth_cost import auth_cost
from .auth.auth_group import auth_group
from .auth.auth_limit import LimitManager, auth_limit
from .auth.auth_plugin import auth_plugin
from .auth.bot_filter import bot_filter
from .auth.config import LOGGER_COMMAND, WARNING_THRESHOLD
from .auth.exception import (
    IsSuperuserException,
    PermissionExemption,
    SkipPluginException,
)
from .auth.utils import base_config

TIMEOUT_SECONDS = 5.0
CIRCUIT_RESET_TIME = 300
HOOKS_TIMEOUT = TIMEOUT_SECONDS * 2


@dataclass(slots=True)
class CircuitBreaker:
    """熔断器数据类"""
    failures: int = 0
    threshold: int = 3
    active: bool = False
    reset_time: float = 0


CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {
    name: CircuitBreaker() for name in (
        "auth_ban", "auth_bot", "auth_group",
        "auth_admin", "auth_plugin", "auth_limit"
    )
}

HOOKS_CONCURRENCY_LIMIT = base_config.get("AUTH_HOOKS_CONCURRENCY_LIMIT")
HOOKS_SEMAPHORE = asyncio.Semaphore(HOOKS_CONCURRENCY_LIMIT)
HOOKS_ACTIVE_COUNT = 0
HOOKS_ACTIVE_LOCK = asyncio.Lock()


async def with_timeout(coro, timeout: float = TIMEOUT_SECONDS, name: str | None = None):
    """带超时控制的协程执行

    参数:
        coro: 要执行的协程
        timeout: 超时时间（秒）
        name: 操作名称，用于日志记录

    返回:
        协程的返回值，或者在超时时抛出 TimeoutError
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        if name:
            logger.error(f"{name} 操作超时 (>{timeout}s)", LOGGER_COMMAND)
            if name in CIRCUIT_BREAKERS:
                cb = CIRCUIT_BREAKERS[name]
                cb.failures += 1
                if cb.failures >= cb.threshold and not cb.active:
                    cb.active = True
                    cb.reset_time = time.time() + CIRCUIT_RESET_TIME
                    logger.warning(
                        f"{name} 熔断器已激活，将在 {CIRCUIT_RESET_TIME} 秒后重置",
                        LOGGER_COMMAND,
                    )
        raise


def check_circuit_breaker(name: str) -> bool:
    """检查熔断器状态

    参数:
        name: 操作名称

    返回:
        bool: 是否已熔断
    """
    if name not in CIRCUIT_BREAKERS:
        return False

    cb = CIRCUIT_BREAKERS[name]
    if cb.active and time.time() > cb.reset_time:
        cb.active = False
        cb.failures = 0
        logger.info(f"{name} 熔断器已重置", LOGGER_COMMAND)

    return cb.active


async def get_plugin_and_user(
    module: str, user_id: str
) -> tuple[PluginInfo, UserConsole]:
    """获取用户数据和插件信息

    参数:
        module: 模块名
        user_id: 用户id

    异常:
        PermissionExemption: 插件数据不存在
        PermissionExemption: 插件类型为HIDDEN
        PermissionExemption: 用户数据不存在

    返回:
        tuple[PluginInfo, UserConsole]: 插件信息，用户信息
    """
    user_dao = DataAccess(UserConsole)
    plugin_dao = DataAccess(PluginInfo)

    plugin_task = plugin_dao.safe_get_or_none(module=module)
    user_task = user_dao.get_by_func_or_none(
        UserConsole.get_user, False, user_id=user_id
    )

    try:
        plugin, user = await with_timeout(
            asyncio.gather(plugin_task, user_task), name="get_plugin_and_user"
        )
    except TimeoutError:
        logger.warning("并行查询超时，尝试串行查询", LOGGER_COMMAND)
        plugin = await with_timeout(
            plugin_dao.safe_get_or_none(module=module), name="get_plugin"
        )
        user = await with_timeout(
            user_dao.safe_get_or_none(user_id=user_id), name="get_user"
        )
    except IntegrityError:
        await asyncio.sleep(0.5)
        plugin_task = plugin_dao.safe_get_or_none(module=module)
        user_task = user_dao.get_by_func_or_none(
            UserConsole.get_user, False, user_id=user_id
        )
        plugin, user = await with_timeout(
            asyncio.gather(plugin_task, user_task), name="get_plugin_and_user"
        )

    match (plugin, user):
        case (None, _):
            raise PermissionExemption(f"插件:{module} 数据不存在，已跳过权限检查...")
        case (p, _) if p.plugin_type == PluginType.HIDDEN:
            raise PermissionExemption(
                f"插件: {p.name}:{p.module} 为HIDDEN，已跳过权限检查..."
            )
        case (_, None):
            raise PermissionExemption("用户数据不存在，已跳过权限检查...")

    return plugin, user


async def get_plugin_cost(
    bot: Bot, user: UserConsole, plugin: PluginInfo, session: Uninfo
) -> int:
    """获取插件费用

    参数:
        bot: Bot
        user: 用户数据
        plugin: 插件数据
        session: Uninfo

    异常:
        IsSuperuserException: 超级用户

    返回:
        int: 调用插件金币费用
    """
    cost_gold = await with_timeout(auth_cost(user, plugin, session), name="auth_cost")
    if session.user.id in bot.config.superusers:
        match plugin:
            case p if p.plugin_type == PluginType.SUPERUSER:
                raise IsSuperuserException()
            case p if not p.limit_superuser:
                raise IsSuperuserException()
    return cost_gold


async def reduce_gold(user_id: str, module: str, cost_gold: int, session: Uninfo):
    """扣除用户金币

    参数:
        user_id: 用户id
        module: 插件模块名称
        cost_gold: 消耗金币
        session: Uninfo
    """
    user_dao = DataAccess(UserConsole)
    try:
        await with_timeout(
            UserConsole.reduce_gold(
                user_id=user_id,
                gold=cost_gold,
                source=module,
                platform=PlatformUtils.get_platform(session),
            ),
            name="reduce_gold",
        )
    except InsufficientGold:
        if u := await UserConsole.get_user(user_id):
            u.gold = 0
            await u.save(update_fields=["gold"])
    except TimeoutError:
        logger.error(
            f"扣除金币超时，用户: {user_id}, 金币: {cost_gold}",
            LOGGER_COMMAND,
            session=session,
        )

    await user_dao.clear_cache(user_id=user_id)
    logger.debug(f"调用功能花费金币: {cost_gold}", LOGGER_COMMAND, session=session)


async def time_hook(coro, name: str, time_dict: dict):
    """辅助函数，用于记录每个 hook 的执行时间"""
    start = time.time()
    try:
        if check_circuit_breaker(name):
            logger.info(f"{name} 熔断器激活中，跳过执行", LOGGER_COMMAND)
            time_dict[name] = "熔断跳过"
            return

        return await with_timeout(coro, name=name)
    except TimeoutError:
        time_dict[name] = f"超时 (>{TIMEOUT_SECONDS}s)"
    finally:
        if name not in time_dict:
            time_dict[name] = f"{time.time() - start:.3f}s"


async def _enter_hooks_section():
    """尝试获取全局信号量并更新计数器"""
    global HOOKS_ACTIVE_COUNT
    await HOOKS_SEMAPHORE.acquire()
    async with HOOKS_ACTIVE_LOCK:
        HOOKS_ACTIVE_COUNT += 1
        logger.debug(f"当前并发权限检查数量: {HOOKS_ACTIVE_COUNT}", LOGGER_COMMAND)


async def _leave_hooks_section():
    """释放信号量并更新计数器"""
    global HOOKS_ACTIVE_COUNT
    with suppress(Exception):
        HOOKS_SEMAPHORE.release()
    async with HOOKS_ACTIVE_LOCK:
        HOOKS_ACTIVE_COUNT = max(HOOKS_ACTIVE_COUNT - 1, 0)
        logger.debug(f"当前并发权限检查数量: {HOOKS_ACTIVE_COUNT}", LOGGER_COMMAND)


async def auth(
    matcher: Matcher,
    event: Event,
    bot: Bot,
    session: Uninfo,
    message: UniMsg,
):
    """权限检查

    参数:
        matcher: matcher
        event: Event
        bot: bot
        session: Uninfo
        message: UniMsg
    """
    start_time = time.time()
    cost_gold = 0
    ignore_flag = False
    entity = get_entity_ids(session)
    module = matcher.plugin_name or ""

    hook_times: dict[str, str] = {}
    hooks_time = 0
    entered_hooks = False

    try:
        if not module:
            raise PermissionExemption("Matcher插件名称不存在...")

        plugin_user_start = time.time()
        try:
            plugin, user = await with_timeout(
                get_plugin_and_user(module, entity.user_id), name="get_plugin_and_user"
            )
            hook_times["get_plugin_user"] = f"{time.time() - plugin_user_start:.3f}s"
        except TimeoutError:
            logger.error(
                f"获取插件和用户数据超时，模块: {module}",
                LOGGER_COMMAND,
                session=session,
            )
            raise PermissionExemption("获取插件和用户数据超时，请稍后再试...")

        await _enter_hooks_section()
        entered_hooks = True

        cost_start = time.time()
        try:
            cost_gold = await with_timeout(
                get_plugin_cost(bot, user, plugin, session), name="get_plugin_cost"
            )
            hook_times["cost_gold"] = f"{time.time() - cost_start:.3f}s"
        except TimeoutError:
            logger.error(
                f"获取插件费用超时，模块: {module}", LOGGER_COMMAND, session=session
            )

        bot_filter(session)

        group = None
        if entity.group_id:
            group_dao = DataAccess(GroupConsole)
            group = await with_timeout(
                group_dao.safe_get_or_none(
                    group_id=entity.group_id, channel_id=None
                ),
                name="get_group",
            )
            if not group:
                group, _ = await with_timeout(
                    GroupConsole.get_or_create(
                        group_id=entity.group_id,
                        channel_id=None,
                    ),
                    name="create_group",
                )

        hooks_start = time.time()

        hook_tasks = [
            time_hook(auth_ban(matcher, bot, session, plugin), "auth_ban", hook_times),
            time_hook(auth_bot(plugin, bot.self_id), "auth_bot", hook_times),
            time_hook(
                auth_group(plugin, group, message, entity.group_id),
                "auth_group",
                hook_times,
            ),
            time_hook(auth_admin(plugin, session), "auth_admin", hook_times),
            time_hook(
                auth_plugin(plugin, group, session, event), "auth_plugin", hook_times
            ),
            time_hook(auth_limit(plugin, session), "auth_limit", hook_times),
        ]

        with suppress(asyncio.TimeoutError):
            await with_timeout(
                asyncio.gather(*hook_tasks),
                timeout=HOOKS_TIMEOUT,
                name="auth_hooks_gather",
            )

        hooks_time = time.time() - hooks_start

    except SkipPluginException as e:
        LimitManager.unblock(module, entity.user_id, entity.group_id, entity.channel_id)
        logger.info(str(e), LOGGER_COMMAND, session=session)
        ignore_flag = True
    except IsSuperuserException:
        logger.debug("超级用户跳过权限检测...", LOGGER_COMMAND, session=session)
    except PermissionExemption as e:
        logger.info(str(e), LOGGER_COMMAND, session=session)
    finally:
        if entered_hooks:
            with suppress(Exception):
                await _leave_hooks_section()

    if not ignore_flag and cost_gold > 0:
        gold_start = time.time()
        with suppress(asyncio.TimeoutError):
            await with_timeout(
                reduce_gold(entity.user_id, module, cost_gold, session),
                name="reduce_gold",
            )
            hook_times["reduce_gold"] = f"{time.time() - gold_start:.3f}s"

    total_time = time.time() - start_time
    if total_time > WARNING_THRESHOLD:
        logger.warning(
            f"权限检查耗时过长: {total_time:.3f}s, 模块: {module}, "
            f"hooks时间: {hooks_time:.3f}s, 详情: {hook_times}",
            LOGGER_COMMAND,
            session=session,
        )

    if ignore_flag:
        raise IgnoredException("权限检测 ignore")
