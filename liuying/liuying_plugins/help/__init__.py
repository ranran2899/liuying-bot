"""
帮助插件主模块
"""
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaQuery,
    Args,
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

from .data_source import (
    create_help_image,
    get_plugin_help_detail,
    get_save_path,
)

__plugin_meta__ = PluginMetadata(
    name="帮助",
    description="查看插件功能帮助",
    usage="",
    extra=PluginExtraData(
        author="liuying",
        version="0.3",
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
        result = await get_plugin_help_detail(
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
    image_path = get_save_path(group_id, is_detail)
    if not image_path.exists():
        await create_help_image(session, group_id, is_detail)
    await MessageUtils.build_message(image_path).finish()
