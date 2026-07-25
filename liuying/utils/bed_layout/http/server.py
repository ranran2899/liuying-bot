"""
床图HTTP服务注册模块

通过 nonebot.get_app() 获取 FastAPI 应用，将床图路由
注册到 nonebot2 框架统一端口，避免独立服务端口冲突。
"""
from fastapi import FastAPI
import nonebot

from liuying.utils.bed_layout.http.config import ROUTE_PREFIX
from liuying.utils.bed_layout.http.handlers import router as bed_layout_router
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle


class BedLayoutServer:
    """
    床图HTTP服务注册器

    通过 nonebot2 框架统一端口注册路由，
    不再启动独立的 aiohttp 服务器，避免端口冲突。
    """

    _registered: bool = False

    @classmethod
    async def register_routes(cls) -> None:
        """注册床图路由到 nonebot2 FastAPI 应用

        通过 ROUTE_PREFIX 前缀隔离路由，避免与其他模块冲突
        """
        if cls._registered:
            return

        app: FastAPI = nonebot.get_app()
        app.include_router(bed_layout_router, prefix=ROUTE_PREFIX)
        cls._registered = True
        logger.info(
            f"床图路由已注册至 nonebot2 统一端口 | 前缀: {ROUTE_PREFIX}",
            "BedLayoutServer",
        )


@PriorityLifecycle.on_startup(priority=2)
async def _register_server():
    """在Bot启动时将床图路由注册到 nonebot2 应用"""
    await BedLayoutServer.register_routes()
