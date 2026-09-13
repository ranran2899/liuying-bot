"""流萤AI QZone 工具插件

QQ空间协议封装 + Agent工具 + 管理命令 + WebUI。
通过 PluginExtraData.smart_tools 声明智能工具，由 AI 插件 SmartToolBridge 自动注册。
不直接导入 AI 插件的任何模块。
"""

from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import (
    AICallableParam,
    AICallableProperties,
    AICallableTag,
    Command,
    PluginExtraData,
    PluginSetting,
)
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .commands import setup_qzone_commands
from .config import PluginConfig, get_config
from .service import qzone_service
from .tools import qzone_feeds, qzone_like, qzone_publish
from .webui import register_qzone_webui

__plugin_meta__ = PluginMetadata(
    name="流萤AI空间工具",
    description=(
        "QQ空间协议封装 + Agent工具 + 管理命令 + WebUI"
        "（通过smart_tools声明，由AI插件自动桥接）"
    ),
    usage="""
    流萤AI空间 [set|clear] --p_skey xxx --uin xxx - 配置QZone cookie
    流萤AI空间状态 - 查看QZone状态
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.DEPENDANT,
        menu_type="AI",
        is_show=False,
        configs=PluginConfig,
        setting=PluginSetting(
            level=5,
            default_status=True,
            cost_gold=0,
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
        smart_tools=[
            AICallableTag(
                name="qzone_publish",
                description=(
                    "发布QQ空间说说（需管理员预先配置QZone cookie），"
                    "适用于自己主动发表心情/动态/想法时"
                ),
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "content": AICallableProperties(
                            type="string",
                            description="说说正文内容",
                        ),
                        "visible": AICallableProperties(
                            type="integer",
                            description="可见性：0=公开 1=好友 2=私密",
                        ),
                    },
                    required=["content"],
                ),
                func=qzone_publish,
                intent_tags=["admin", "network"],
                latency_class="network",
                requires_network=True,
                metadata={"requires_admin": True},
            ),
            AICallableTag(
                name="qzone_feeds",
                description=(
                    "拉取QQ空间好友动态列表，"
                    "返回结果中每条动态都会标明 feed_id 和 owner_uin，"
                    "供 qzone_like 等工具使用"
                ),
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "count": AICallableProperties(
                            type="integer",
                            description="拉取数量，默认10，最大20",
                        ),
                    },
                    required=[],
                ),
                func=qzone_feeds,
                intent_tags=["network", "realtime"],
                latency_class="network",
                requires_network=True,
                metadata={"requires_admin": True},
            ),
            AICallableTag(
                name="qzone_like",
                description=(
                    "对指定QQ空间动态点赞，"
                    "feed_id 和 owner_uin 必须从 qzone_feeds 返回结果中对应字段提取，"
                    "适用于自己表达对好友动态的支持时"
                ),
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "feed_id": AICallableProperties(
                            type="string",
                            description="动态ID，从 qzone_feeds 结果中的 feed_id 字段获取",
                        ),
                        "owner_uin": AICallableProperties(
                            type="string",
                            description=(
                                "动态所有者QQ号，"
                                "从 qzone_feeds 结果中的 owner_uin 字段获取"
                            ),
                        ),
                    },
                    required=["feed_id", "owner_uin"],
                ),
                func=qzone_like,
                intent_tags=["network", "admin"],
                latency_class="network",
                requires_network=True,
                metadata={"requires_admin": True},
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
