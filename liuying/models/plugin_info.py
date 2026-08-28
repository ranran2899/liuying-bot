"""
插件信息表
"""

from typing import ClassVar, Self

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from liuying.services.liuying_db import Model
from liuying.utils.enum import BlockType, CacheType, PluginType


class PluginInfo(Model):
    """插件信息模型

    用于管理插件的配置信息、状态和权限设置。
    """

    __tablename__ = "plugin_info"
    __table_args__: ClassVar[dict[str, str]] = {
        "comment": "插件信息表，用于管理插件的配置信息、状态和权限设置"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    module: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="模块名"
    )
    """模块名"""
    module_path: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, comment="模块路径"
    )
    """模块路径"""
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="插件名称"
    )
    """插件名称"""
    status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="全局开关状态"
    )
    """全局开关状态"""
    block_type: Mapped[BlockType | None] = mapped_column(
        String(255), nullable=True, default=None, comment="禁用类型"
    )
    """禁用类型"""
    load_status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="加载状态"
    )
    """加载状态"""
    author: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="作者"
    )
    """作者"""
    version: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="版本"
    )
    """版本"""
    level: Mapped[int] = mapped_column(default=5, comment="所需群权限")
    """所需群权限"""
    default_status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="进群默认开关状态"
    )
    """进群默认开关状态"""
    limit_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否限制超级用户"
    )
    """是否限制超级用户"""
    menu_type: Mapped[str] = mapped_column(
        String(255), default="", comment="菜单类型"
    )
    """菜单类型"""
    plugin_type: Mapped[PluginType | None] = mapped_column(
        String(255), nullable=True, comment="插件类型"
    )
    """插件类型"""
    cost_gold: Mapped[int] = mapped_column(
        default=0, comment="调用插件所需金币"
    )
    """调用插件所需金币"""
    admin_level: Mapped[int | None] = mapped_column(
        default=0, nullable=True, comment="调用所需权限等级"
    )
    """调用所需权限等级"""
    ignore_prompt: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否忽略提示"
    )
    """是否忽略提示"""
    is_delete: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否删除"
    )
    """是否删除"""
    parent: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="父插件"
    )
    """父插件"""
    is_show: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否显示在帮助中"
    )
    """是否显示在帮助中"""
    plugin_limits = relationship(
        "PluginLimit", back_populates="plugin", passive_deletes=True
    )

    cache_type = CacheType.PLUGINS
    """缓存类型"""
    cache_key_field = "module"
    """缓存键字段"""

    @classmethod
    def _visible_query(
        cls,
        load_status: bool = True,
        filter_parent: bool = True,
        **kwargs,
    ):
        """构建基础查询

        参数:
            load_status: 加载状态
            filter_parent: 是否过滤父插件
            **kwargs: 其他查询条件

        返回:
            查询对象
        """
        query = cls.filter(load_status=load_status)
        if filter_parent and not kwargs.get("plugin_type"):
            query = query.filter(cls.plugin_type != PluginType.PARENT)
        if kwargs:
            query = query.filter(**kwargs)
        return query

    @classmethod
    async def get_plugin(
        cls, load_status: bool = True, filter_parent: bool = True, **kwargs
    ) -> Self | None:
        """获取单个插件信息

        参数:
            load_status: 加载状态
            filter_parent: 是否过滤父插件
            **kwargs: 其他查询条件

        返回:
            PluginInfo对象或None
        """
        return await cls._visible_query(load_status, filter_parent, **kwargs).first()

    @classmethod
    async def get_plugins(
        cls, load_status: bool = True, filter_parent: bool = True, **kwargs
    ) -> list[Self]:
        """获取插件列表

        参数:
            load_status: 加载状态
            filter_parent: 是否过滤父插件
            **kwargs: 其他查询条件

        返回:
            PluginInfo对象列表
        """
        return await cls._visible_query(load_status, filter_parent, **kwargs).all()

    @classmethod
    def visible_query(cls, **kwargs):
        """构建对外可见插件查询（已加载、显示中、未删除、非父插件）

        参数:
            **kwargs: 附加查询条件

        返回:
            查询对象
        """
        return cls._visible_query(is_show=True, is_delete=False, **kwargs)

    @classmethod
    async def get_visible_plugins(cls, **kwargs) -> list[Self]:
        """获取对外可见插件列表（已加载、显示中、未删除、非父插件）

        参数:
            **kwargs: 附加查询条件

        返回:
            PluginInfo对象列表
        """
        return await cls.visible_query(**kwargs).all()

    @classmethod
    async def get_by_module(cls, module: str) -> Self | None:
        """按模块名获取插件

        参数:
            module: 模块名

        返回:
            PluginInfo对象或None
        """
        return await cls.filter(module=module).first()

    @classmethod
    async def get_by_id_or_name(cls, value: str, **filters) -> Self | None:
        """按ID或名称获取插件

        参数:
            value: 插件ID（纯数字）或插件名称
            **filters: 附加查询条件（仅对名称查询生效）

        返回:
            PluginInfo对象或None
        """
        if value.isdigit():
            return await cls.filter(id=int(value)).first()
        return await cls.filter(name=value, load_status=True, **filters).first()

    @classmethod
    async def get_by_name_or_module(cls, value: str) -> Self | None:
        """按名称或模块名获取插件，名称优先

        参数:
            value: 插件名称或模块名

        返回:
            PluginInfo对象或None
        """
        return await cls.get_plugin(name=value) or await cls.get_by_module(value)

    @classmethod
    async def get_name_map(cls, modules) -> dict[str, str]:
        """获取模块名到插件名称的映射

        参数:
            modules: 模块名集合

        返回:
            dict[str, str]: 模块名 -> 插件名称
        """
        module_list = list(modules)
        if not module_list:
            return {}
        plugins = await cls.filter(module__in=module_list).all()
        return {p.module: p.name for p in plugins}

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "ALTER TABLE plugin_info DROP COLUMN impression", 
        ]