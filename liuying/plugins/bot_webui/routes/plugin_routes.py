"""插件管理路由

提供插件列表查询与按机器人账号启用/禁用插件。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from liuying.models._bot import BotConsole
from liuying.models.plugin_info import PluginInfo
from liuying.utils.enum import PluginType

from ..deps import require_auth

__all__ = ["build_plugin_router"]


def _plugin_to_view(plugin: PluginInfo) -> dict[str, Any]:
    """将 PluginInfo 转为视图字典"""
    return {
        "id": plugin.id,
        "module": plugin.module,
        "name": plugin.name,
        "status": plugin.status,
        "load_status": plugin.load_status,
        "block_type": plugin.block_type,
        "author": plugin.author,
        "version": plugin.version,
        "level": plugin.level,
        "menu_type": plugin.menu_type,
        "plugin_type": plugin.plugin_type,
        "cost_gold": plugin.cost_gold,
        "admin_level": plugin.admin_level,
        "is_show": plugin.is_show,
        "parent": plugin.parent,
    }


def build_plugin_router() -> APIRouter:
    """构建插件管理路由

    Returns:
        APIRouter: 插件管理路由器
    """
    router = APIRouter(prefix="/plugins", tags=["本体-插件管理"])

    @router.get("")
    async def list_plugins(
        load_status: bool | None = None,
        menu_type: str = "",
    ) -> dict[str, Any]:
        """获取插件列表

        参数:
            load_status: 加载状态过滤（True仅加载成功，False仅失败，None全部）
            menu_type: 菜单类型过滤

        返回:
            dict: 插件列表与统计
        """
        try:
            query = PluginInfo.filter(
                PluginInfo.plugin_type != PluginType.PARENT
            )
            if load_status is not None:
                query = query.filter(load_status=load_status)
            if menu_type:
                query = query.filter(menu_type=menu_type)
            plugins = await query.all()
            menu_types = sorted(
                {p.menu_type for p in plugins if p.menu_type}
            )
            return {
                "plugins": [_plugin_to_view(p) for p in plugins],
                "count": len(plugins),
                "menu_types": menu_types,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/bot/{bot_id}")
    async def list_plugins_for_bot(bot_id: str) -> dict[str, Any]:
        """获取指定机器人的插件启用/禁用状态

        参数:
            bot_id: 机器人ID

        返回:
            dict: 插件列表含该机器人的启用状态
        """
        try:
            bot = await BotConsole.filter(bot_id=bot_id).first()
            blocked = (
                set(BotConsole.convert_module_format(bot.block_plugins))
                if bot
                else set()
            )
            plugins = await PluginInfo.filter(
                PluginInfo.plugin_type != PluginType.PARENT,
                load_status=True,
            ).all()
            result = []
            for p in plugins:
                view = _plugin_to_view(p)
                view["enabled_for_bot"] = p.module not in blocked
                result.append(view)
            return {
                "bot_id": bot_id,
                "plugins": result,
                "count": len(result),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/toggle")
    async def toggle_plugin(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """启用/禁用指定机器人的插件

        请求体:
            bot_id: 机器人ID
            module: 插件模块名
            enabled: True启用 False禁用
        """
        bot_id = str(body.get("bot_id", "")).strip()
        module = str(body.get("module", "")).strip()
        enabled = bool(body.get("enabled", True))
        if not bot_id or not module:
            raise HTTPException(
                status_code=400, detail="bot_id 与 module 不能为空"
            )
        plugin = await PluginInfo.filter(module=module).first()
        if not plugin:
            raise HTTPException(
                status_code=404, detail=f"未找到插件: {module}"
            )
        try:
            if enabled:
                await BotConsole.enable_plugin(bot_id, module)
            else:
                await BotConsole.disable_plugin(bot_id, module)
            return {
                "ok": True,
                "bot_id": bot_id,
                "module": module,
                "enabled": enabled,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/toggle_all")
    async def toggle_all_plugins(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """启用/禁用指定机器人的全部插件

        请求体:
            bot_id: 机器人ID
            enabled: True全部启用 False全部禁用
        """
        bot_id = str(body.get("bot_id", "")).strip()
        enabled = bool(body.get("enabled", True))
        if not bot_id:
            raise HTTPException(
                status_code=400, detail="bot_id 不能为空"
            )
        try:
            if enabled:
                await BotConsole.enable_all(bot_id, "plugins")
            else:
                await BotConsole.disable_all(bot_id, "plugins")
            return {
                "ok": True,
                "bot_id": bot_id,
                "enabled": enabled,
                "scope": "all_plugins",
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
