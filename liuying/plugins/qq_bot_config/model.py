"""QQ机器人配置模型"""

from typing import Any, ClassVar

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType


class QQBotConfig(Model):
    """QQ机器人配置模型类

    每个用户一行,其接入的全部QQ机器人以JSON列表存储,
    列表格式与环境变量QQ_BOTS完全一致
    """

    __tablename__ = "qq_bot_config"
    __table_args__: ClassVar[dict] = {
        "comment": "QQ机器人配置表,按用户存储QQ_BOTS格式的机器人配置列表"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="用户ID"
    )
    """用户ID - 配置所有者"""
    bots: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, comment="机器人配置列表 - QQ_BOTS格式"
    )
    """机器人配置列表 - 与QQ_BOTS环境变量格式完全一致"""

    cache_type = CacheType.QQ_BOT_CONFIG
    """缓存类型"""
    cache_key_field = "user_id"
    """缓存键字段"""

    @classmethod
    async def get_user_bots(cls, user_id: str) -> list[dict[str, Any]]:
        """获取用户的全部机器人配置

        参数:
            user_id: 用户ID

        返回:
            list[dict[str, Any]]: QQ_BOTS格式的配置列表
        """
        row = await cls.filter(user_id=user_id).first()
        return row.bots if row else []

    @classmethod
    async def save_user_bots(
        cls, user_id: str, bots: list[dict[str, Any]]
    ) -> None:
        """保存用户的机器人配置列表(不存在则创建)

        参数:
            user_id: 用户ID
            bots: QQ_BOTS格式的配置列表
        """
        row = await cls.filter(user_id=user_id).first()
        if row is None:
            await cls.create(user_id=user_id, bots=bots)
            return
        row.bots = list(bots)  # 重新赋值以触发JSON列变更检测
        await row.save(update_fields=["bots"])

    @classmethod
    async def get_bot(
        cls, user_id: str, bot_id: str
    ) -> dict[str, Any] | None:
        """获取用户的单个机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            dict[str, Any] | None: QQ_BOTS格式的单个配置,不存在返回None
        """
        bots = await cls.get_user_bots(user_id)
        return next((b for b in bots if b["id"] == bot_id), None)

    @classmethod
    async def get_all_bots(cls) -> list[tuple[str, dict[str, Any]]]:
        """获取全部机器人的配置

        返回:
            list[tuple[str, dict[str, Any]]]: (归属用户ID, 机器人配置) 列表
        """
        rows = await cls.filter().all()
        return [
            (row.user_id, bot) for row in rows for bot in row.bots
        ]

    @classmethod
    async def get_bot_owner(cls, bot_id: str) -> str | None:
        """反查机器人配置的归属用户ID

        参数:
            bot_id: 机器人ID

        返回:
            str | None: 归属用户ID,不存在返回None
        """
        for user_id, bot in await cls.get_all_bots():
            if bot["id"] == bot_id:
                return user_id
        return None

    @classmethod
    async def bot_id_exists(cls, bot_id: str) -> bool:
        """检查机器人ID是否已被任何用户配置(全局检查)

        参数:
            bot_id: 机器人ID

        返回:
            bool: 是否存在
        """
        return any(bot["id"] == bot_id for _, bot in await cls.get_all_bots())

    @classmethod
    async def delete_all(cls) -> None:
        """清空全部用户的机器人配置"""
        await cls.filter().delete()
