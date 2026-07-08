"""流萤本体 WebUI 插件

流萤机器人本体的 WebUI 管理控制台。
提供前端界面 + 后端 API，覆盖本体运行总览、机器人账号、插件管理、
群组管理、定时任务、系统信息、日志查看、调用统计等功能。

不依赖 AI 插件，直接对接流萤本体核心数据（BotConsole / PluginInfo /
GroupConsole / task_manager / Statistics / 日志文件）。
通过 PriorityLifecycle 在本体核心初始化完成后挂载路由。
"""

from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData, PluginSetting
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .app import build_webui_router
from .config import PluginConfig, get_config
from .deps import register_runtime_context

__plugin_meta__ = PluginMetadata(
    name="流萤本体 WebUI",
    description=(
        "流萤机器人本体 WebUI 管理控制台：总览/机器人账号/插件/群组/"
        "定时任务/系统信息/日志/调用统计"
    ),
    usage="""
    访问 http://<bot地址>:<端口>/bot/ 打开本体 WebUI 控制台
    所有写操作需在请求中携带 auth_uid 参数（超级用户校验）
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.DEPENDANT,
        menu_type="管理",
        is_show=True,
        configs=PluginConfig,
        setting=PluginSetting(
            level=5,
            default_status=True,
            cost_gold=0,
            impression=0.0,
        ),
    ).to_dict(),
)

_PLUGIN_PRIORITY = 4
"""本体 WebUI 插件生命周期优先级（晚于本体核心 priority=2，确保 DB/调度器已就绪）"""


@PriorityLifecycle.on_startup(priority=_PLUGIN_PRIORITY)
async def _init_bot_webui_plugin() -> None:
    """本体 WebUI 插件初始化

    通过 PriorityLifecycle 注册，优先级=4，确保在本体核心（priority=2）
    完全初始化后再挂载 WebUI 路由，避免依赖的模型与调度器单例未就绪。

    启用条件：WEBUI_ENABLED 配置为 True。
    """
    if not get_config("WEBUI_ENABLED", False):
        logger.info(
            "本体 WebUI 已禁用（WEBUI_ENABLED=False）",
            command="Bot-WebUI",
        )
        return

    try:
        driver = get_driver()
    except Exception as e:
        logger.warning(
            f"本体 WebUI 获取 driver 失败: {e}",
            command="Bot-WebUI",
            e=e,
        )
        return

    server_app = getattr(driver, "server_app", None)
    if server_app is None:
        logger.warning(
            "当前驱动不支持 server_app，本体 WebUI 未挂载",
            command="Bot-WebUI",
        )
        return

    superusers = set(
        getattr(driver.config, "superusers", set()) or set()
    )
    route_prefix = str(get_config("WEBUI_ROUTE_PREFIX", "/bot") or "/bot")

    register_runtime_context(
        enabled=True,
        superusers=superusers,
        route_prefix=route_prefix,
    )

    try:
        router = build_webui_router(prefix=route_prefix)
        server_app.include_router(router)
        logger.info(
            f"本体 WebUI 路由已挂载到 {route_prefix}/*",
            command="Bot-WebUI",
        )
    except Exception as e:
        logger.warning(
            f"本体 WebUI 路由挂载失败: {e}",
            command="Bot-WebUI",
            e=e,
        )


@PriorityLifecycle.on_shutdown(priority=_PLUGIN_PRIORITY)
async def _shutdown_bot_webui_plugin() -> None:
    """本体 WebUI 插件关闭清理"""
    logger.info("本体 WebUI 插件已关闭", command="Bot-WebUI")


# 保留 driver 引用，便于其他模块通过本插件获取 driver 实例
_ = get_driver
