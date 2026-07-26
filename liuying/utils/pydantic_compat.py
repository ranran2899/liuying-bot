"""Pydantic V2 工具函数模块

提供 Pydantic V2 环境下的便捷函数与类，包括 model_dump、parse_as 等。
所有 V1 兼容代码已移除，仅支持 Pydantic V2。
"""

from typing import Any, TypeVar, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, computed_field

V = TypeVar("V")

__all__ = [
    "_dump_pydantic_obj",
    "_is_pydantic_type",
    "compat_computed_field",
    "model_dump",
    "parse_as",
]


def model_dump(model: BaseModel, **kwargs: Any) -> dict[str, Any]:
    """序列化 Pydantic 模型为字典

    参数:
        model: Pydantic 模型实例
        **kwargs: 传递给 model_dump 的额外参数

    返回:
        序列化后的字典
    """
    return model.model_dump(**kwargs)


def parse_as(type_: type[V], obj: Any) -> V:
    """将对象解析为目标类型

    参数:
        type_: 目标类型
        obj: 待解析的对象

    返回:
        解析后的目标类型实例
    """
    return TypeAdapter(type_).validate_python(obj)


compat_computed_field = computed_field
"""Pydantic V2 计算字段装饰器"""


def _is_pydantic_type(t: Any) -> bool:
    """递归检查一个类型注解是否与 Pydantic BaseModel 相关

    参数:
        t: 待检查的类型

    返回:
        是否为 Pydantic 类型
    """
    if t is None:
        return False
    origin = get_origin(t)
    if origin:
        return any(_is_pydantic_type(arg) for arg in get_args(t))
    return isinstance(t, type) and issubclass(t, BaseModel)


def _dump_pydantic_obj(obj: Any) -> Any:
    """递归地将对象内部的 Pydantic BaseModel 实例转换为字典

    参数:
        obj: 待处理的对象

    返回:
        转换后的对象
    """
    match obj:
        case BaseModel():
            return model_dump(obj)
        case list():
            return [_dump_pydantic_obj(item) for item in obj]
        case dict():
            return {key: _dump_pydantic_obj(value) for key, value in obj.items()}
        case _:
            return obj
