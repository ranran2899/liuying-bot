"""本体状态总览路由

提供流萤机器人本体运行状态概览：版本、昵称、在线账号、各资源计数。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from nonebot import get_bots

from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.utils.bot.version import BotVersionInfo, get_bot_name
from liuying.utils.apscheduler.manager import task_manager

__all__ = ["build_status_router"]


def build_status_router() -> APIRouter:
    """构建状态总览路由"""
    router = APIRouter(prefix="/status", tags=["WebUI-状态总览"])

    @router.get("")
    async def status() -> dict[str, Any]:
        """获取本体运行状态概览"""
        version = await BotVersionInfo.get_version()
        name = await get_bot_name()

        online_bots = list(get_bots().keys())
        bot_count = await BotConsole.filter().count()
        plugin_count = await PluginInfo.filter(load_status=True).count()
        group_count = await GroupConsole.filter().count()
        task_count = len(task_manager.get_all_tasks())

        return {
            "bot_name": name,
            "bot_version": version,
            "online_bots": online_bots,
            "online_count": len(online_bots),
            "bot_account_count": bot_count,
            "plugin_count": plugin_count,
            "group_count": group_count,
            "task_count": task_count,
            "scheduler_started": getattr(task_manager, "_started", False),
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/bots")
    async def online_bots() -> dict[str, Any]:
        """获取当前在线（已连接）的机器人账号列表"""
        bots = get_bots()
        result = []
        for bot_id, bot in bots.items():
            adapter = getattr(bot, "adapter", None)
            adapter_name = (
                getattr(adapter, "get_name", lambda: "")()
                if adapter
                else ""
            )
            result.append(
                {
                    "bot_id": bot_id,
                    "adapter": adapter_name,
                    "self_id": getattr(bot, "self_id", bot_id),
                }
            )
        return {"bots": result, "count": len(result)}

    return router
