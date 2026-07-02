"""流萤AI WebUI 插件

独立的AI插件WebUI管理控制台，从AI插件本体分离。
提供前端界面 + 后端API，覆盖状态查询、配置管理、记忆查看、
运行时开关、人格管理、Token统计、视觉能力、知识库等功能。

依赖流萤AI插件的公开API（core模块单例），作为AI插件的扩展模块。
通过 PriorityLifecycle 在AI插件初始化完成后挂载路由。
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
    name="流萤AI WebUI",
    description=(
        "AI插件WebUI管理控制台：状态/配置/记忆/开关/人格/Token统计"
        "（依赖流萤AI插件）"
    ),
    usage="""
    访问 http://<bot地址>:<端口>/ai/ 打开WebUI控制台
    所有写操作需在请求中携带 user_id 参数（超级用户校验）
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.DEPENDANT,
        menu_type="AI",
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

_PLUGIN_PRIORITY = 3
"""AI WebUI插件生命周期优先级（晚于AI插件的2，确保AI插件核心已就绪）"""


@PriorityLifecycle.on_startup(priority=_PLUGIN_PRIORITY)
async def _init_ai_webui_plugin() -> None:
    """AI WebUI插件初始化

    通过 PriorityLifecycle 注册，优先级=3，确保在AI插件（priority=2）
    完全初始化后再挂载WebUI路由，避免依赖的core模块单例未就绪。

    启用条件：WEBUI_ENABLED 配置为 True。
    """
    if not get_config("WEBUI_ENABLED", False):
        logger.info(
            "AI WebUI已禁用（WEBUI_ENABLED=False）",
            command="AI-WebUI",
        )
        return

    try:
        driver = get_driver()
    except Exception as e:
        logger.warning(
            f"AI WebUI获取driver失败: {e}",
            command="AI-WebUI",
            e=e,
        )
        return

    server_app = getattr(driver, "server_app", None)
    if server_app is None:
        logger.warning(
            "当前驱动不支持server_app，AI WebUI未挂载",
            command="AI-WebUI",
        )
        return

    superusers = set(
        getattr(driver.config, "superusers", set()) or set()
    )
    route_prefix = str(get_config("WEBUI_ROUTE_PREFIX", "/ai") or "/ai")

    register_runtime_context(
        enabled=True,
        superusers=superusers,
        route_prefix=route_prefix,
    )

    try:
        router = build_webui_router(prefix=route_prefix)
        server_app.include_router(router)
        logger.info(
            f"AI WebUI路由已挂载到 {route_prefix}/*",
            command="AI-WebUI",
        )
    except Exception as e:
        logger.warning(
            f"AI WebUI路由挂载失败: {e}",
            command="AI-WebUI",
            e=e,
        )


@PriorityLifecycle.on_shutdown(priority=_PLUGIN_PRIORITY)
async def _shutdown_ai_webui_plugin() -> None:
    """AI WebUI插件关闭清理"""
    logger.info("AI WebUI插件已关闭", command="AI-WebUI")


# 保留 driver 引用，便于其他模块通过本插件获取 driver 实例
_ = get_driver
