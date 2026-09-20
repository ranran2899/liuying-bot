import asyncio
import secrets

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
import nonebot
from nonebot.log import default_filter, default_format
from nonebot.plugin import PluginMetadata

from liuying.configs.config import Config as gConfig
from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.log import logger, logger_
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .api.configure import router as configure_router
from .api.logs import router as ws_log_routes
from .api.logs.log_manager import LOG_STORAGE
from .api.menu import router as menu_router
from .api.tabs.ai import router as ai_router
from .api.tabs.dashboard import router as dashboard_router
from .api.tabs.database import router as database_router
from .api.tabs.database.monitor import ws_router as db_monitor_ws_routes
from .api.tabs.main import router as main_router
from .api.tabs.main import ws_router as status_routes
from .api.tabs.manage import router as manage_router
from .api.tabs.manage.chat import ws_router as chat_routes
from .api.tabs.plugin_manage import router as plugin_router
from .api.tabs.plugin_manage.store import router as store_router
from .api.tabs.qqbot import router as qqbot_router
from .api.tabs.scheduler import router as scheduler_router
from .api.tabs.scheduler.monitor import ws_router as scheduler_monitor_ws_routes
from .api.tabs.system import router as system_router
from .auth import router as auth_router
from .public import init_public
from .registry import registry

__plugin_meta__ = PluginMetadata(
    name="web_ui",
    description="WebUi API",
    usage="""
    WebUi API
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.HIDDEN,
        configs=[
            RegisterConfig(
                module="web-ui",
                key="username",
                value="admin",
                help="前端管理用户名",
                type=str,
                default_value="admin",
            ),
            RegisterConfig(
                module="web-ui",
                key="password",
                value=None,
                help="前端管理密码",
                type=str,
                default_value=None,
            ),
            RegisterConfig(
                module="web-ui",
                key="secret",
                value=secrets.token_urlsafe(32),
                help="JWT密钥",
                type=str,
                default_value=None,
            ),
        ],
    ).to_dict(),
)


gConfig.set_name("web-ui", "web-ui")


BaseApiRouter = APIRouter(prefix="/liuying/api")


BaseApiRouter.include_router(auth_router)
BaseApiRouter.include_router(store_router)
BaseApiRouter.include_router(dashboard_router)
BaseApiRouter.include_router(main_router)
BaseApiRouter.include_router(manage_router)
BaseApiRouter.include_router(database_router)
BaseApiRouter.include_router(plugin_router)
BaseApiRouter.include_router(system_router)
BaseApiRouter.include_router(menu_router)
BaseApiRouter.include_router(configure_router)
BaseApiRouter.include_router(ai_router)
BaseApiRouter.include_router(qqbot_router)
BaseApiRouter.include_router(scheduler_router)

WsApiRouter = APIRouter(prefix="/liuying/socket")

WsApiRouter.include_router(ws_log_routes)
WsApiRouter.include_router(status_routes)
WsApiRouter.include_router(db_monitor_ws_routes)
WsApiRouter.include_router(scheduler_monitor_ws_routes)
WsApiRouter.include_router(chat_routes)


@PriorityLifecycle.on_startup(priority=1)
async def _():
    try:
        # 存储任务引用的列表，防止任务被垃圾回收
        _tasks = []

        async def log_sink(message: str):
            loop = None
            if not loop:
                try:
                    loop = asyncio.get_running_loop()
                except Exception as e:
                    logger.warning("Web Ui log_sink", command="WebUi", e=e)
            if not loop:
                loop = asyncio.new_event_loop()
            # 存储任务引用到外部列表中
            _tasks.append(loop.create_task(LOG_STORAGE.add(message.rstrip("\n"))))

        logger_.add(
            log_sink, colorize=True, filter=default_filter, format=default_format
        )

        app: FastAPI = nonebot.get_app()
        # 挂载外部插件注册的 API 与 WS 路由（插件导入阶段完成注册）
        for ext_router in registry.api_routers:
            BaseApiRouter.include_router(ext_router)
        for ext_router in registry.ws_routers:
            WsApiRouter.include_router(ext_router)
        # 清理已卸载插件残留的外部菜单项
        registry.sync_menus()
        app.include_router(BaseApiRouter)
        app.include_router(WsApiRouter)
        await init_public(app)
        # 挂载外部插件注册的静态资源目录
        for mount_path, directory in registry.static_mounts:
            if not directory.is_dir():
                logger.warning(
                    f"外部静态资源目录不存在，跳过挂载: {directory}",
                    command="WebUI",
                )
                continue
            app.mount(
                mount_path,
                StaticFiles(directory=directory, check_dir=True),
                name=f"ext_{mount_path.strip('/') or 'root'}",
            )
            logger.debug(f"挂载外部静态资源: {mount_path}", command="WebUI")
        logger.info("<g>API启动成功</g>", command="WebUi")
    except Exception as e:
        logger.error("<g>API启动失败</g>", command="WebUi", e=e)
