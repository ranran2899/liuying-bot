from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import ensure_group

from ..help._render import build_superuser_help

__plugin_meta__ = PluginMetadata(
    name="超级用户帮助",
    description="超级用户帮助列表",
    usage="""
    超级用户帮助
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        plugin_type=PluginType.SUPERUSER,
        admin_level=9,
    ).to_dict(),
)


async def build_superuser_help_image(session: Uninfo, group_id: str | None) -> bytes:
    """构建超级用户帮助图片"""
    return await build_superuser_help(
        session=session, group_id=group_id, menu_title="超级用户帮助"
    )


_matcher = on_alconna(
    Alconna("超级用户帮助"),
    aliases={"superuser_help", "超级用户菜单"},
    permission=SUPERUSER,
    rule=ensure_group,
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
        image_bytes = await build_superuser_help_image(session, group_id)
        logger.info("查看超级用户帮助", arparma.header_result, session=session)
        await MessageUtils.build_message(image_bytes).send(reply_to=True)
    except Exception as e:
        logger.error(f"生成超级用户帮助失败: {e}", "超级用户帮助", session=session)
        await MessageUtils.build_message("生成超级用户帮助失败，请稍后再试...").finish(
            reply_to=True
        )
