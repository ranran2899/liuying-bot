import httpx
from nonebot.adapters import Bot
from nonebot_plugin_uninfo import SceneType, get_interface
from nonebot_plugin_uninfo.model import Member

from liuying.models._group import GroupConsole
from liuying.utils.log import logger
from liuying.utils.platform.helper import PlatformUtils
from liuying.utils.platform.models import UserData, build_user_data


class GroupUtils:
    """群组工具类"""

    @classmethod
    async def get_group_member_list(cls, bot: Bot, group_id: str) -> list[UserData]:
        """获取群组/频道成员列表

        参数:
            bot: Bot
            group_id: 群组/频道id

        返回:
            list[UserData]: 用户数据列表
        """
        if not (interface := get_interface(bot)):
            return []
        members: list[Member] = await interface.get_members(SceneType.GROUP, group_id)
        return [build_user_data(m.user, m, group_id=group_id) for m in members]

    @classmethod
    async def update_group(cls, bot: Bot) -> int:
        """更新群组信息

        参数:
            bot: Bot

        返回:
            int: 更新个数
        """
        group_list, platform = await cls.get_group_list(bot)
        if not group_list:
            return 0
        db_groups = {
            (g.group_id, g.channel_id): g
            for g in await GroupConsole.filter().all()
        }
        create_list, update_list = [], []
        for group in group_list:
            group.platform = platform
            if db_group := db_groups.get((group.group_id, group.channel_id)):
                db_group.group_name = group.group_name
                db_group.max_member_count = group.max_member_count
                db_group.member_count = group.member_count
                update_list.append(db_group)
            else:
                create_list.append(group)
                logger.debug(
                    "群聊信息更新成功",
                    command="更新群信息",
                    target=f"{group.group_id}:{group.channel_id}",
                )
        if create_list:
            await GroupConsole.filter().bulk_create(create_list)
        if update_list:
            await GroupConsole.filter().bulk_update(
                update_list, ["group_name", "max_member_count", "member_count"]
            )
        return len(create_list)

    @classmethod
    async def get_group_list(
        cls, bot: Bot, only_group: bool = False
    ) -> tuple[list[GroupConsole], str]:
        """获取群组列表

        参数:
            bot: Bot
            only_group: 是否只获取群组（不获取channel）

        返回:
            tuple[list[GroupConsole], str]: 群组列表, 平台
        """
        if not (interface := get_interface(bot)):
            return [], ""
        platform = PlatformUtils.get_platform(bot)
        result_list = []
        for scene in await interface.get_scenes(SceneType.GROUP):
            result_list.append(
                GroupConsole(group_id=scene.id, group_name=scene.name)
            )
            if (
                not only_group
                and platform != "qq"
                and (
                    channel_list := await interface.get_scenes(
                        parent_scene_id=scene.id
                    )
                )
            ):
                result_list.extend(
                    GroupConsole(
                        group_id=scene.id,
                        group_name=channel.name,
                        channel_id=channel.id,
                    )
                    for channel in channel_list
                )
        return result_list, platform

    @classmethod
    async def get_group_avatar(cls, gid: str, platform: str) -> bytes | None:
        """快捷获取群头像

        参数:
            gid: 群组id
            platform: 平台

        返回:
            bytes | None: 群头像数据
        """
        if platform != "qq":
            return None
        url = f"http://p.qlogo.cn/gh/{gid}/{gid}/640/"
        async with httpx.AsyncClient() as client:
            for _ in range(3):
                try:
                    return (await client.get(url)).content
                except Exception:
                    logger.error(
                        "获取群头像错误",
                        command="Util",
                        target=gid,
                        platform=platform,
                    )
        return None
