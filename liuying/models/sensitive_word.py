from typing import ClassVar

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.services.cache import CacheRoot
from liuying.utils.enum import CacheType


class SensitiveWord(Model):
    """敏感词模型类

    用于管理敏感词过滤
    """

    __tablename__ = "sensitive_word"
    __table_args__: ClassVar[dict] = {
        "comment": "敏感词表，用于消息过滤"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    word: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, comment="敏感词"
    )
    """敏感词"""
    is_regex: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否为正则表达式"
    )
    """是否为正则表达式"""
    level: Mapped[int] = mapped_column(
        Integer, default=1, comment="敏感等级 1-低 2-中 3-高"
    )
    """敏感等级"""
    action: Mapped[int] = mapped_column(
        Integer, default=1, comment="处理方式 1-替换 2-拦截 3-封禁"
    )
    """处理方式"""
    replacement: Mapped[str | None] = mapped_column(
        String(255), default="*", comment="替换文本"
    )
    """替换文本"""
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="描述"
    )
    """描述"""
    status: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用"
    )
    """是否启用"""

    cache_type = CacheType.SENSITIVE
    """缓存类型"""
    cache_key_field = "all"
    """缓存键字段"""

    @classmethod
    async def _invalidate_cache(cls) -> None:
        """清除敏感词缓存"""
        await CacheRoot.invalidate_cache(cls.cache_type, cls.cache_key_field)

    @classmethod
    async def get_active_words(cls) -> list["SensitiveWord"]:
        """获取所有启用的敏感词

        返回:
            list[SensitiveWord]: 敏感词列表
        """
        return await cls.filter(status=True).all()

    @classmethod
    async def add_word(
        cls,
        word: str,
        is_regex: bool = False,
        level: int = 1,
        action: int = 1,
        replacement: str = "*",
        description: str | None = None,
    ) -> "SensitiveWord | None":
        """添加敏感词

        参数:
            word: 敏感词
            is_regex: 是否为正则
            level: 敏感等级
            action: 处理方式
            replacement: 替换文本
            description: 描述

        返回:
            SensitiveWord | None: 敏感词对象
        """
        if await cls.filter(word=word).first():
            return None
        result = await cls.create(
            word=word,
            is_regex=is_regex,
            level=level,
            action=action,
            replacement=replacement,
            description=description,
        )
        await cls._invalidate_cache()
        return result

    @classmethod
    async def remove_word(cls, word: str) -> bool:
        """删除敏感词

        参数:
            word: 敏感词

        返回:
            bool: 是否删除成功
        """
        if obj := await cls.filter(word=word).first():
            await obj.delete()
            await cls._invalidate_cache()
            return True
        return False

    @classmethod
    async def update_word(
        cls,
        word: str,
        **kwargs,
    ) -> bool:
        """更新敏感词

        参数:
            word: 敏感词
            **kwargs: 更新字段

        返回:
            bool: 是否更新成功
        """
        if obj := await cls.filter(word=word).first():
            for key, value in kwargs.items():
                if hasattr(obj, key):
                    setattr(obj, key, value)
            await obj.save()
            await cls._invalidate_cache()
            return True
        return False
