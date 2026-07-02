"""
机器人账号优先级模型
已经移除
"""
from typing import ClassVar

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.cache import Cache
from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType

_PRIORITY_CACHE = Cache(CacheType.BOT_PRIORITY, result_type=int)


class BotPriority(Model):
    """机器人账号优先级模型

    用于管理同一群组中多个机器人账号的响应优先级，
    优先级数值越小等级越高，1级为最高优先级，5级为最低优先级。
    每个群组可独立配置各机器人的优先级。
    """

    __tablename__ = "bot_priority"
    __table_args__: ClassVar[tuple] = (
        UniqueConstraint("group_id", "bot_id"),
        {"comment": "机器人账号优先级表，存储各群组中机器人账号的响应优先级等级"},
    )

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    group_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="群组id"
    )
    """群组id"""
    bot_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="bot_id"
    )
    """bot_id"""
    priority: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False, comment="优先级等级(1-5, 1最高)"
    )
    """优先级等级(1-5, 1最高)"""
    platform: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="平台"
    )
    """平台"""

    cache_type = CacheType.BOT_PRIORITY
    """缓存类型"""
    cache_key_field = ("group_id", "bot_id")
    """缓存键字段 - 复合键"""

    MIN_PRIORITY = 1
    """最低优先级数值（最高等级）"""
    MAX_PRIORITY = 5
    """最高优先级数值（最低等级）"""
    DEFAULT_PRIORITY = 5
    """默认优先级"""
    CACHE_EXPIRE = 600
    """缓存过期时间（秒）"""

    _PRIORITY_DESC: ClassVar[dict[int, str]] = {
        1: "最高",
        2: "高",
        3: "中",
        4: "低",
        5: "最低",
    }
    """优先级等级描述映射"""

    @classmethod
    def priority_desc(cls, priority: int) -> str:
        """获取优先级等级描述

        参数:
            priority: 优先级数值

        返回:
            str: 优先级描述
        """
        return cls._PRIORITY_DESC.get(priority, "未知")

    @classmethod
    async def get_priority(cls, group_id: str, bot_id: str) -> int:
        """获取机器人在指定群组的优先级等级

        参数:
            group_id: 群组id
            bot_id: 机器人账号id

        返回:
            int: 优先级等级(1-5)，未配置时返回默认值5
        """
        record = await cls.filter(
            group_id=group_id, bot_id=bot_id
        ).first()
        return record.priority if record else cls.DEFAULT_PRIORITY

    @classmethod
    async def get_priority_cached(
        cls, group_id: str, bot_id: str
    ) -> int:
        """获取机器人在指定群组的优先级等级（带缓存）

        优先从缓存读取，缓存未命中时从数据库加载并写入缓存，
        内置击穿防护避免并发重复加载。

        参数:
            group_id: 群组id
            bot_id: 机器人账号id

        返回:
            int: 优先级等级(1-5)，未配置时返回默认值5
        """
        result = await _PRIORITY_CACHE.get_or_load(
            f"{group_id}_{bot_id}",
            loader=lambda: cls.get_priority(group_id, bot_id),
            expire=cls.CACHE_EXPIRE,
        )
        return result if result is not None else cls.DEFAULT_PRIORITY

    @classmethod
    async def get_priorities_cached(
        cls, group_id: str, bot_ids: set[str]
    ) -> dict[str, int]:
        """批量获取机器人在指定群组的优先级等级（带缓存）

        顺序获取以避免 SQLite 并发锁问题。缓存命中时无 DB 开销，
        仅未命中时才会查库，顺序执行对性能影响极小。

        参数:
            group_id: 群组id
            bot_ids: 机器人账号id集合

        返回:
            dict[str, int]: bot_id到优先级等级的映射
        """
        if not bot_ids:
            return {}
        return {
            bid: await cls.get_priority_cached(group_id, bid)
            for bid in bot_ids
        }

    @classmethod
    async def set_priority(
        cls,
        group_id: str,
        bot_id: str,
        priority: int,
        platform: str | None = None,
    ) -> "BotPriority":
        """设置机器人在指定群组的优先级等级

        update_or_create 内部自动调用 _invalidate_cache 使缓存失效，
        下次读取时将通过 get_or_load 重新加载。

        参数:
            group_id: 群组id
            bot_id: 机器人账号id
            priority: 优先级等级(1-5)
            platform: 平台信息

        返回:
            BotPriority: 优先级记录

        异常:
            ValueError: 优先级不在1-5范围内
        """
        if not cls.MIN_PRIORITY <= priority <= cls.MAX_PRIORITY:
            raise ValueError(
                f"优先级等级必须在 {cls.MIN_PRIORITY}-{cls.MAX_PRIORITY} 之间，"
                f"当前值: {priority}"
            )
        record, _ = await cls.update_or_create(
            group_id=group_id,
            bot_id=bot_id,
            defaults={"priority": priority, "platform": platform},
        )
        return record

    @classmethod
    async def get_all_priorities(
        cls, group_id: str | None = None
    ) -> list["BotPriority"]:
        """获取机器人优先级记录

        参数:
            group_id: 群组id，为None时获取全部记录

        返回:
            list[BotPriority]: 优先级记录列表
        """
        kwargs = {"group_id": group_id} if group_id else {}
        return await cls.filter(**kwargs).all()

    @classmethod
    async def _reset_priorities(
        cls, group_id: str | None = None
    ) -> int:
        """重置机器人优先级为默认值的内部实现

        批量更新不触发框架的 _invalidate_cache，需手动清除缓存。

        参数:
            group_id: 群组id，为None时重置全部

        返回:
            int: 重置的记录数量
        """
        kwargs = {"group_id": group_id} if group_id else {}
        count = await cls.filter(**kwargs).update(
            priority=cls.DEFAULT_PRIORITY
        )
        if count > 0:
            await cls.clear_cache()
        return count

    @classmethod
    async def reset_group(cls, group_id: str) -> int:
        """重置指定群组的机器人优先级为默认值

        参数:
            group_id: 群组id

        返回:
            int: 重置的记录数量
        """
        return await cls._reset_priorities(group_id)

    @classmethod
    async def reset_all(cls) -> int:
        """重置全部机器人优先级为默认值

        返回:
            int: 重置的记录数量
        """
        return await cls._reset_priorities()

    @classmethod
    async def delete_priority(
        cls, group_id: str, bot_id: str
    ) -> bool:
        """删除机器人在指定群组的优先级记录

        delete 内部自动调用 _invalidate_cache 使缓存失效。

        参数:
            group_id: 群组id
            bot_id: 机器人账号id

        返回:
            bool: 是否成功删除
        """
        record = await cls.filter(
            group_id=group_id, bot_id=bot_id
        ).first()
        if record:
            await record.delete()
            return True
        return False

    @classmethod
    async def clear_cache(cls) -> None:
        """清除所有优先级缓存

        仅用于批量操作（如 reset_all）后的手动缓存清除，
        单条记录的增删改由框架基类自动处理缓存失效。
        """
        try:
            await _PRIORITY_CACHE.clear()
        except Exception:
            pass

    @classmethod
    def _run_script(cls):
        """运行数据库迁移脚本"""
        return [
            (
                "ALTER TABLE bot_priority "
                "ADD COLUMN group_id VARCHAR(255) NOT NULL DEFAULT '';"
            ),
        ]
