"""
缓存数据模型
"""

from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from .config import DEFAULT_EXPIRE, SPECIAL_KEY_FORMATS


class CacheModel(BaseModel):
    """缓存数据模型"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    """缓存名称"""
    expire: int = DEFAULT_EXPIRE
    """过期时间（秒）"""
    result_type: Any = None
    """结果类型（支持泛型如 list[Model]）"""
    key_format: str | None = None
    """键格式"""

    @classmethod
    def create(
        cls,
        name: str,
        result_type: type | None = None,
        expire: int = DEFAULT_EXPIRE,
        key_format: str | None = None,
    ) -> Self:
        """创建缓存模型

        参数:
            name: 缓存名称
            result_type: 结果类型
            expire: 过期时间（秒）
            key_format: 键格式

        返回:
            Self: 缓存模型实例
        """
        name = name.upper()
        if not key_format and name in SPECIAL_KEY_FORMATS:
            key_format = SPECIAL_KEY_FORMATS[name]
        return cls(
            name=name,
            expire=expire,
            result_type=result_type,
            key_format=key_format,
        )
