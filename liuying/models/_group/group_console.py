from typing import ClassVar

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.data_access import DataAccess
from liuying.services.liuying_db import Model
from liuying.utils.enum import CacheType, DbLockType


def add_disable_marker(name: str) -> str:
    """添加模块禁用标记符

    参数:
        name: 模块名称

    返回:
        添加了禁用标记的模块名 (前缀'<'和后缀',')
    """
    return f"<{name},"


def convert_module_format(data: str | list[str]) -> str | list[str]:
    """在 `<aaa,<bbb,<ccc,` 和 `["aaa", "bbb", "ccc"]` 之间相互转换

    参数:
        data: 要转换的数据

    返回:
        str | list[str]: 根据输入类型返回转换后的数据
    """
    if isinstance(data, str):
        return [item.strip(",") for item in data.split("<") if item.strip()]
    return "".join(add_disable_marker(item) for item in data)


class GroupConsole(Model):
    """群组控制台模型类

    用于管理群组的基本信息、权限设置、插件禁用状态等
    """
    __tablename__ = "group_console"
    __table_args__ = (
        UniqueConstraint("group_id", "channel_id"),
        {"comment": "群组控制台表，用于管理群组的基本信息、权限设置、插件禁用状态等"}
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    group_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="群聊id")
    channel_id: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="频道id")
    group_name: Mapped[str] = mapped_column(Text, default="", comment="群聊名称")
    max_member_count: Mapped[int] = mapped_column(default=0, comment="最大人数")
    member_count: Mapped[int] = mapped_column(default=0, comment="当前人数")
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment="群状态")
    level: Mapped[int] = mapped_column(default=5, comment="群权限")
    is_super: Mapped[bool] = mapped_column(Boolean, default=False, comment="超级用户指定群，可以使用全局关闭的功能")
    group_flag: Mapped[int] = mapped_column(default=0, comment="群认证状态")
    block_plugin: Mapped[str] = mapped_column(Text, default="", comment="禁用插件")
    superuser_block_plugin: Mapped[str] = mapped_column(Text, default="", comment="超级用户禁用插件")
    block_task: Mapped[str] = mapped_column(Text, default="", comment="禁用被动技能")
    superuser_block_task: Mapped[str] = mapped_column(Text, default="", comment="超级用户禁用被动")
    proactive_allowed: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="群聊是否允许机器人主动消息"
    )
    platform: Mapped[str] = mapped_column(String(255), default="qq", comment="所属平台")

    cache_type = CacheType.GROUPS
    cache_key_field = ("group_id", "channel_id")
    enable_lock: ClassVar[list[DbLockType]] = [DbLockType.CREATE, DbLockType.UPSERT]

    @classmethod
    async def get_group(
        cls, group_id: str, channel_id: str | None = None, clean_duplicates: bool = True
    ):
        """获取群组

        参数:
            group_id: 群组id
            channel_id: 频道id
            clean_duplicates: 是否删除重复的记录，仅保留最新的

        返回:
            GroupConsole | None
        """
        dao = DataAccess(cls)
        if channel_id:
            return await dao.safe_get_or_none(
                group_id=group_id,
                channel_id=channel_id,
                clean_duplicates=clean_duplicates,
            )
        return await dao.safe_get_or_none(
            group_id=group_id,
            channel_id=None,
            clean_duplicates=clean_duplicates,
        )

    @classmethod
    async def is_super_group(cls, group_id: str) -> bool:
        """是否超级用户指定群

        参数:
            group_id: 群组id

        返回:
            bool: 是否超级用户指定群
        """
        return group.is_super if (group := await cls.get_group(group_id)) else False

    @classmethod
    async def is_superuser_block_plugin(cls, group_id: str, module: str) -> bool:
        """查看群组是否超级用户禁用功能

        参数:
            group_id: 群组id
            module: 模块名称

        返回:
            bool: 是否禁用
        """
        return await cls.filter(
            group_id=group_id,
        ).filter(cls.superuser_block_plugin.contains(add_disable_marker(module))).exists()

    @classmethod
    async def is_block_plugin(cls, group_id: str, module: str) -> bool:
        """查看群组是否禁用插件

        参数:
            group_id: 群组id
            module: 插件名称

        返回:
            bool: 是否禁用插件
        """
        module = add_disable_marker(module)
        return await cls.filter(
            group_id=group_id
        ).filter(cls.block_plugin.contains(module)).exists() or await cls.filter(
            group_id=group_id
        ).filter(cls.superuser_block_plugin.contains(module)).exists()

    @classmethod
    async def set_block_plugin(
        cls,
        group_id: str,
        module: str,
        is_superuser: bool = False,
        platform: str | None = None,
    ):
        """禁用群组插件

        参数:
            group_id: 群组id
            module: 任务模块
            is_superuser: 是否为超级用户
            platform: 平台
        """
        group, _ = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"platform": platform}
        )
        if is_superuser:
            superuser_block_plugin = convert_module_format(group.superuser_block_plugin)
            if module not in superuser_block_plugin:
                superuser_block_plugin.append(module)
                group.superuser_block_plugin = convert_module_format(
                    superuser_block_plugin
                )
        elif add_disable_marker(module) not in group.block_plugin:
            block_plugin = convert_module_format(group.block_plugin)
            block_plugin.append(module)
            group.block_plugin = convert_module_format(block_plugin)
        await group.save()

    @classmethod
    async def set_unblock_plugin(
        cls,
        group_id: str,
        module: str,
        is_superuser: bool = False,
        platform: str | None = None,
    ):
        """启用群组插件

        参数:
            group_id: 群组id
            module: 任务模块
            is_superuser: 是否为超级用户
            platform: 平台
        """
        group, _ = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"platform": platform}
        )
        if is_superuser:
            superuser_block_plugin = convert_module_format(group.superuser_block_plugin)
            if module in superuser_block_plugin:
                superuser_block_plugin.remove(module)
                group.superuser_block_plugin = convert_module_format(
                    superuser_block_plugin
                )
        elif add_disable_marker(module) in group.block_plugin:
            block_plugin = convert_module_format(group.block_plugin)
            block_plugin.remove(module)
            group.block_plugin = convert_module_format(block_plugin)
        await group.save()

    @classmethod
    async def is_normal_block_plugin(
        cls, group_id: str, module: str, channel_id: str | None = None
    ) -> bool:
        """查看群组是否禁用功能

        参数:
            group_id: 群组id
            module: 模块名称
            channel_id: 频道id

        返回:
            bool: 是否禁用
        """
        return await cls.filter(
            group_id=group_id,
            channel_id=channel_id,
        ).filter(cls.block_plugin.contains(f"<{module},")).exists()

    @classmethod
    async def is_superuser_block_task(cls, group_id: str, task: str) -> bool:
        """查看群组是否超级用户禁用被动

        参数:
            group_id: 群组id
            task: 模块名称

        返回:
            bool: 是否禁用
        """
        return await cls.filter(
            group_id=group_id,
        ).filter(cls.superuser_block_task.contains(add_disable_marker(task))).exists()

    @classmethod
    async def is_block_task(
        cls, group_id: str, task: str, channel_id: str | None = None
    ) -> bool:
        """查看群组是否禁用被动

        参数:
            group_id: 群组id
            task: 任务模块
            channel_id: 频道id

        返回:
            bool: 是否禁用
        """
        task = add_disable_marker(task)
        if not channel_id:
            return (
                await cls.filter(group_id=group_id)
                .where_null("channel_id")
                .filter(cls.block_task.contains(task))
                .exists()
                or await cls.filter(group_id=group_id)
                .where_null("channel_id")
                .filter(cls.superuser_block_task.contains(task))
                .exists()
            )
        return (
            await cls.filter(
                group_id=group_id, channel_id=channel_id
            ).filter(cls.block_task.contains(task)).exists()
            or await cls.filter(group_id=group_id)
            .where_null("channel_id")
            .filter(cls.superuser_block_task.contains(task))
            .exists()
        )

    @classmethod
    async def set_block_task(
        cls,
        group_id: str,
        task: str,
        is_superuser: bool = False,
        platform: str | None = None,
    ):
        """禁用群组被动

        参数:
            group_id: 群组id
            task: 任务模块
            is_superuser: 是否为超级用户
            platform: 平台
        """
        group, _ = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"platform": platform}
        )
        if is_superuser:
            superuser_block_task = convert_module_format(group.superuser_block_task)
            if task not in superuser_block_task:
                superuser_block_task.append(task)
                group.superuser_block_task = convert_module_format(superuser_block_task)
        elif add_disable_marker(task) not in group.block_task:
            block_task = convert_module_format(group.block_task)
            block_task.append(task)
            group.block_task = convert_module_format(block_task)
        await group.save()

    @classmethod
    async def set_unblock_task(
        cls,
        group_id: str,
        task: str,
        is_superuser: bool = False,
        platform: str | None = None,
    ):
        """启用群组被动

        参数:
            group_id: 群组id
            task: 任务模块
            is_superuser: 是否为超级用户
            platform: 平台
        """
        group, _ = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"platform": platform}
        )
        if is_superuser:
            superuser_block_task = convert_module_format(group.superuser_block_task)
            if task in superuser_block_task:
                superuser_block_task.remove(task)
                group.superuser_block_task = convert_module_format(superuser_block_task)
        elif add_disable_marker(task) in group.block_task:
            block_task = convert_module_format(group.block_task)
            block_task.remove(task)
            group.block_task = convert_module_format(block_task)
        await group.save()

    @classmethod
    async def set_status(cls, group_id: str, status: bool):
        """设置群组状态

        参数:
            group_id: 群组id
            status: 状态
        """
        group, created = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"status": status}
        )
        if not created:
            group.status = status
            await group.save()

    @classmethod
    async def set_group_level(cls, group_id: str, level: int):
        """设置群组权限

        参数:
            group_id: 群组id
            level: 权限等级
        """
        group, created = await cls.get_or_create(
            group_id=group_id, channel_id=None, defaults={"level": level}
        )
        if not created:
            group.level = level
            await group.save()

    @classmethod
    async def is_proactive_allowed(cls, group_id: str) -> bool:
        """检查群聊是否允许机器人主动消息

        参数:
            group_id: 群组id

        返回:
            bool: 是否允许主动消息，群组不存在时默认返回True
        """
        group = await cls.get_group(group_id)
        return group.proactive_allowed if group else True

    @classmethod
    async def set_proactive_status(
        cls, group_id: str, allowed: bool
    ):
        """设置群聊主动消息状态

        参数:
            group_id: 群组id
            allowed: 是否允许主动消息
        """
        group, created = await cls.get_or_create(
            group_id=group_id, channel_id=None
        )
        if not created or group.proactive_allowed != allowed:
            group.proactive_allowed = allowed
            await group.save()

    @classmethod
    async def toggle_super_group(cls, group_id: str):
        """切换超级群组状态

        参数:
            group_id: 群组id
        """
        group = await cls.filter(group_id=group_id).where_null("channel_id").first()
        if group:
            group.is_super = not group.is_super
            await group.save()

    @classmethod
    async def update_group_info(
        cls,
        group_id: str,
        group_name: str,
        max_member_count: int,
        member_count: int,
        channel_id: str | None = None,
    ):
        """更新群组信息

        参数:
            group_id: 群组id
            group_name: 群组名称
            max_member_count: 最大成员数
            member_count: 当前成员数
            channel_id: 频道id
        """
        group, created = await cls.update_or_create(
            group_id=group_id,
            channel_id=channel_id,
            defaults={
                "group_name": group_name,
                "max_member_count": max_member_count,
                "member_count": member_count,
            },
        )
        if not created:
            group.group_name = group_name
            group.max_member_count = max_member_count
            group.member_count = member_count
            await group.save()

    @classmethod
    async def get_all_groups(cls) -> list:
        """获取所有群组

        返回:
            list: 群组列表
        """
        return await cls.filter().all()

    @classmethod
    def _run_script(cls):
        """数据库迁移

        返回:
            list: SQL语句列表，用于数据库表结构更新
        """
        return [
            "ALTER TABLE group_console ADD superuser_block_plugin TEXT DEFAULT '';",
            "ALTER TABLE group_console ADD superuser_block_task TEXT DEFAULT '';",
            "ALTER TABLE group_console ADD block_task TEXT DEFAULT '';",
            "ALTER TABLE group_console ADD proactive_allowed BOOLEAN DEFAULT TRUE;",
        ]
