"""QQ适配器同步管理

负责QQ机器人配置与QQ适配器实例的同步操作:
- 添加/更新/移除适配器中的机器人配置
- 启动/断开WebSocket连接
- 查询适配器状态
"""

import asyncio
from typing import Any, ClassVar

import nonebot
from nonebot.adapters.qq.config import BotInfo, Intents

from liuying.utils.log import logger

from ._intent import DEFAULT_INTENT


def build_bot_info(config: dict[str, Any]) -> BotInfo:
    """从配置字典构建BotInfo对象

    意图配置与DEFAULT_INTENT合并,数据库旧配置缺失的新字段
    (如group_members)自动取默认值,用户显式配置优先

    参数:
        config: 配置字典

    返回:
        BotInfo: QQ适配器BotInfo对象
    """
    intent = {**DEFAULT_INTENT, **config.get("intent", {})}
    return BotInfo(
        id=config["bot_id"],
        token=config["token"],
        secret=config["secret"],
        intent=Intents(**intent),
        use_websocket=config.get("use_websocket", True),
    )


class QQAdapterManager:
    """QQ适配器同步管理器

    封装与QQ适配器实例的交互,提供机器人配置的同步操作,
    作为业务层与适配器之间的隔离层,便于测试和扩展
    """

    _adapter_instance: ClassVar[Any | None] = None
    """QQ适配器单例(延迟初始化,避免启动时序问题)"""

    @classmethod
    def _get_adapter(cls) -> Any:
        """获取QQ适配器实例(延迟初始化)

        返回:
            Any: QQ适配器实例
        """
        if cls._adapter_instance is None:
            cls._adapter_instance = nonebot.get_adapter("QQ")
        return cls._adapter_instance

    @classmethod
    def add_bot_to_config(cls, bot_info: BotInfo) -> bool:
        """将机器人配置添加到QQ适配器配置列表(不启动连接)

        用于启动阶段,由适配器startup自动遍历qq_bots启动连接

        参数:
            bot_info: BotInfo对象

        返回:
            bool: 是否添加成功(已存在则视为成功)
        """
        adapter = cls._get_adapter()
        if bot_info.id in {b.id for b in adapter.qq_config.qq_bots}:
            return True
        adapter.qq_config.qq_bots.append(bot_info)
        return True

    @classmethod
    def _start_websocket(cls, bot_info: BotInfo) -> None:
        """启动机器人的WebSocket连接

        参数:
            bot_info: BotInfo对象
        """
        adapter = cls._get_adapter()
        task = asyncio.create_task(adapter.run_bot_websocket(bot_info))
        task.add_done_callback(adapter.tasks.discard)
        adapter.tasks.add(task)
        logger.info(f"已启动机器人 {bot_info.id} 的WebSocket连接")

    @classmethod
    def _disconnect_bot(cls, bot_id: str) -> None:
        """断开机器人连接并取消所有相关任务

        同时处理已连接和从未连接成功的机器人,取消其所有
        WebSocket转发任务以停止无限重试

        参数:
            bot_id: 机器人ID
        """
        adapter = cls._get_adapter()
        cancelled = 0
        for task in list(adapter.tasks):
            if task.done():
                continue
            try:
                coro = task.get_coro()
                frame = coro.cr_frame if coro is not None else None
                bot = (
                    frame.f_locals.get("bot") if frame is not None else None
                )
                if bot is not None and getattr(
                    bot, "self_id", None
                ) == bot_id:
                    task.cancel()
                    cancelled += 1
            except (AttributeError, RuntimeError):
                continue
        if cancelled:
            logger.info(f"已取消机器人 {bot_id} 的 {cancelled} 个连接任务")
        if bot_id in adapter.bots:
            adapter.bot_disconnect(adapter.bots[bot_id])
            logger.info(f"已断开机器人 {bot_id} 的连接")

    @classmethod
    def sync_to_adapter(cls, bot_info: BotInfo) -> bool:
        """将机器人配置同步到QQ适配器并启动连接

        用于运行时动态添加或更新机器人配置。
        当配置发生变化时,会断开旧连接并使用新配置重连。

        参数:
            bot_info: BotInfo对象

        返回:
            bool: 是否同步成功
        """
        adapter = cls._get_adapter()
        qq_bots = adapter.qq_config.qq_bots

        idx = next(
            (i for i, b in enumerate(qq_bots) if b.id == bot_info.id),
            None,
        )

        if idx is None:
            qq_bots.append(bot_info)
            logger.info(
                f"已将机器人 {bot_info.id} 添加到QQ适配器配置列表"
            )
        else:
            if qq_bots[idx] == bot_info:
                return True
            qq_bots[idx] = bot_info
            logger.info(f"已更新机器人 {bot_info.id} 的QQ适配器配置")
            cls._disconnect_bot(bot_info.id)

        if bot_info.use_websocket:
            cls._start_websocket(bot_info)
        return True

    @classmethod
    def remove_from_adapter(cls, bot_id: str) -> bool:
        """从QQ适配器移除机器人配置

        参数:
            bot_id: 机器人ID

        返回:
            bool: 是否操作成功
        """
        adapter = cls._get_adapter()
        adapter.qq_config.qq_bots = [
            b for b in adapter.qq_config.qq_bots if b.id != bot_id
        ]
        cls._disconnect_bot(bot_id)
        return True

    @classmethod
    def get_online_bot_ids(cls) -> set[str]:
        """获取当前在线的QQ机器人ID集合

        返回:
            set[str]: 在线机器人ID集合
        """
        return set(cls._get_adapter().bots.keys())

    @classmethod
    def get_adapter_status(cls) -> dict[str, Any]:
        """获取QQ适配器状态

        返回:
            dict[str, Any]: 适配器状态信息
        """
        adapter = cls._get_adapter()
        return {
            "connected_bots": [
                {"id": bot_id, "adapter": adapter.get_name()}
                for bot_id in adapter.bots
            ],
            "configured_bots": [
                {"id": b.id, "use_websocket": b.use_websocket}
                for b in adapter.qq_config.qq_bots
            ],
        }
