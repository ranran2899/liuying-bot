"""用户经验工具模块"""

from liuying.models._user.user_exp import UserExpInfo


class UserExp:
    """用户经验工具类"""

    @classmethod
    async def get_user_exp(cls, user_id: str) -> UserExpInfo:
        """
        获取用户经验信息

        参数:
            user_id: 用户ID

        返回:
            UserExpInfo: 用户经验信息
        """
        return await UserExpInfo.get_user_exp(user_id)

    @classmethod
    async def add_level_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """
        添加等级经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前等级, 当前经验, 是否升级)
        """
        return await UserExpInfo.add_level_exp(user_id, exp)

    @classmethod
    async def add_favor_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """
        添加好感度经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前好感度等级, 当前经验, 是否升级)
        """
        return await UserExpInfo.add_favor_exp(user_id, exp)

    @classmethod
    async def reduce_level_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """
        减少等级经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前等级, 当前经验, 是否降级)
        """
        return await UserExpInfo.reduce_level_exp(user_id, exp)

    @classmethod
    async def reduce_favor_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """
        减少好感度经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前好感度等级, 当前经验, 是否降级)
        """
        return await UserExpInfo.reduce_favor_exp(user_id, exp)

    @classmethod
    async def get_level_progress(cls, user_id: str) -> dict:
        """
        获取等级进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 等级进度信息
        """
        return await UserExpInfo.get_level_progress(user_id)

    @classmethod
    async def get_favor_progress(cls, user_id: str) -> dict:
        """
        获取好感度进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 好感度进度信息
        """
        return await UserExpInfo.get_favor_progress(user_id)

    @classmethod
    async def get_both_progress(cls, user_id: str) -> dict:
        """
        同时获取等级和好感度进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 包含等级和好感度进度信息
        """
        return await UserExpInfo.get_both_progress(user_id)

    @classmethod
    async def set_level(cls, user_id: str, level: int):
        """
        设置用户等级

        参数:
            user_id: 用户ID
            level: 等级
        """
        await UserExpInfo.set_level(user_id, level)

    @classmethod
    async def set_favor(cls, user_id: str, favor: int):
        """
        设置用户好感度等级

        参数:
            user_id: 用户ID
            favor: 好感度等级
        """
        await UserExpInfo.set_favor(user_id, favor)

    @classmethod
    def calculate_next_level_exp(cls, current_level: int) -> int:
        """
        计算下一级所需的经验值

        参数:
            current_level: 当前等级

        返回:
            int: 下一级所需经验值
        """
        return UserExpInfo.calculate_next_level_exp(current_level)

    @classmethod
    def calculate_next_favor_exp(cls, current_favor: int) -> int:
        """
        计算下一级好感度所需的经验值

        参数:
            current_favor: 当前好感度等级

        返回:
            int: 下一级好感度所需经验值
        """
        return UserExpInfo.calculate_next_favor_exp(current_favor)
