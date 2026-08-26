from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.message import MessageUtils

from .config import LOG_COMMAND, RESOURCE_PACKS
from .data_source import ResourcePackManager

__plugin_meta__ = PluginMetadata(
    name="资源包管理",
    description="机器人资源包与 WebUI 资源管理",
    usage="""
    资源包管理        : 查看资源包安装状态
    资源包更新 [名称] : 更新指定资源包
    资源包更新全部    : 更新全部资源包
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna(
        "资源包管理",
        Subcommand("update", Args["name", str]),
        Subcommand("update_all"),
    ),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

_matcher.shortcut(
    r"资源包更新",
    command="资源包管理",
    arguments=["update", "{%0}"],
    prefix=True,
)

_matcher.shortcut(
    r"资源包更新全部",
    command="资源包管理",
    arguments=["update_all"],
    prefix=True,
)


@PriorityLifecycle.on_startup(priority=2)
async def _auto_download():
    """启动时自动下载资源包（优先级 2，晚于数据库与渲染服务）"""
    for meta in RESOURCE_PACKS:
        try:
            result = await ResourcePackManager.install(meta)
            logger.info(result, LOG_COMMAND)
        except Exception as e:
            logger.error(f"自动下载资源包 {meta.name} 失败: {e}", LOG_COMMAND, e=e)


@_matcher.assign("$main")
async def _(session: Uninfo):
    try:
        result = await ResourcePackManager.get_packs_info()
        logger.info("查看资源包状态", LOG_COMMAND, session=session)
        await MessageUtils.build_message("\n".join(result)).send()
    except Exception as e:
        logger.error(f"查看资源包状态失败: {e}", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message("获取资源包状态失败...").send()


@_matcher.assign("update")
async def _(session: Uninfo, name: str):
    meta = next((p for p in RESOURCE_PACKS if p.name == name), None)
    if meta is None:
        await MessageUtils.build_message(f"资源包 {name} 不存在").finish()
    try:
        result = await ResourcePackManager.install(meta)
        logger.info(f"更新资源包 {name}", LOG_COMMAND, session=session)
        await MessageUtils.build_message(result).send()
    except Exception as e:
        logger.error(f"更新资源包 {name} 失败", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message(f"更新资源包 {name} 失败 e: {e}").finish()


@_matcher.assign("update_all")
async def _(session: Uninfo):
    try:
        await MessageUtils.build_message("正在更新全部资源包").send()
        result = await ResourcePackManager.update_all()
        logger.info("更新全部资源包", LOG_COMMAND, session=session)
        await MessageUtils.build_message(result).send()
    except Exception as e:
        logger.error(f"更新全部资源包失败: {e}", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message(f"更新全部资源包失败 e: {e}").finish()
