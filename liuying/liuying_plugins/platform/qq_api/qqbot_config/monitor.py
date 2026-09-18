"""QQ机器人重连监控模块

通过回调注入机制与业务层解耦,避免循环依赖:
- ReconnectMonitor 仅依赖 adapter 查询连接状态
- 业务层(manager)在启动钩子中通过 register_delete_callback 注入删除回调
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import ClassVar

import nonebot
from nonebot.adapters import Bot

from liuying.utils.log import logger

from .adapter import QQAdapterManager
from .model import QQBotConfig

CHECK_INTERVAL = 10.0
"""监控检查间隔(秒)"""

MAX_FAILURES = 3
"""连续失败次数上限,超过后自动删除配置"""

DeleteCallback = Callable[[str, str], Awaitable[str]]
"""自动删除回调签名: (user_id, bot_id) -> 结果消息"""


class ReconnectMonitor:
    """QQ机器人重连监控器

    监控QQ机器人连接状态,当连续多次重连失败时自动删除配置,
    避免因凭据失效导致的无限重试
    """

    _failures: ClassVar[dict[str, int]] = {}
    """机器人ID到连续失败次数的映射"""

    _task: ClassVar[asyncio.Task | None] = None
    """监控任务"""

    _delete_callback: ClassVar[DeleteCallback | None] = None
    """自动删除配置回调(由业务层注入)"""

    @classmethod
    def register_delete_callback(cls, callback: DeleteCallback) -> None:
        """注册自动删除回调

        参数:
            callback: 删除配置回调函数
        """
        cls._delete_callback = callback

    @classmethod
    def start(cls) -> None:
        """启动重连监控"""
        if cls._task is not None and not cls._task.done():
            return
        cls._task = asyncio.create_task(cls._loop())
        logger.info("QQ机器人重连监控已启动", "QQBotConfig")

    @classmethod
    def on_connected(cls, bot_id: str) -> None:
        """机器人连接成功时重置失败计数

        参数:
            bot_id: 机器人ID
        """
        cls._failures.pop(bot_id, None)

    @classmethod
    def reset_failures(cls) -> None:
        """清空全部失败计数"""
        cls._failures.clear()

    @classmethod
    async def _loop(cls) -> None:
        """监控主循环"""
        while True:
            try:
                await asyncio.sleep(CHECK_INTERVAL)
                await cls._check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重连监控异常: {e}", "QQBotConfig", e=e)

    @classmethod
    async def _check(cls) -> None:
        """执行一次连接状态检查"""
        adapter = QQAdapterManager._get_adapter()
        online_ids = set(adapter.bots.keys())
        configured_ids = {b.id for b in adapter.qq_config.qq_bots}

        for bot_id in configured_ids:
            if bot_id in online_ids:
                cls.on_connected(bot_id)
                continue
            count = cls._failures.get(bot_id, 0) + 1
            cls._failures[bot_id] = count
            if count < MAX_FAILURES:
                continue
            logger.warning(
                f"机器人 {bot_id} 连续 {count} 次重连失败,"
                "自动删除配置以停止无限重试",
                "QQBotConfig",
            )
            await cls._auto_delete(bot_id)

    @classmethod
    async def _auto_delete(cls, bot_id: str) -> None:
        """自动删除配置并清理

        参数:
            bot_id: 机器人ID
        """
        cls._failures.pop(bot_id, None)
        if cls._delete_callback is None:
            logger.warning("未注册删除回调,无法自动删除机器人配置", "QQBotConfig")
            return

        user_id = await QQBotConfig.get_bot_owner(bot_id)
        if user_id is None:
            return

        msg = await cls._delete_callback(user_id, bot_id)
        logger.warning(f"重连失败保护触发: {msg}", "QQBotConfig")


_driver = nonebot.get_driver()


@_driver.on_bot_connect
async def _on_qq_bot_connect(bot: Bot) -> None:
    """机器人连接成功时重置重连失败计数"""
    if bot.adapter.get_name() == "QQ":
        ReconnectMonitor.on_connected(bot.self_id)
