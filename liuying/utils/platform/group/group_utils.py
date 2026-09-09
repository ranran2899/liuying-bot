import httpx
from nonebot.adapters import Bot

from liuying.models._group import GroupConsole
from liuying.utils.log import logger
from liuying.utils.platform.group.group_list import GroupListUtils


class GroupUtils:
    """群组工具类"""

    @classmethod
    async def update_group(cls, bot: Bot) -> int:
        """更新群组信息

        参数:
            bot: Bot

        返回:
            int: 更新个数
        """
        group_list, platform = await GroupListUtils.get_group_list(bot)
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
