from nonebot.adapters import Bot
from nonebot_plugin_uninfo import SceneType, get_interface
from nonebot_plugin_uninfo.model import Member

from liuying.utils.platform.models import UserData, build_user_data


class MemberListUtils:
    """群成员列表工具类"""

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
