"""
帮助插件主模块
"""
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
    Arparma,
    Match,
    Option,
    Query,
    on_alconna,
    store_true,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check, ensure_group

from .data_source import HelpManage
from .render import HelpRender

__plugin_meta__ = PluginMetadata(
    name="帮助",
    description="查看插件功能帮助",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.5",
        plugin_type=PluginType.DEPENDANT,
        is_show=False,
        configs=[
            RegisterConfig(
                key="type",
                value="liuying",
                help="帮助图片样式 [liuying]",
                default_value="liuying",
            ),
            RegisterConfig(
                key="detail_type",
                value="liuying",
                help="帮助详情图片样式 ['liuying']",
                default_value="liuying",
            )
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna(
        "功能",
        Args["name?", str],
        Option("-s|--superuser", action=store_true, help_text="超级用户帮助"),
        Option("-d|--detail", action=store_true, help_text="详细帮助"),
    ),
    aliases={"help", "帮助", "菜单", "/功能", "/帮助", "/菜单"},
    rule=to_me(),
    priority=1,
    block=True,
)

_matcher.shortcut(
    r"详细帮助",
    command="功能",
    arguments=["--detail"],
    prefix=True,
)

_admin_help_matcher = on_alconna(
    Alconna("管理员帮助"),
    aliases={"admin_help", "管理员菜单"},
    rule=admin_check(1) & ensure_group,
    priority=5,
    block=True,
)

_superuser_help_matcher = on_alconna(
    Alconna("超级用户帮助"),
    aliases={"superuser_help", "超级用户菜单"},
    permission=SUPERUSER,
    rule=admin_check(9),
    priority=5,
    block=True,
)


@_matcher.handle()
async def _(
    bot: Bot,
    name: Match[str],
    session: Uninfo,
    is_superuser: Query[bool] = AlconnaQuery("superuser.value", False),
    is_detail: Query[bool] = AlconnaQuery("detail.value", False),
):
    """
    帮助命令处理器

    参数:
        bot: Bot实例
        name: 插件名称匹配
        session: 会话信息
        is_superuser: 是否超级用户帮助
        is_detail: 是否详细帮助
    """
    if name.available:
        result = await HelpManage.get_plugin_help_detail(
            session.user.id, name.result, is_superuser.result
        )
        await MessageUtils.build_message(result).send(reply_to=True)

        if isinstance(result, str) and "没有查找到这个功能噢..." in result:
            logger.info(
                f"查看帮助详情失败，未找到: {name.result}",
                "帮助",
                session=session,
            )
        else:
            logger.info(f"查看帮助详情: {name.result}", "帮助", session=session)
        return

    if session.group and (gid := session.group.id):
        await _send_help_image(session, gid, is_detail.result)
    else:
        await _send_help_image(session, None, is_detail.result)


@_admin_help_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    await _send_menu_help(
        session,
        arparma,
        "管理员帮助",
        "群管理员帮助",
        [PluginType.ADMIN, PluginType.SUPER_AND_ADMIN],
    )


@_superuser_help_matcher.handle()
async def _(session: Uninfo, arparma: Arparma):
    await _send_menu_help(
        session, arparma, "超级用户帮助", "超级用户帮助", [PluginType.SUPERUSER]
    )


async def _send_help_image(
    session: Uninfo, group_id: str | None, is_detail: bool
) -> None:
    """
    发送帮助菜单图片，不存在时先生成

    参数:
        session: 会话信息
        group_id: 群号，私聊时为 None
        is_detail: 是否详细帮助
    """
    image_path = HelpManage.get_save_path(group_id, is_detail)
    if not image_path.exists():
        await HelpManage.create_help_image(session, group_id, is_detail)
    await MessageUtils.build_message(image_path).finish()


async def _send_menu_help(
    session: Uninfo,
    arparma: Arparma,
    cmd: str,
    menu_title: str,
    plugin_types: list[PluginType],
) -> None:
    """
    构建并发送角色帮助菜单图片，失败时发送提示

    参数:
        session: 会话信息
        arparma: 命令解析结果
        cmd: 命令名称，用于日志与提示
        menu_title: 菜单标题
        plugin_types: 插件类型列表
    """
    group_id = session.group.id if session.group else None
    try:
        image_bytes = await HelpRender.build(
            session=session,
            group_id=group_id,
            is_detail=True,
            plugin_types=plugin_types,
            menu_title=menu_title,
        )
        logger.info(f"查看{cmd}", arparma.header_result, session=session)
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except Exception as e:
        logger.error(f"生成{cmd}失败: {e}", cmd, session=session)
        await MessageUtils.build_message(f"生成{cmd}失败，请稍后再试...").finish(
            reply_to=True
        )
