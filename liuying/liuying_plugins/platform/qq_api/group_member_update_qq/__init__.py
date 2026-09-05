"""QQ官方适配器群成员信息更新插件

- 机器人被拉入群聊(GroupAddRobotEvent)时自动调用QQ开放平台
  /v2/groups/{group_openid}/members 接口拉取并更新群成员列表
- 支持管理员指令「更新群组成员信息」主动触发
"""

from nonebot import on_notice
from nonebot.adapters import Event
from nonebot.adapters.qq import Bot, GroupAddRobotEvent
from nonebot.adapters.qq import Event as QQEvent
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import adapter_in, admin_check, ensure_group, notice_rule

from .data_source import MemberUpdateManage

__plugin_meta__ = PluginMetadata(
    name="QQ官方群成员信息更新",
    description="QQ官方适配器群成员信息更新，机器人进群时自动拉取群成员列表",
    usage="""
    更新群组成员的基本信息
    指令：
        更新群组成员信息
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=1,
    ).to_dict(),
)


_matcher = on_alconna(
    Alconna("更新群组成员信息"),
    rule=admin_check(1) & ensure_group & notice_rule(QQEvent), 
    priority=5,
    block=True,
)


_group_add_robot = on_notice(priority=1, block=False, rule=notice_rule(QQEvent))


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma):
    if gid := session.group.id if session.group else None:
        logger.info("更新群组成员信息", arparma.header_result, session=session)
        result = await MemberUpdateManage.update_group_member(bot, gid)
        await MessageUtils.build_message(result).finish()
    await MessageUtils.build_message("群组id为空...").send()


@_group_add_robot.handle()
async def _(bot: Bot, event: Event):
    if isinstance(event, GroupAddRobotEvent):
        result = await MemberUpdateManage.update_group_member(
            bot, event.group_openid
        )
        logger.info(
            "机器人进群更新群成员信息",
            "QQ官方群成员信息更新",
            target=event.group_openid,
            result=result,
        )
