"""QQ机器人配置模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType


class QQBotConfig(Model):
    """QQ机器人配置模型类

    用于存储用户配置的QQ机器人信息,支持权限隔离和数据加密
    """

    __tablename__ = "qq_bot_config"
    __table_args__: ClassVar[dict] = {
        "comment": "QQ机器人配置表,用于管理用户的QQ机器人配置信息"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="用户ID"
    )
    """用户ID - 配置所有者"""
    bot_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="机器人ID"
    )
    """机器人ID - QQ号"""
    bot_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="机器人名称"
    )
    """机器人名称 - 用户自定义名称"""
    token: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="机器人Token"
    )
    """机器人Token - 加密存储"""
    secret: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="机器人Secret"
    )
    """机器人Secret - 加密存储"""
    intent: Mapped[str] = mapped_column(
        Text, nullable=False, comment="意图配置 - JSON格式"
    )
    """意图配置 - JSON格式存储"""
    use_websocket: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否使用WebSocket"
    )
    """是否使用WebSocket"""
    is_sandbox: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否为沙箱环境"
    )
    """是否为沙箱环境"""
    status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="配置状态"
    )
    """配置状态 - 是否启用"""
    create_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    """创建时间"""
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), comment="更新时间"
    )
    """更新时间"""
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注信息"
    )
    """备注信息"""

    cache_type = CacheType.QQ_BOT_CONFIG
    """缓存类型"""
    cache_key_field = ("user_id", "bot_id")
    """缓存键字段 - 复合键"""

    @classmethod
    async def get_user_configs(cls, user_id: str) -> list["QQBotConfig"]:
        """获取用户的所有QQ机器人配置

        参数:
            user_id: 用户ID

        返回:
            list[QQBotConfig]: 配置列表
        """
        return await cls.filter(user_id=user_id).all()

    @classmethod
    async def get_config_by_bot_id(
        cls, user_id: str, bot_id: str
    ) -> "QQBotConfig | None":
        """根据机器人ID获取配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            QQBotConfig | None: 配置对象,不存在返回None
        """
        return await cls.filter(user_id=user_id, bot_id=bot_id).first()

    @classmethod
    async def create_config(
        cls,
        user_id: str,
        bot_id: str,
        token: str,
        secret: str,
        intent: str,
        bot_name: str | None = None,
        use_websocket: bool = True,
        is_sandbox: bool = False,
        remark: str | None = None,
    ) -> "QQBotConfig":
        """创建QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            token: 机器人Token
            secret: 机器人Secret
            intent: 意图配置JSON字符串
            bot_name: 机器人名称
            use_websocket: 是否使用WebSocket
            is_sandbox: 是否为沙箱环境
            remark: 备注信息

        返回:
            QQBotConfig: 创建的配置对象
        """
        return await cls.create(
            user_id=user_id,
            bot_id=bot_id,
            bot_name=bot_name,
            token=token,
            secret=secret,
            intent=intent,
            use_websocket=use_websocket,
            is_sandbox=is_sandbox,
            remark=remark,
        )

    @classmethod
    async def update_config(
        cls,
        user_id: str,
        bot_id: str,
        **kwargs,
    ) -> bool:
        """更新QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            **kwargs: 要更新的字段

        返回:
            bool: 是否更新成功
        """
        config = await cls.filter(user_id=user_id, bot_id=bot_id).first()
        if not config:
            return False

        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        await config.save()
        return True

    @classmethod
    async def delete_config(cls, user_id: str, bot_id: str) -> bool:
        """删除QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            bool: 是否删除成功
        """
        config = await cls.filter(user_id=user_id, bot_id=bot_id).first()
        if not config:
            return False

        await config.delete()
        return True

    @classmethod
    async def count_user_configs(cls, user_id: str) -> int:
        """统计用户的配置数量

        参数:
            user_id: 用户ID

        返回:
            int: 配置数量
        """
        return await cls.filter(user_id=user_id).count()

    @classmethod
    async def check_bot_id_exists(cls, user_id: str, bot_id: str) -> bool:
        """检查机器人ID在指定用户下是否已存在

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            bool: 是否存在
        """
        return await cls.filter(user_id=user_id, bot_id=bot_id).exists()

    @classmethod
    async def check_bot_id_global_exists(cls, bot_id: str) -> bool:
        """检查机器人ID是否已被任何用户添加(全局检查)

        参数:
            bot_id: 机器人ID

        返回:
            bool: 是否存在
        """
        return await cls.filter(bot_id=bot_id).exists()
