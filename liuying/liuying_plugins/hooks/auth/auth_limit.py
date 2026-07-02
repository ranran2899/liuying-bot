import asyncio
from contextlib import suppress
import time
from typing import ClassVar

import nonebot
from nonebot_plugin_uninfo import Uninfo
from pydantic import BaseModel

from liuying.models.extra.limit import CountLimiter, FreqLimiter, UserBlockLimiter
from liuying.models.plugin_info import PluginInfo
from liuying.models.plugin_limit import PluginLimit
from liuying.utils.enum import LimitWatchType, PluginLimitType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.message import MessageUtils
from liuying.utils.time_utils import TimeUtils

from .config import LOGGER_COMMAND, WARNING_THRESHOLD
from .exception import SkipPluginException
from .utils import get_group_channel_ids

driver = nonebot.get_driver()

DB_TIMEOUT = 5.0
UPDATE_TIMEOUT = 10.0


@PriorityLifecycle.on_startup(priority=5)
async def _():
    """初始化限制"""
    await LimitManager.init_limit()


class LimitModel(BaseModel):
    limit: PluginLimit
    limiter: FreqLimiter | UserBlockLimiter | CountLimiter

    class Config:
        arbitrary_types_allowed = True


class LimitManager:
    """限制管理器"""

    add_module: ClassVar[list[str]] = []
    last_update_time: ClassVar[float] = 0
    update_interval: ClassVar[float] = 6000
    is_updating: ClassVar[bool] = False

    cd_limit: ClassVar[dict[str, LimitModel]] = {}
    block_limit: ClassVar[dict[str, LimitModel]] = {}
    count_limit: ClassVar[dict[str, LimitModel]] = {}

    module_limit_cache: ClassVar[dict[str, tuple[float, list[PluginLimit]]]] = {}
    module_cache_ttl: ClassVar[float] = 60

    @classmethod
    async def init_limit(cls):
        """初始化限制"""
        cls.last_update_time = time.time()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(cls.update_limits(), timeout=UPDATE_TIMEOUT)

    @classmethod
    async def update_limits(cls):
        """更新限制信息"""
        if cls.is_updating:
            return

        cls.is_updating = True
        try:
            start_time = time.time()
            try:
                limit_list = await asyncio.wait_for(
                    PluginLimit.filter(status=True).all(), timeout=DB_TIMEOUT
                )
            except TimeoutError:
                logger.error("查询限制信息超时", LOGGER_COMMAND)
                return

            cls.add_module = []
            cls.cd_limit = {}
            cls.block_limit = {}
            cls.count_limit = {}
            for limit in limit_list:
                cls.add_limit(limit)

            cls.last_update_time = time.time()
            elapsed = time.time() - start_time
            if elapsed > WARNING_THRESHOLD:
                logger.warning(f"更新限制信息耗时: {elapsed:.3f}s", LOGGER_COMMAND)
        finally:
            cls.is_updating = False

    @classmethod
    def add_limit(cls, limit: PluginLimit):
        """添加限制

        参数:
            limit: PluginLimit
        """
        if limit.module in cls.add_module:
            return

        cls.add_module.append(limit.module)
        match limit.limit_type:
            case PluginLimitType.BLOCK:
                cls.block_limit[limit.module] = LimitModel(
                    limit=limit, limiter=UserBlockLimiter()
                )
            case PluginLimitType.CD:
                cls.cd_limit[limit.module] = LimitModel(
                    limit=limit, limiter=FreqLimiter(limit.cd)
                )
            case PluginLimitType.COUNT:
                cls.count_limit[limit.module] = LimitModel(
                    limit=limit, limiter=CountLimiter(limit.max_count)
                )

    @classmethod
    def unblock(
        cls, module: str, user_id: str, group_id: str | None, channel_id: str | None
    ):
        """解除插件block

        参数:
            module: 模块名
            user_id: 用户id
            group_id: 群组id
            channel_id: 频道id
        """
        if not (limit_model := cls.block_limit.get(module)):
            return

        limit = limit_model.limit
        limiter: UserBlockLimiter = limit_model.limiter
        key_type = (
            channel_id or group_id
            if group_id and limit.watch_type == LimitWatchType.GROUP
            else user_id
        )
        logger.debug(
            f"解除对象: {key_type} 的block限制",
            LOGGER_COMMAND,
            session=user_id,
            group_id=group_id,
        )
        limiter.set_false(key_type)

    @classmethod
    async def get_module_limits(cls, module: str) -> list[PluginLimit]:
        """获取模块的限制信息，使用缓存减少数据库查询

        参数:
            module: 模块名

        返回:
            list[PluginLimit]: 限制列表
        """
        current_time = time.time()

        if module in cls.module_limit_cache:
            cache_time, limits = cls.module_limit_cache[module]
            if current_time - cache_time < cls.module_cache_ttl:
                return limits

        try:
            start_time = time.time()
            limits = await asyncio.wait_for(
                PluginLimit.filter(module=module, status=True).all(),
                timeout=DB_TIMEOUT,
            )
            elapsed = time.time() - start_time
            if elapsed > WARNING_THRESHOLD:
                logger.warning(
                    f"查询模块限制信息耗时: {elapsed:.3f}s, 模块: {module}",
                    LOGGER_COMMAND,
                )

            cls.module_limit_cache[module] = (current_time, limits)
            return limits
        except TimeoutError:
            logger.error(f"查询模块限制信息超时: {module}", LOGGER_COMMAND)
            return []

    @classmethod
    async def check(
        cls,
        module: str,
        user_id: str,
        group_id: str | None,
        channel_id: str | None,
    ):
        """检测限制

        参数:
            module: 模块名
            user_id: 用户id
            group_id: 群组id
            channel_id: 频道id

        异常:
            SkipPluginException: 限制触发
        """
        start_time = time.time()

        if (
            time.time() - cls.last_update_time > cls.update_interval
            and not cls.is_updating
        ):
            _update_task = asyncio.create_task(cls.update_limits())

        if module not in cls.add_module:
            limits = await cls.get_module_limits(module)
            for limit in limits:
                cls.add_limit(limit)

        try:
            for limit_dict in (cls.cd_limit, cls.block_limit, cls.count_limit):
                if limit_model := limit_dict.get(module):
                    await cls._check_limit(
                        limit_model, user_id, group_id, channel_id
                    )
        finally:
            elapsed = time.time() - start_time
            if elapsed > WARNING_THRESHOLD:
                logger.warning(
                    f"限制检查耗时: {elapsed:.3f}s, 模块: {module}",
                    LOGGER_COMMAND,
                    session=user_id,
                    group_id=group_id,
                )

    @classmethod
    async def _check_limit(
        cls,
        limit_model: LimitModel | None,
        user_id: str,
        group_id: str | None,
        channel_id: str | None,
    ):
        """检测限制

        参数:
            limit_model: LimitModel
            user_id: 用户id
            group_id: 群组id
            channel_id: 频道id

        异常:
            SkipPluginException: 限制触发
        """
        if not limit_model:
            return

        limit = limit_model.limit
        limiter = limit_model.limiter

        is_limit = (
            limit.watch_type == LimitWatchType.ALL
            or (group_id and limit.watch_type == LimitWatchType.GROUP)
            or (not group_id and limit.watch_type == LimitWatchType.USER)
        )

        key_type = (
            channel_id or group_id
            if group_id and limit.watch_type == LimitWatchType.GROUP
            else user_id
        )

        if is_limit and not limiter.check(key_type):
            if limit.result:
                format_kwargs = {}
                if isinstance(limiter, FreqLimiter):
                    left_time = limiter.left_time(key_type)
                    cd_str = TimeUtils.format_duration(left_time)
                    format_kwargs = {"cd": cd_str}
                try:
                    await asyncio.wait_for(
                        MessageUtils.build_message(
                            limit.result, format_args=format_kwargs
                        ).send(),
                        timeout=DB_TIMEOUT,
                    )
                except TimeoutError:
                    logger.error(f"发送限制消息超时: {limit.module}", LOGGER_COMMAND)
            raise SkipPluginException(
                f"{limit.module}({limit.limit_type}) 正在限制中..."
            )

        logger.debug(
            f"开始进行限制 {limit.module}({limit.limit_type})...",
            LOGGER_COMMAND,
            session=user_id,
            group_id=group_id,
        )
        match limiter:
            case FreqLimiter():
                limiter.start_cd(key_type)
            case UserBlockLimiter():
                limiter.set_true(key_type)
            case CountLimiter():
                limiter.increase(key_type)


async def auth_limit(plugin: PluginInfo, session: Uninfo):
    """插件限制

    参数:
        plugin: PluginInfo
        session: Uninfo
    """
    user_id = session.user.id
    ids = get_group_channel_ids(session)

    try:
        await asyncio.wait_for(
            LimitManager.check(
                plugin.module, user_id, ids.group_id, ids.channel_id
            ),
            timeout=UPDATE_TIMEOUT,
        )
    except TimeoutError:
        logger.error(f"检查插件限制超时: {plugin.module}", LOGGER_COMMAND)
