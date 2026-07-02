"""Pydantic V1 & V2 兼容层模块

为 Pydantic V1 与 V2 版本提供统一的便捷函数与类，
包括 model_dump, model_copy, model_json_schema, parse_as 等。
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin

from nonebot.compat import PYDANTIC_V2, model_dump
import orjson as json
from pydantic import VERSION, BaseModel, TypeAdapter

if not PYDANTIC_V2:
    from pydantic import parse_obj_as

T = TypeVar("T", bound=BaseModel)
V = TypeVar("V")


__all__ = [
    "PYDANTIC_V2",
    "_dump_pydantic_obj",
    "_is_pydantic_type",
    "compat_computed_field",
    "dump_json_safely",
    "model_copy",
    "model_dump",
    "model_json_schema",
    "parse_as",
]


def model_copy(
    model: T, *, update: dict[str, Any] | None = None, deep: bool = False
) -> T:
    """Pydantic `model.copy()` (v1) 和 `model.model_copy()` (v2) 的兼容函数"""
    if PYDANTIC_V2:
        return model.model_copy(update=update, deep=deep)
    return model.copy(update=update or {}, deep=deep)


if PYDANTIC_V2:
    from pydantic import computed_field as compat_computed_field
else:
    compat_computed_field = property


def model_json_schema(model_class: type[BaseModel], **kwargs: Any) -> dict[str, Any]:
    """Pydantic `Model.schema()` (v1) 和 `Model.model_json_schema()` (v2) 的兼容函数"""
    if PYDANTIC_V2:
        return model_class.model_json_schema(**kwargs)
    return model_class.schema(by_alias=kwargs.get("by_alias", True))


def _is_pydantic_type(t: Any) -> bool:
    """递归检查一个类型注解是否与 Pydantic BaseModel 相关"""
    if t is None:
        return False
    origin = get_origin(t)
    if origin:
        return any(_is_pydantic_type(arg) for arg in get_args(t))
    return isinstance(t, type) and issubclass(t, BaseModel)


def _dump_pydantic_obj(obj: Any) -> Any:
    """递归地将一个对象内部的 Pydantic BaseModel 实例转换为字典"""
    match obj:
        case BaseModel():
            return model_dump(obj)
        case list():
            return [_dump_pydantic_obj(item) for item in obj]
        case dict():
            return {key: _dump_pydantic_obj(value) for key, value in obj.items()}
        case _:
            return obj


def parse_as(type_: type[V], obj: Any) -> V:
    """兼容 Pydantic V1/V2 的对象解析辅助函数"""
    if VERSION.startswith("1"):
        return parse_obj_as(type_, obj)
    return TypeAdapter(type_).validate_python(obj)


def json_default(o: Any) -> Any:
    """json 序列化的默认处理函数"""
    match o:
        case Enum():
            return o.value
        case datetime():
            return o.isoformat()
        case Path():
            return o.as_posix()
        case set():
            return list(o)
        case BaseModel():
            return model_dump(o)
        case _:
            raise TypeError(
                f"Object of type {o.__class__.__name__} is not JSON serializable"
            )


def dump_json_safely(obj: Any, **kwargs) -> str:
    """安全地将可能包含 Pydantic 特定类型的对象序列化为 JSON 字符串"""
    return json.dumps(obj, default=json_default, **kwargs).decode("utf-8")
