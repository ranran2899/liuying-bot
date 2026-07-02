"""用户经验模型"""

from typing import ClassVar

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.cache import CacheRoot
from liuying.services.liuying_db import Model
from liuying.configs.config import Config

from .user_info import UserInfo


class UserExpInfo(Model):
    """用户经验模型类"""

    __tablename__ = "user_exp"
    __table_args__: ClassVar[dict] = {
        "comment": "用户经验表，用于管理用户的经验值"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="用户ID"
    )
    """用户ID"""
    favor_exp: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="好感度经验点"
    )
    """好感度经验点"""
    next_favor_exp: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="下一级需要的好感度经验点"
    )
    """每个等级需要的好感度经验点"""
    level_exp: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="等级经验点"
    )
    """等级经验点"""
    next_level_exp: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="下一级需要的等级经验点"
    )
    """下一级需要的等级经验点"""

    BASE_LEVEL_EXP: ClassVar[int] = 100
    """基础等级经验值"""
    LEVEL_EXP_GROWTH: ClassVar[float] = Config.get_config("signIn", "LEVEL_EXPERIENCE_RATE", 1.5)
    """等级经验增长系数"""
    MAX_LEVEL: ClassVar[int] = Config.get_config("signIn", "MAX_LEVEL", 100)
    """最大等级"""
    BASE_FAVOR_EXP: ClassVar[int] = 50
    """基础好感度经验值"""
    FAVOR_EXP_GROWTH: ClassVar[float] = Config.get_config("signIn", "FAVOR_EXPERIENCE_RATE", 5.5)
    """好感度经验增长系数"""
    MAX_FAVOR_LEVEL: ClassVar[int] = Config.get_config("signIn", "MAX_FAVOR", 9)
    """最大好感度等级"""

    _exp_cache = CacheRoot.cache_dict("USER_EXP_CACHE")
    """经验值缓存字典"""

    @classmethod
    def _init_exp_cache(cls):
        """初始化经验值缓存"""
        if "level_exp_initialized" in cls._exp_cache:
            return

        for level in range(cls.MAX_LEVEL + 1):
            level_exp = int(cls.BASE_LEVEL_EXP * (cls.LEVEL_EXP_GROWTH**level))
            favor_exp = int(cls.BASE_FAVOR_EXP * (cls.FAVOR_EXP_GROWTH**level))
            cls._exp_cache.set(f"level_exp_{level}", level_exp)
            cls._exp_cache.set(f"favor_exp_{level}", favor_exp)

        cumulative_level = 0
        cumulative_favor = 0
        for level in range(cls.MAX_LEVEL + 1):
            cumulative_level += cls._exp_cache.get(f"level_exp_{level}", 0)
            cumulative_favor += cls._exp_cache.get(f"favor_exp_{level}", 0)
            cls._exp_cache.set(f"level_cumulative_{level}", cumulative_level)
            cls._exp_cache.set(f"favor_cumulative_{level}", cumulative_favor)

        cls._exp_cache.set("level_exp_initialized", True)

    @classmethod
    async def get_user_exp(cls, user_id: str) -> "UserExpInfo":
        """获取用户经验信息

        参数:
            user_id: 用户ID

        返回:
            UserExpInfo: 用户经验信息
        """
        user_exp, _ = await cls.get_or_create(user_id=user_id)
        return user_exp

    @classmethod
    async def _get_user_exp_and_info(
        cls, user_id: str
    ) -> tuple["UserExpInfo", UserInfo]:
        """同时获取用户经验信息和用户信息

        参数:
            user_id: 用户ID

        返回:
            tuple[UserExpInfo, UserInfo]: 用户经验信息和用户信息
        """
        user_exp, _ = await cls.get_or_create(user_id=user_id)
        user_info = await UserInfo.get_user(user_id)
        return user_exp, user_info

    @classmethod
    def calculate_next_level_exp(cls, current_level: int) -> int:
        """计算下一级所需的经验值

        参数:
            current_level: 当前等级

        返回:
            int: 下一级所需经验值
        """
        cls._init_exp_cache()
        max_exp = cls._exp_cache.get(f"level_exp_{cls.MAX_LEVEL}", 0)
        return cls._exp_cache.get(f"level_exp_{current_level}", max_exp)

    @classmethod
    def calculate_next_favor_exp(cls, current_favor: int) -> int:
        """计算下一级好感度所需的经验值

        参数:
            current_favor: 当前好感度等级

        返回:
            int: 下一级好感度所需经验值
        """
        cls._init_exp_cache()
        max_exp = cls._exp_cache.get(f"favor_exp_{cls.MAX_FAVOR_LEVEL}", 0)
        return cls._exp_cache.get(f"favor_exp_{current_favor}", max_exp)

    @classmethod
    def _calculate_level_from_exp(
        cls, current_level: int, total_exp: int
    ) -> tuple[int, int, bool]:
        """根据总经验值计算等级

        参数:
            current_level: 当前等级
            total_exp: 总经验值

        返回:
            tuple[int, int, bool]: (新等级, 剩余经验, 是否升级)
        """
        cls._init_exp_cache()
        leveled_up = False

        while current_level < cls.MAX_LEVEL:
            next_exp = cls._exp_cache.get(f"level_exp_{current_level}", 0)
            if total_exp >= next_exp:
                total_exp -= next_exp
                current_level += 1
                leveled_up = True
            else:
                break

        return current_level, total_exp, leveled_up

    @classmethod
    def _calculate_favor_from_exp(
        cls, current_favor: int, total_exp: int
    ) -> tuple[int, int, bool]:
        """根据总经验值计算好感度等级

        参数:
            current_favor: 当前好感度等级
            total_exp: 总经验值

        返回:
            tuple[int, int, bool]: (新好感度等级, 剩余经验, 是否升级)
        """
        cls._init_exp_cache()
        leveled_up = False

        while current_favor < cls.MAX_FAVOR_LEVEL:
            next_exp = cls._exp_cache.get(f"favor_exp_{current_favor}", 0)
            if total_exp >= next_exp:
                total_exp -= next_exp
                current_favor += 1
                leveled_up = True
            else:
                break

        return current_favor, total_exp, leveled_up

    @classmethod
    async def add_level_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """添加等级经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前等级, 当前经验, 是否升级)
        """
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_level = user_info.level_value
        current_exp = user_exp.level_exp + exp

        new_level, remaining_exp, leveled_up = cls._calculate_level_from_exp(
            current_level, current_exp
        )

        user_exp.level_exp = remaining_exp
        user_exp.next_level_exp = cls.calculate_next_level_exp(new_level)

        if leveled_up:
            user_info.level_value = new_level
            await user_info.save(update_fields=["level_value"])

        await user_exp.save(update_fields=["level_exp", "next_level_exp"])

        return new_level, remaining_exp, leveled_up

    @classmethod
    async def add_favor_exp(cls, user_id: str, exp: int) -> tuple[int, int, bool]:
        """添加好感度经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前好感度等级, 当前经验, 是否升级)
        """
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_favor = user_info.favor_value
        current_exp = user_exp.favor_exp + exp

        new_favor, remaining_exp, leveled_up = cls._calculate_favor_from_exp(
            current_favor, current_exp
        )

        user_exp.favor_exp = remaining_exp
        user_exp.next_favor_exp = cls.calculate_next_favor_exp(new_favor)

        if leveled_up:
            user_info.favor_value = new_favor
            await user_info.save(update_fields=["favor_value"])

        await user_exp.save(update_fields=["favor_exp", "next_favor_exp"])

        return new_favor, remaining_exp, leveled_up

    @classmethod
    async def get_level_progress(cls, user_id: str) -> dict:
        """获取等级进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 等级进度信息
        """
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_level = user_info.level_value
        current_exp = user_exp.level_exp
        next_exp = cls.calculate_next_level_exp(current_level)
        progress = (
            min(100, int((current_exp / next_exp) * 100)) if next_exp > 0 else 100
        )

        return {
            "level": current_level,
            "current_exp": current_exp,
            "next_exp": next_exp,
            "progress": progress,
            "max_level": cls.MAX_LEVEL,
        }

    @classmethod
    async def get_favor_progress(cls, user_id: str) -> dict:
        """获取好感度进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 好感度进度信息
        """
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_favor = user_info.favor_value
        current_exp = user_exp.favor_exp
        next_exp = cls.calculate_next_favor_exp(current_favor)
        progress = (
            min(100, int((current_exp / next_exp) * 100)) if next_exp > 0 else 100
        )

        return {
            "favor": current_favor,
            "current_exp": current_exp,
            "next_exp": next_exp,
            "progress": progress,
            "max_favor": cls.MAX_FAVOR_LEVEL,
        }

    @classmethod
    async def set_level(cls, user_id: str, level: int):
        """设置用户等级

        参数:
            user_id: 用户ID
            level: 等级
        """
        level = max(0, min(level, cls.MAX_LEVEL))
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        user_info.level_value = level
        user_exp.level_exp = 0
        user_exp.next_level_exp = cls.calculate_next_level_exp(level)

        await user_info.save(update_fields=["level_value"])
        await user_exp.save(update_fields=["level_exp", "next_level_exp"])

    @classmethod
    async def set_favor(cls, user_id: str, favor: int):
        """设置用户好感度等级

        参数:
            user_id: 用户ID
            favor: 好感度等级
        """
        favor = max(0, min(favor, cls.MAX_FAVOR_LEVEL))
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        user_info.favor_value = favor
        user_exp.favor_exp = 0
        user_exp.next_favor_exp = cls.calculate_next_favor_exp(favor)

        await user_info.save(update_fields=["favor_value"])
        await user_exp.save(update_fields=["favor_exp", "next_favor_exp"])

    @classmethod
    def _calculate_level_reduce(
        cls, current_level: int, current_exp: int, reduce_exp: int
    ) -> tuple[int, int, bool]:
        """根据减少的经验值计算等级

        参数:
            current_level: 当前等级
            current_exp: 当前经验值
            reduce_exp: 要减少的经验值

        返回:
            tuple[int, int, bool]: (新等级, 剩余经验, 是否降级)
        """
        cls._init_exp_cache()
        leveled_down = False
        total_exp = current_exp - reduce_exp

        while current_level > 0 and total_exp < 0:
            current_level -= 1
            prev_exp = cls._exp_cache.get(f"level_exp_{current_level}", 0)
            total_exp += prev_exp
            leveled_down = True

        if total_exp < 0:
            total_exp = 0

        return current_level, total_exp, leveled_down

    @classmethod
    def _calculate_favor_reduce(
        cls, current_favor: int, current_exp: int, reduce_exp: int
    ) -> tuple[int, int, bool]:
        """根据减少的经验值计算好感度等级

        参数:
            current_favor: 当前好感度等级
            current_exp: 当前经验值
            reduce_exp: 要减少的经验值

        返回:
            tuple[int, int, bool]: (新好感度等级, 剩余经验, 是否降级)
        """
        cls._init_exp_cache()
        leveled_down = False
        total_exp = current_exp - reduce_exp

        while current_favor > 0 and total_exp < 0:
            current_favor -= 1
            prev_exp = cls._exp_cache.get(f"favor_exp_{current_favor}", 0)
            total_exp += prev_exp
            leveled_down = True

        if total_exp < 0:
            total_exp = 0

        return current_favor, total_exp, leveled_down

    @classmethod
    async def reduce_level_exp(
        cls, user_id: str, exp: int
    ) -> tuple[int, int, bool]:
        """减少等级经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前等级, 当前经验, 是否降级)
        """
        if exp <= 0:
            return await cls.get_level_progress(user_id)

        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_level = user_info.level_value
        current_exp = user_exp.level_exp

        new_level, remaining_exp, leveled_down = cls._calculate_level_reduce(
            current_level, current_exp, exp
        )

        user_exp.level_exp = remaining_exp
        user_exp.next_level_exp = cls.calculate_next_level_exp(new_level)

        if leveled_down:
            user_info.level_value = new_level
            await user_info.save(update_fields=["level_value"])

        await user_exp.save(update_fields=["level_exp", "next_level_exp"])

        return new_level, remaining_exp, leveled_down

    @classmethod
    async def reduce_favor_exp(
        cls, user_id: str, exp: int
    ) -> tuple[int, int, bool]:
        """减少好感度经验

        参数:
            user_id: 用户ID
            exp: 经验值

        返回:
            tuple[int, int, bool]: (当前好感度等级, 当前经验, 是否降级)
        """
        if exp <= 0:
            return await cls.get_favor_progress(user_id)

        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_favor = user_info.favor_value
        current_exp = user_exp.favor_exp

        new_favor, remaining_exp, leveled_down = cls._calculate_favor_reduce(
            current_favor, current_exp, exp
        )

        user_exp.favor_exp = remaining_exp
        user_exp.next_favor_exp = cls.calculate_next_favor_exp(new_favor)

        if leveled_down:
            user_info.favor_value = new_favor
            await user_info.save(update_fields=["favor_value"])

        await user_exp.save(update_fields=["favor_exp", "next_favor_exp"])

        return new_favor, remaining_exp, leveled_down

    @classmethod
    async def get_both_progress(cls, user_id: str) -> dict:
        """同时获取等级和好感度进度信息

        参数:
            user_id: 用户ID

        返回:
            dict: 包含等级和好感度进度信息
        """
        user_exp, user_info = await cls._get_user_exp_and_info(user_id)

        current_level = user_info.level_value
        level_exp = user_exp.level_exp
        next_level_exp = cls.calculate_next_level_exp(current_level)
        level_progress = (
            min(100, int((level_exp / next_level_exp) * 100))
            if next_level_exp > 0
            else 100
        )

        current_favor = user_info.favor_value
        favor_exp = user_exp.favor_exp
        next_favor_exp = cls.calculate_next_favor_exp(current_favor)
        favor_progress = (
            min(100, int((favor_exp / next_favor_exp) * 100))
            if next_favor_exp > 0
            else 100
        )

        return {
            "level": {
                "level": current_level,
                "current_exp": level_exp,
                "next_exp": next_level_exp,
                "progress": level_progress,
                "max_level": cls.MAX_LEVEL,
            },
            "favor": {
                "favor": current_favor,
                "current_exp": favor_exp,
                "next_exp": next_favor_exp,
                "progress": favor_progress,
                "max_favor": cls.MAX_FAVOR_LEVEL,
            },
        }

    @classmethod
    def _run_script(cls):
        """运行数据库迁移脚本"""
        return [
            "ALTER TABLE user_exp DROP COLUMN IF EXISTS default_exp;",
            "ALTER TABLE user_exp DROP COLUMN IF EXISTS default_max;",
            "ALTER TABLE user_exp DROP COLUMN IF EXISTS next_default_exp;",
        ]
