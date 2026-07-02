from nonebot import on_notice
from nonebot.adapters.onebot.v11 import GroupAdminNoticeEvent
from nonebot.plugin import PluginMetadata
from sqlalchemy import false

from liuying.configs.config import Config
from liuying.configs.utils.models import PluginExtraData, RegisterConfig
from liuying.models._user import UserLevel
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.rules import notice_rule

__plugin_meta__ = PluginMetadata(
    name="群管理员变动监测",
    description="当群内管理员变更时，自动设置/取消用户权限等级",
    usage="无需手动触发，自动运行",
    extra=PluginExtraData(
        author="Liuying",
        version="1.0",
        plugin_type=PluginType.HIDDEN,
        configs=[
            RegisterConfig(
                key="ADMIN_DEFAULT_AUTH",
                value=5,
                help="当用户成为群管理员时，自动设置的权限等级",
                default_value=5,
                type=int,
            ),
        ],
    ).to_dict(),
)

admin_notice = on_notice(
    priority=5,
    rule=notice_rule(GroupAdminNoticeEvent),
    block=False)


base_config = Config.get("admin_watch")


@admin_notice.handle()
async def _(event: GroupAdminNoticeEvent):
    match event.sub_type:
        case "set":
            admin_default_auth = base_config.get("ADMIN_DEFAULT_AUTH")
            if admin_default_auth is not None:
                await UserLevel.set_level(
                    str(event.user_id),
                    str(event.group_id),
                    admin_default_auth,
                )
                logger.info(
                    f"成为管理员，添加权限: {admin_default_auth}",
                    "群管理员变动监测",
                    session=event.user_id,
                    group_id=event.group_id,
                )
            else:
                logger.warning(
                    "配置项 MODULE: [<u><y>admin_bot_manage</y></u>] |"
                    " KEY: [<u><y>ADMIN_DEFAULT_AUTH</y></u>] 为空"
                )
        case "unset":
            await UserLevel.delete_level(str(event.user_id), str(event.group_id))
            logger.info(
                "撤销群管理员, 取消权限等级",
                "群管理员变动监测",
                session=event.user_id,
                group_id=event.group_id,
            )
