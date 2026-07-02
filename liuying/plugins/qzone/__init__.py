"""流萤AI QZone 工具插件

QQ空间协议封装 + Agent工具 + 管理命令 + WebUI。
依赖流萤AI插件的公开API（register_external_tool）注册工具。

本插件从流萤AI插件独立出来，降低AI插件维护成本，
便于第三方独立维护QQ空间协议封装。
"""

from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import Command, PluginExtraData, PluginSetting
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from . import tools  # noqa: F401  触发Agent工具注册（register_external_tool装饰器）
from .commands import setup_qzone_commands
from .config import PluginConfig, get_config
from .service import qzone_service
from .webui import register_qzone_webui

__plugin_meta__ = PluginMetadata(
    name="流萤AI空间工具",
    description=(
        "QQ空间协议封装 + Agent工具 + 管理命令 + WebUI"
        "（依赖流萤AI插件公开API）"
    ),
    usage="""
    流萤AI空间 [set|clear] --p_skey xxx --uin xxx - 配置QZone cookie
    流萤AI空间状态 - 查看QZone状态
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
        commands=[
            Command(
                command="流萤AI空间 [set|clear]",
                description="配置QZone cookie（高级管理员）",
            ),
            Command(
                command="流萤AI空间状态",
                description="查看QZone状态（管理员）",
            ),
        ],
    ).to_dict(),
)

_PLUGIN_PRIORITY = 3
"""QZone插件生命周期优先级（晚于AI插件的2，确保tool_registry就绪）"""

# 注册管理命令（on_alconna在模块导入时执行）
setup_qzone_commands()


@PriorityLifecycle.on_startup(priority=_PLUGIN_PRIORITY)
async def _init_qzone_plugin() -> None:
    """QZone插件初始化

    通过 PriorityLifecycle 注册，优先级=3，确保在AI插件（priority=2）
    完全初始化后再挂载WebUI，避免driver未就绪。
    """
    if get_config("QZONE_ENABLED", False):
        register_qzone_webui()
        logger.info(
            "QZone插件初始化完成（WebUI已挂载）",
            command="QZone",
        )
    else:
        logger.info(
            "QZone插件初始化完成（QZONE_ENABLED=False，WebUI未挂载）",
            command="QZone",
        )


@PriorityLifecycle.on_shutdown(priority=_PLUGIN_PRIORITY)
async def _shutdown_qzone_plugin() -> None:
    """QZone插件关闭清理

    关闭QZone httpx客户端，避免连接泄漏。
    """
    try:
        await qzone_service.close()
    except Exception as e:
        logger.debug(
            f"QZone服务关闭失败: {e}",
            command="QZone",
            e=e,
        )
    logger.info("QZone插件已关闭", command="QZone")


# 保留 get_driver 引用，便于WebUI模块直接获取driver
_ = get_driver
