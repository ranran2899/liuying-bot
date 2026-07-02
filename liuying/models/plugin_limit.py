from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing_extensions import Self

from liuying.services.liuying_db import Model
from liuying.utils.enum import LimitCheckType, LimitWatchType, PluginLimitType

class PluginLimit(Model):
    """插件限制模型类
    
    用于管理插件的调用限制、CD时间和次数限制等配置
    """
    __tablename__ = 'plugin_limit'
    __table_args__ = {'comment': '插件限制表，用于管理插件的调用限制、CD时间和次数限制等配置'}
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    module: Mapped[str] = mapped_column(String(255), nullable=False, comment='模块名')
    """模块名"""
    module_path: Mapped[str] = mapped_column(String(255), nullable=False, comment='模块路径')
    """模块路径"""
    plugin_id: Mapped[int] = mapped_column(ForeignKey('plugin_info.id', ondelete='CASCADE'), nullable=False, comment='所属插件ID')
    """所属插件ID"""
    limit_type: Mapped[str] = mapped_column(String(255), default=PluginLimitType.CD, comment='限制类型')
    """限制类型"""
    watch_type: Mapped[str] = mapped_column(String(255), default=LimitWatchType.USER, comment='监听类型')
    """监听类型"""
    status: Mapped[bool] = mapped_column(Boolean, default=True, comment='限制的开关状态')
    """限制的开关状态"""
    check_type: Mapped[str] = mapped_column(String(255), default=LimitCheckType.ALL, comment='检查类型')
    """检查类型"""
    result: Mapped[str | None] = mapped_column(String(255), nullable=True, comment='返回信息')
    """返回信息"""
    cd: Mapped[int | None] = mapped_column(nullable=True, comment='cd')
    """cd"""
    max_count: Mapped[int | None] = mapped_column(nullable=True, comment='最大调用次数')
    """最大调用次数"""
    plugin = relationship("PluginInfo", back_populates="plugin_limits")

    @classmethod
    async def get_limit(cls, module_path: str, **kwargs) -> Optional[Self]:
        """获取插件限制信息
        
        参数:
            module_path: 模块路径
            **kwargs: 其他查询条件
        
        返回:
            PluginLimit对象或None
        """
        query = cls.filter(module_path=module_path)
        for key, value in kwargs.items():
            query = query.filter(**{key: value})
        return await query.first()
    
    @classmethod
    async def get_limits(cls, **kwargs) -> list[Self]:
        """获取插件限制列表
        
        参数:
            **kwargs: 查询条件
        
        返回:
            PluginLimit对象列表
        """
        query = cls.filter()
        for key, value in kwargs.items():
            query = query.filter(**{key: value})
        return await query.all()
