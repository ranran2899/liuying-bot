"""用户其他货币工具类"""

from liuying.models._user.user_curr import UserCurr
from liuying.utils.exception import (
    InsufficientCopper,
    InsufficientDiamond,
    InsufficientSilver,
    InsufficientTianrew,
    InsufficientXingqiong,
    InsufficientYuanshi,
)


class UserCurrUtils:
    """用户其他货币工具类"""

    @classmethod
    async def get_user_copper(cls, user_id: str) -> int:
        """获取用户铜币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前铜币数量
        """
        return await UserCurr.get_user_copper(user_id)

    @classmethod
    async def add_user_copper(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户铜币

        参数:
            user_id: 用户ID
            amount: 增加的铜币数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前铜币数量
        """
        await UserCurr.add_copper(
            user_id=user_id, copper=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_copper(user_id)

    @classmethod
    async def reduce_user_copper(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户铜币

        参数:
            user_id: 用户ID
            amount: 减少的铜币数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_copper(
                user_id=user_id, copper=amount, source=source, platform=platform
            )
            return True
        except InsufficientCopper:
            return False

    @classmethod
    async def get_user_silver(cls, user_id: str) -> int:
        """获取用户银币

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前银币数量
        """
        return await UserCurr.get_user_silver(user_id)

    @classmethod
    async def add_user_silver(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户银币

        参数:
            user_id: 用户ID
            amount: 增加的银币数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前银币数量
        """
        await UserCurr.add_silver(
            user_id=user_id, silver=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_silver(user_id)

    @classmethod
    async def reduce_user_silver(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户银币

        参数:
            user_id: 用户ID
            amount: 减少的银币数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_silver(
                user_id=user_id, silver=amount, source=source, platform=platform
            )
            return True
        except InsufficientSilver:
            return False

    @classmethod
    async def get_user_diamond(cls, user_id: str) -> int:
        """获取用户钻石

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前钻石数量
        """
        return await UserCurr.get_user_diamond(user_id)

    @classmethod
    async def add_user_diamond(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户钻石

        参数:
            user_id: 用户ID
            amount: 增加的钻石数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前钻石数量
        """
        await UserCurr.add_diamond(
            user_id=user_id, diamond=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_diamond(user_id)

    @classmethod
    async def reduce_user_diamond(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户钻石

        参数:
            user_id: 用户ID
            amount: 减少的钻石数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_diamond(
                user_id=user_id, diamond=amount, source=source, platform=platform
            )
            return True
        except InsufficientDiamond:
            return False

    @classmethod
    async def get_user_xingqiong(cls, user_id: str) -> int:
        """获取用户星琼

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前星琼数量
        """
        return await UserCurr.get_user_xingqiong(user_id)

    @classmethod
    async def add_user_xingqiong(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户星琼

        参数:
            user_id: 用户ID
            amount: 增加的星琼数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前星琼数量
        """
        await UserCurr.add_xingqiong(
            user_id=user_id, xingqiong=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_xingqiong(user_id)

    @classmethod
    async def reduce_user_xingqiong(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户星琼

        参数:
            user_id: 用户ID
            amount: 减少的星琼数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_xingqiong(
                user_id=user_id, xingqiong=amount, source=source, platform=platform
            )
            return True
        except InsufficientXingqiong:
            return False

    @classmethod
    async def get_user_yuanshi(cls, user_id: str) -> int:
        """获取用户原石

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前原石数量
        """
        return await UserCurr.get_user_yuanshi(user_id)

    @classmethod
    async def add_user_yuanshi(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户原石

        参数:
            user_id: 用户ID
            amount: 增加的原石数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前原石数量
        """
        await UserCurr.add_yuanshi(
            user_id=user_id, yuanshi=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_yuanshi(user_id)

    @classmethod
    async def reduce_user_yuanshi(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户原石

        参数:
            user_id: 用户ID
            amount: 减少的原石数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_yuanshi(
                user_id=user_id, yuanshi=amount, source=source, platform=platform
            )
            return True
        except InsufficientYuanshi:
            return False

    @classmethod
    async def get_user_tianrew(cls, user_id: str) -> int:
        """获取用户天赏点

        参数:
            user_id: 用户ID

        返回:
            int: 用户当前天赏点数量
        """
        return await UserCurr.get_user_tianrew(user_id)

    @classmethod
    async def add_user_tianrew(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> int:
        """增加用户天赏点

        参数:
            user_id: 用户ID
            amount: 增加的天赏点数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            int: 用户当前天赏点数量
        """
        await UserCurr.add_tianrew(
            user_id=user_id, tianrew=amount, source=source, platform=platform
        )
        return await UserCurr.get_user_tianrew(user_id)

    @classmethod
    async def reduce_user_tianrew(
        cls,
        user_id: str,
        amount: int,
        source: str | None = None,
        platform: str | None = None,
    ) -> bool:
        """减少用户天赏点

        参数:
            user_id: 用户ID
            amount: 减少的天赏点数量
            source: 来源，默认为None
            platform: 平台，默认为None

        返回:
            bool: 是否减少成功
        """
        try:
            await UserCurr.reduce_tianrew(
                user_id=user_id, tianrew=amount, source=source, platform=platform
            )
            return True
        except InsufficientTianrew:
            return False
