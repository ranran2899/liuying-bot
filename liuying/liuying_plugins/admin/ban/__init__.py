from arclet.alconna import Args
from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Arparma,
    At,
    Match,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import (
    AICallableParam,
    AICallableProperties,
    AICallableTag,
    PluginExtraData,
)
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from ._data_source import BanManage

__plugin_meta__ = PluginMetadata(
    name="Ban",
    description="你被逮捕了！丢进小黑屋！封禁用户以及群组，屏蔽消息",
    usage="""
    普通管理员
        格式:
        ban [At用户] ?[-t [时长(分钟)]]

        示例:
        ban @用户          : 永久拉黑用户
        ban @用户 -t 100   : 拉黑用户100分钟
        unban @用户        : 从小黑屋中拉出来
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        admin_level=5,
        plugin_type=PluginType.SUPER_AND_ADMIN,
        smart_tools=[
            AICallableTag(
                name="ban_user",
                description=(
                    "封禁（拉黑）指定用户，使其无法使用机器人的任何功能；"
                    "需要调用人具备管理员等级（等级5及以上或超级用户），"
                    "且不能封禁自己；duration为分钟数，省略表示永久封禁"
                ),
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "user_id": AICallableProperties(
                            type="string",
                            description=(
                                "要封禁的用户ID，可从群成员信息工具获取"
                            ),
                        ),
                        "duration": AICallableProperties(
                            type="integer",
                            description=(
                                "封禁时长（分钟），省略表示永久封禁"
                            ),
                        ),
                    },
                    required=["user_id"],
                ),
                func=BanManage.smart_ban_user,
            ),
            AICallableTag(
                name="unban_user",
                description=(
                    "解除（解禁）指定用户的封禁，使其恢复正常使用机器人；"
                    "需要调用人具备管理员等级（等级5及以上或超级用户）"
                ),
                parameters=AICallableParam(
                    type="object",
                    properties={
                        "user_id": AICallableProperties(
                            type="string",
                            description=(
                                "要解禁的用户ID，可从群成员信息工具获取"
                            ),
                        ),
                    },
                    required=["user_id"],
                ),
                func=BanManage.smart_unban_user,
            ),
        ],
        superuser_help="""
        超级管理员额外命令
        格式:
        ban [At用户/用户Id] ?[-t [时长]]
        unban --id [idx]  : 通过id来进行unban操作
        ban列表: 获取所有Ban数据

        群组ban列表: 获取群组Ban数据
        用户ban列表: 获取用户Ban数据

        ban列表 -u [用户Id]: 查找指定用户ban数据
        ban列表 -g [群组Id]: 查找指定群组ban数据
        示例:
            ban列表 -u 123456789    : 查找用户123456789的ban数据
            ban列表 -g 123456789    : 查找群组123456789的ban数据

        私聊下:
            示例:
            ban 123456789          : 永久拉黑用户123456789
            ban 123456789 -t 100   : 拉黑用户123456789 100分钟

            ban -g 999999              : 拉黑群组为999999的群组
            ban -g 999999 -t 100       : 拉黑群组为999999的群组 100分钟

            unban 123456789     : 从小黑屋中拉出来
            unban -g 999999     : 将群组9999999从小黑屋中拉出来
        """,
    ).to_dict(),
)


def _resolve_target(user: Match[str | At]) -> str | None:
    """从 Match 中解析用户ID"""
    if not user.available:
        return None
    match user.result:
        case At() as at:
            return at.target
        case str() as s:
            return s
    return None


_ban_matcher = on_alconna(
    Alconna(
        "ban",
        Args["user?", [str, At]],
        Option("-g|--group", Args["group_id", str]),
        Option("-t|--time", Args["duration", int]),
    ),
    rule=admin_check(5),
    priority=5,
    block=True,
)

_unban_matcher = on_alconna(
    Alconna(
        "unban",
        Args["user?", [str, At]],
        Option("-g|--group", Args["group_id", str]),
        Option("--id", Args["idx", int]),
    ),
    rule=admin_check(5),
    priority=5,
    block=True,
)

_status_matcher = on_alconna(
    Alconna(
        "ban列表",
        Option("-u", Args["user_id", str], help_text="查找用户"),
        Option("-g", Args["group_id", str], help_text="查找群组"),
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@_ban_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    user: Match[str | At],
    group_id: Match[str],
    duration: Match[int],
):
    group_flag = group_id.available
    target_id = group_id.result if group_flag else _resolve_target(user)
    if not target_id:
        await MessageUtils.build_message("请输入要操作的用户或群组").finish(
            reply_to=True
        )

    result = await BanManage.ban(
        target_id,
        session,
        ban_level=1,
        duration=duration.result if duration.available else -1,
        is_group=group_flag,
    )

    await MessageUtils.build_message(result[1]).finish(reply_to=True)


@_unban_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
    arparma: Arparma,
    user: Match[str | At],
    group_id: Match[str],
    idx: Match[int],
):
    user_id = _resolve_target(user)
    target_group_id = group_id.result if group_id.available else None

    if not target_group_id and session.group and user_id:
        target_group_id = session.group.id

    is_superuser = session.user.id in bot.config.superusers

    result = await BanManage.unban(
        user_id,
        target_group_id,
        session,
        idx=idx.result if idx.available else None,
        is_superuser=is_superuser,
    )

    await MessageUtils.build_message(result[1]).finish(reply_to=True)


@_status_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    user_id: Match[str],
    group_id: Match[str],
):
    match (user_id.available, group_id.available, arparma.header_result):
        case (True, _, _):
            image = await BanManage.build_ban_image("user", user_id=user_id.result)
        case (_, True, _):
            image = await BanManage.build_ban_image("group", group_id=group_id.result)
        case (_, _, header) if "群组" in header:
            image = await BanManage.build_ban_image("group")
        case (_, _, header) if "用户" in header:
            image = await BanManage.build_ban_image("user")
        case _:
            image = await BanManage.build_ban_image(None)

    if image:
        await MessageUtils.build_message(image).finish(reply_to=True)
    await MessageUtils.build_message("暂无数据").finish(reply_to=True)
