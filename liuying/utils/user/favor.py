"""用户好感度工具模块"""

from liuying.models._user.user_info import UserInfo

FAVER_LEVELS: dict[int, str] = {
    0: "陌生",
    1: "初识",
    2: "熟悉",
    3: "友好",
    4: "信任",
    5: "亲密",
    6: "挚友",
    7: "至交",
    8: "知己",
    9: "恋人",
}


class UserFavor:
    """用户好感度工具类"""

    @classmethod
    async def get_favor_value(cls, user_id: str) -> int:
        """
        获取用户好感度等级数值

        参数:
            user_id: 用户ID

        返回:
            int: 好感度等级数值
        """
        user = await UserInfo.get_user(user_id)
        return user.favor_value

    @classmethod
    async def get_favor_level(cls, user_id: str) -> str:
        """
        获取用户好感度等级名称

        参数:
            user_id: 用户ID

        返回:
            str: 好感度等级名称
        """
        favor_value = await cls.get_favor_value(user_id)
        return cls.get_favor_level_name(favor_value)

    @classmethod
    async def get_favor_info(cls, user_id: str) -> dict[str, int | str]:
        """
        获取用户好感度完整信息

        参数:
            user_id: 用户ID

        返回:
            dict[str, int | str]: 包含好感度数值和等级名称的字典
        """
        favor_value = await cls.get_favor_value(user_id)
        return {
            "favor_value": favor_value,
            "favor_level": cls.get_favor_level_name(favor_value),
        }

    @classmethod
    def get_favor_level_name(cls, favor_value: int) -> str:
        """
        根据好感度数值获取等级名称

        参数:
            favor_value: 好感度数值

        返回:
            str: 好感度等级名称
        """
        return FAVER_LEVELS.get(favor_value, FAVER_LEVELS[max(FAVER_LEVELS.keys())])
