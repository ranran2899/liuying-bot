"""机器人账号管理路由

提供 BotConsole 账号列表与状态切换。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from nonebot import get_bots

from liuying.models._bot import BotConsole

from ..deps import require_superuser

__all__ = ["build_bot_router"]


def _convert_count(raw: str) -> int:
    """统计 BotConsole 中 `<a,<b,` 格式字符串的条目数

    参数:
        raw: 原始字符串

    返回:
        int: 条目数
    """
    if not raw:
        return 0
    return len([s for s in raw.split("<") if s.strip(",")])


def _bot_to_view(bot: BotConsole, online_ids: set[str]) -> dict[str, Any]:
    """将 BotConsole 转为视图字典"""
    create_time = ""
    if bot.create_time:
        try:
            create_time = (
                bot.create_time.isoformat()
                if hasattr(bot.create_time, "isoformat")
                else str(bot.create_time)
            )
        except Exception:
            create_time = str(bot.create_time)
    return {
        "bot_id": bot.bot_id,
        "status": bot.status,
        "platform": bot.platform or "",
        "create_time": create_time,
        "online": bot.bot_id in online_ids,
        "available_plugins": _convert_count(bot.available_plugins),
        "block_plugins": _convert_count(bot.block_plugins),
        "available_tasks": _convert_count(bot.available_tasks),
        "block_tasks": _convert_count(bot.block_tasks),
    }


def build_bot_router() -> APIRouter:
    """构建机器人账号管理路由

    Returns:
        APIRouter: 机器人账号管理路由器
    """
    router = APIRouter(prefix="/bots", tags=["本体-机器人账号"])

    @router.get("")
    async def list_bots() -> dict[str, Any]:
        """获取全部机器人账号列表（含在线状态与插件/被动计数）"""
        try:
            bots = await BotConsole.filter().all()
            online_ids = set(get_bots().keys())
            return {
                "bots": [_bot_to_view(b, online_ids) for b in bots],
                "count": len(bots),
                "online_count": sum(
                    1 for b in bots if b.bot_id in online_ids
                ),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/status")
    async def set_bot_status(
        bot_id: str,
        status: bool,
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """切换机器人账号状态

        参数:
            bot_id: 机器人ID（为空时切换全部）
            status: 目标状态
        """
        try:
            await BotConsole.set_bot_status(status, bot_id or None)
            return {
                "ok": True,
                "bot_id": bot_id or "all",
                "status": status,
            }
        except ValueError as e:
            raise HTTPException(
                status_code=404, detail=str(e)
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/{bot_id}")
    async def bot_detail(bot_id: str) -> dict[str, Any]:
        """获取单个机器人账号详情"""
        try:
            bot = await BotConsole.filter(bot_id=bot_id).first()
            if not bot:
                raise HTTPException(
                    status_code=404, detail=f"未找到机器人: {bot_id}"
                )
            online_ids = set(get_bots().keys())
            data = _bot_to_view(bot, online_ids)
            data["available_plugins_list"] = BotConsole.convert_module_format(
                bot.available_plugins
            )
            data["block_plugins_list"] = BotConsole.convert_module_format(
                bot.block_plugins
            )
            data["available_tasks_list"] = BotConsole.convert_module_format(
                bot.available_tasks
            )
            data["block_tasks_list"] = BotConsole.convert_module_format(
                bot.block_tasks
            )
            return data
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
