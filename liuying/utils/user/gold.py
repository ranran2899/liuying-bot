
from liuying.models._user.user_info import UserInfo
from liuying.utils.exception import InsufficientGold


class UserGold:
    """用户金币工具类"""

    @classmethod
    async def get_user_gold(cls, user_id: str) -> int:
        """获取用户金币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前金币数量
        """
        return await UserInfo.get_user_gold(user_id)

    @classmethod
    async def add_user_gold(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None
        ) -> int:
        """增加用户金币

        参数:
            user_id: 用户ID
            amount: 增加的金币数量
            source: 金币来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前金币数量
        """
        await UserInfo.add_gold(
            user_id=user_id, gold=amount,
            source=source, platform=platform
        )
        return await UserInfo.get_user_gold(user_id)

    @classmethod
    async def reduce_user_gold(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None
    ) -> bool:
        """减少用户金币

        参数:
            user_id: 用户ID
            amount: 减少的金币数量
            source: 插件模块名，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserInfo.reduce_gold(
                user_id=user_id,
                gold=amount,
                plugin_module=source,
                platform=platform
            )
            return True
        except InsufficientGold:
            return False

    @classmethod
    async def set_user_gold(cls, user_id: str, amount: int) -> int:
        """设置用户金币

        参数:
            user_id: 用户ID
            amount: 设置的金币数量

        返回:
            int: 用户当前金币数量
        """
        user, _ = await UserInfo.get_or_create(user_id=str(user_id))
        user.gold = amount
        await user.save()
        return user.gold
