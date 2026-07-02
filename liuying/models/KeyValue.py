
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserKeyValue(Model):
    """用户键值对模型类
    
    用于存储和管理用户的键值对数据
    """
    __tablename__ = 'user_key_value'
    __table_args__ = (
        UniqueConstraint('user_id', 'key', name='_user_key_uc'),
        {'comment': '用户键值对表，用于存储和管理用户的键值对数据'}
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment='自增id')
    """自增id"""
    user_id: Mapped[str] = mapped_column(String(255), index=True, comment='用户ID')
    """用户ID"""
    key: Mapped[str] = mapped_column(String(255), index=True, comment='键名')
    """键名"""
    value: Mapped[Any | None] = mapped_column(JSON, default=None, comment='键值，JSON格式')
    """键值，JSON格式"""
    last_updated: Mapped[datetime | None] = mapped_column(default=datetime.now, onupdate=datetime.now, comment='最后更新时间，自动更新')
    """最后更新时间，自动更新"""

    @classmethod
    async def get(cls, user_id: str, key: str) -> Any:
        """获取用户键值对
        
        参数:
            user_id: 用户ID
            key: 键名
        
        返回:
            Any: 键值，如果不存在则返回None
        """
        instance = await cls.filter(user_id=str(user_id), key=key).first()
        return instance.value if instance else None
    
    @classmethod
    async def set(cls, user_id: str, key: str, value: Any) -> None:
        """设置用户键值对
        
        参数:
            user_id: 用户ID
            key: 键名
            value: 键值
        """
        instance = await cls.filter(user_id=str(user_id), key=key).first()
        if instance:
            instance.value = value
            await instance.save()
        else:
            await cls.create(user_id=str(user_id), key=key, value=value)
    
    @classmethod
    async def delete(cls, user_id: str, key: str) -> bool:
        """删除用户键值对
        
        参数:
            user_id: 用户ID
            key: 键名
        
        返回:
            bool: 删除是否成功
        """
        instance = await cls.filter(user_id=str(user_id), key=key).first()
        if instance:
            await instance.delete()
            return True
        return False
    
    @classmethod
    async def get_all_keys(cls, user_id: str) -> list[str]:
        """获取用户的所有键名
        
        参数:
            user_id: 用户ID
        
        返回:
            list[str]: 键名列表
        """
        return await cls.filter(user_id=str(user_id)).values_list('key', flat=True)
    
    @classmethod
    async def get_all(cls, user_id: str) -> dict[str, Any]:
        """获取用户的所有键值对
        
        参数:
            user_id: 用户ID
        
        返回:
            dict[str, Any]: 键值对字典
        """
        instances = await cls.filter(user_id=str(user_id)).all()
        return {instance.key: instance.value for instance in instances}
