"""QQ机器人重连监控模块"""

import asyncio
from typing import ClassVar

import nonebot
from nonebot.adapters import Bot

from liuying.configs.config import Config
from liuying.models._bot.qq_bot_config import QQBotConfig
from liuying.utils.log import logger


class ReconnectMonitor:
    """QQ机器人重连监控器

    监控QQ机器人连接状态,当连续多次重连失败时自动删除配置,
    避免因令牌失效导致的无限重试
    """

    MAX_FAILURES: int = int(
        Config.get_config("qq_bot_config", "MAX_RECONNECT_FAILURES") or 3
    )
    """最大连续失败次数,超过此值自动删除配置"""

    CHECK_INTERVAL: float = 10.0
    """检查间隔(秒)"""

    _failures: ClassVar[dict[str, int]] = {}
    """机器人ID到连续失败次数的映射"""

    _task: ClassVar[asyncio.Task | None] = None
    """监控任务"""

    @classmethod
    def start(cls) -> None:
        """启动重连监控"""
        if cls._task is not None and not cls._task.done():
            return
        cls._task = asyncio.create_task(cls._loop())
        logger.info("QQ机器人重连监控已启动", "QQBotConfig")

    @classmethod
    def stop(cls) -> None:
        """停止重连监控"""
        if cls._task is not None and not cls._task.done():
            cls._task.cancel()
        cls._task = None
        cls._failures.clear()

    @classmethod
    def on_connected(cls, bot_id: str) -> None:
        """机器人连接成功时重置失败计数

        参数:
            bot_id: 机器人ID
        """
        cls._failures.pop(bot_id, None)

    @classmethod
    async def _loop(cls) -> None:
        """监控主循环"""
        while True:
            try:
                await asyncio.sleep(cls.CHECK_INTERVAL)
                await cls._check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"重连监控异常: {e}", "QQBotConfig", e=e)

    @classmethod
    async def _check(cls) -> None:
        """执行一次连接状态检查"""
        # 延迟导入: 与 _data_source 存在循环依赖
        # _data_source.QQBotConfigManager.delete_config 调用本类的 on_connected
        from ._data_source import _get_adapter

        try:
            adapter = _get_adapter()
        except Exception:
            return

        online_ids = set(adapter.bots.keys())
        configured_ids = {b.id for b in adapter.qq_config.qq_bots}

        for bot_id in configured_ids:
            if bot_id in online_ids:
                cls.on_connected(bot_id)
            else:
                count = cls._failures.get(bot_id, 0) + 1
                cls._failures[bot_id] = count
                if count >= cls.MAX_FAILURES:
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
        # 延迟导入: 与 _data_source 存在循环依赖
        from ._data_source import QQBotConfigManager

        cls._failures.pop(bot_id, None)
        config = await QQBotConfig.filter(bot_id=bot_id).first()
        if config is None:
            return
        success, _ = await QQBotConfigManager.delete_config(
            config.user_id, bot_id
        )
        if success:
            logger.warning(
                f"已自动删除机器人 {bot_id} 配置: 连续重连失败保护触发",
                "QQBotConfig",
            )


_driver = nonebot.get_driver()


@_driver.on_bot_connect
async def _on_qq_bot_connect(bot: Bot) -> None:
    """机器人连接成功时重置重连失败计数"""
    if bot.adapter.get_name() == "QQ":
        ReconnectMonitor.on_connected(bot.self_id)
