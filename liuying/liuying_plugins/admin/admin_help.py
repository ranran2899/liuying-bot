from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check, ensure_group

from ..help._render import build_admin_help

__plugin_meta__ = PluginMetadata(
    name="管理员帮助",
    description="管理员帮助列表",
    usage="""
    管理员帮助
    """.strip(),
    extra=PluginExtraData(
        author="流萤",
        version="1.0",
        plugin_type=PluginType.ADMIN,
        admin_level=1,
    ).to_dict(),
)


async def build_admin_help_image(session: Uninfo, group_id: str | None) -> bytes:
    """构建管理员帮助图片"""
    return await build_admin_help(
        session=session, group_id=group_id, menu_title="群管理员帮助"
    )


_matcher = on_alconna(
    Alconna("管理员帮助"),
    aliases={"admin_help", "管理员菜单"},
    rule=admin_check(1) & ensure_group,
    priority=5,
    block=True,
)


@_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
):
    try:
        group_id = session.group.id if session.group else None
        image_bytes = await build_admin_help_image(session, group_id)
        logger.info("查看管理员帮助", arparma.header_result, session=session)
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except Exception as e:
        logger.error(f"生成管理员帮助失败: {e}", "管理员帮助", session=session)
        await MessageUtils.build_message("生成管理员帮助失败，请稍后再试...").finish(
            reply_to=True
        )
