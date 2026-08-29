"""群组配置模型"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class GroupConfig(Model):
    """群组配置模型类

    存储机器人在群内的配置与状态,每个群一条记录,
    支持QQ官方 bot_state 接口数据同步
    """

    __tablename__ = "group_config"
    __table_args__: ClassVar[dict] = {
        "comment": "群组配置表,存储机器人在群内的主动消息开关与群内状态"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    group_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="群号/群openid"
    )
    """群号/群openid"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="机器人id"
    )
    """获取的机器人id"""
    proactive_allowed: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="群聊是否允许机器人主动消息"
    )
    """群聊是否允许机器人主动消息"""
    recv_msg_setting: Mapped[str] = mapped_column(
        String(50), default="all", comment="接收消息设置"
    )
    """群内接收消息的设置: all/only_mention/mention_and_context"""
    bot_role: Mapped[str] = mapped_column(
        String(50), default="member", comment="机器人群内角色"
    )
    """机器人群内角色: member/owner/admin"""
    platform: Mapped[str] = mapped_column(String(255), default="qq", comment="所属平台")
    """所属平台"""
    create_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    """创建时间"""
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, onupdate=func.now(), comment="更新时间"
    )
    """更新时间"""

    @classmethod
    async def get_config(cls, group_id: str) -> GroupConfig | None:
        """获取群组配置

        参数:
            group_id: 群号/群openid

        返回:
            GroupConfig | None: 配置对象,不存在返回None
        """
        return await cls.filter(group_id=group_id).first()

    @classmethod
    async def get_or_create_config(
        cls, group_id: str, platform: str = "qq"
    ) -> GroupConfig:
        """获取或创建群组配置

        参数:
            group_id: 群号/群openid
            platform: 所属平台

        返回:
            GroupConfig: 配置对象
        """
        return await cls.get_or_create(
            group_id=group_id, defaults={"platform": platform}
        )

    @classmethod
    async def is_proactive_allowed(cls, group_id: str) -> bool:
        """检查群聊是否允许机器人主动消息

        参数:
            group_id: 群号/群openid

        返回:
            bool: 是否允许主动消息,配置不存在时默认返回True
        """
        config = await cls.filter(group_id=group_id).first()
        return config.proactive_allowed if config else True

    @classmethod
    async def set_proactive_status(cls, group_id: str, allowed: bool) -> None:
        """设置群聊主动消息状态

        参数:
            group_id: 群号/群openid
            allowed: 是否允许主动消息
        """
        config = await cls.get_or_create_config(group_id)
        if config.proactive_allowed != allowed:
            config.proactive_allowed = allowed
            await config.save()

    @classmethod
    async def update_bot_state(
        cls,
        group_id: str,
        allow_proactive_msg: bool,
        recv_msg_setting: str,
        member_role: str,
        platform: str = "qq",
    ) -> None:
        """同步QQ官方bot_state接口数据

        对应 GET /v2/groups/{group_openid}/bot/state 响应体,
        一次写入主动消息开关、接收消息设置与群内角色

        参数:
            group_id: 群openid
            allow_proactive_msg: 是否接收主动推送
            recv_msg_setting: 接收消息设置 all/only_mention/mention_and_context
            member_role: 群成员角色 member/owner/admin
            platform: 所属平台
        """
        config = await cls.get_or_create_config(group_id, platform)
        config.proactive_allowed = allow_proactive_msg
        config.recv_msg_setting = recv_msg_setting
        config.bot_role = member_role
        await config.save()

    @classmethod
    def _run_script(cls):
        """数据库迁移: 旧版group_config表结构调整

        移除auto_reply等遗留字段,补充机器人状态字段,
        重复执行报错由脚本执行流程吞掉

        返回:
            list[str]: SQL语句列表
        """
        return [
            "ALTER TABLE group_config DROP COLUMN auto_reply;",
            "ALTER TABLE group_config DROP COLUMN repeat;",
            "ALTER TABLE group_config DROP COLUMN repeat_probability;",
            "ALTER TABLE group_config DROP COLUMN welcome;",
            "ALTER TABLE group_config DROP COLUMN welcome_msg;",
            "ALTER TABLE group_config ADD COLUMN bot_id VARCHAR(255) DEFAULT NULL;",
            "ALTER TABLE group_config"
            " ADD COLUMN recv_msg_setting VARCHAR(50) DEFAULT 'all';",
            "ALTER TABLE group_config"
            " ADD COLUMN bot_role VARCHAR(50) DEFAULT 'member';",
            "ALTER TABLE group_config"
            " ADD COLUMN platform VARCHAR(255) DEFAULT 'qq';",
            "ALTER TABLE group_config"
            " ADD COLUMN proactive_allowed BOOLEAN DEFAULT TRUE;",
        ]
