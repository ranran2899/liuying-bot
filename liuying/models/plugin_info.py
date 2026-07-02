"""
插件信息表
"""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing_extensions import Self

from liuying.services.liuying_db import Model
from liuying.utils.enum import BlockType, CacheType, PluginType

class PluginInfo(Model):
    """
    插件信息模型类
    
    用于管理插件的配置信息、状态和权限设置
    """
    __tablename__ = 'plugin_info'
    __table_args__ = {'comment': '插件信息表，用于管理插件的配置信息、状态和权限设置'}
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    module: Mapped[str] = mapped_column(String(255), nullable=False, comment='模块名')
    """模块名"""
    module_path: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment='模块路径')
    """模块路径"""
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment='插件名称')
    """插件名称"""
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment='全局开关状态')
    """全局开关状态"""
    block_type: Mapped[BlockType | None] = mapped_column(String(255), nullable=True, default=None, comment='禁用类型(BlockType枚举)')
    """禁用类型"""
    load_status: Mapped[bool] = mapped_column(Boolean, default=True, comment='加载状态')
    """加载状态"""
    author: Mapped[str | None] = mapped_column(String(255), nullable=True, comment='作者')
    """作者"""
    version: Mapped[str | None] = mapped_column(String(255), nullable=True, comment='版本')
    """版本"""
    level: Mapped[int] = mapped_column(default=5, comment='所需群权限')
    """所需群权限"""
    default_status: Mapped[bool] = mapped_column(Boolean, default=True, comment='进群默认开关状态')
    """进群默认开关状态"""
    limit_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否限制超级用户')
    """是否限制超级用户"""
    menu_type: Mapped[str] = mapped_column(String(255), default="", comment='菜单类型')
    """菜单类型"""
    plugin_type: Mapped[PluginType | None] = mapped_column(String(255), nullable=True, comment='插件类型(PluginType枚举)')
    """插件类型"""
    cost_gold: Mapped[int] = mapped_column(default=0, comment='调用插件所需金币')
    """调用插件所需金币"""
    admin_level: Mapped[int | None] = mapped_column(default=0, nullable=True, comment='调用所需权限等级')
    """调用所需权限等级"""
    ignore_prompt: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否忽略提示')
    """是否忽略提示"""
    is_delete: Mapped[bool] = mapped_column(Boolean, default=False, comment='是否删除')
    """是否删除"""
    parent: Mapped[str | None] = mapped_column(String(255), nullable=True, comment='父插件')
    """父插件"""
    is_show: Mapped[bool] = mapped_column(Boolean, default=True, comment='是否显示在帮助中')
    """是否显示在帮助中"""
    impression: Mapped[float] = mapped_column(Float, default=0, comment='插件好感度限制')
    """插件好感度限制"""
    plugin_limits = relationship("PluginLimit", back_populates="plugin", passive_deletes=True)
    
    cache_type = CacheType.PLUGINS
    """缓存类型"""
    cache_key_field = "module"
    """缓存键字段"""
    
    @classmethod
    async def get_plugin(cls, load_status: bool = True, filter_parent: bool = True, **kwargs):
        """
        获取插件信息
        
        参数:
            load_status: 加载状态
            filter_parent: 是否过滤父组件
            **kwargs: 其他查询条件
        
        返回:
            PluginInfo对象或None
        """
        query = cls.filter(load_status=load_status)
        
        if filter_parent and not kwargs.get("plugin_type"):
            query = query.filter(cls.plugin_type != PluginType.PARENT)
        
        for key, value in kwargs.items():
            query = query.filter(**{key: value})
        
        return await query.first()
    
    @classmethod
    async def get_plugins(cls, load_status: bool = True, filter_parent: bool = True, **kwargs):
        """
        获取插件列表
        
        参数:
            load_status: 加载状态
            filter_parent: 是否过滤父组件
            **kwargs: 其他查询条件
        
        返回:
            PluginInfo对象列表
        """
        query = cls.filter(load_status=load_status)
        
        if filter_parent and not kwargs.get("plugin_type"):
            query = query.filter(cls.plugin_type != PluginType.PARENT)
        
        for key, value in kwargs.items():
            query = query.filter(**{key: value})
        
        return await query.all()

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "ALTER TABLE plugin_info ADD ignore_prompt BOOLEAN DEFAULT FALSE;",
        ]
