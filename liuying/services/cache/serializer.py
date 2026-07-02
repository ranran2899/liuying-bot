"""
缓存序列化和反序列化工具

支持自定义类型序列化器注册，允许用户为特定类型注册自定义的序列化/反序列化逻辑。
"""

import base64
import dataclasses
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel

from liuying.utils.log import logger

from .config import LOG_COMMAND


class CustomSerializer:
    """自定义序列化器基类

    用户可以继承此类实现自定义类型的序列化和反序列化。
    """

    def serialize(self, value: Any) -> Any:
        """序列化值

        参数:
            value: 需要序列化的值

        返回:
            Any: 序列化后的值

        异常:
            SerializationError: 序列化失败时抛出
        """
        raise NotImplementedError

    def deserialize(self, value: Any) -> Any:
        """反序列化值

        参数:
            value: 需要反序列化的值

        返回:
            Any: 反序列化后的值

        异常:
            DeserializationError: 反序列化失败时抛出
        """
        raise NotImplementedError


class SerializationError(Exception):
    """序列化错误"""


class DeserializationError(Exception):
    """反序列化错误"""


class CacheSerializer:
    """缓存序列化器

    支持自定义类型序列化器注册，允许用户为特定类型注册自定义的序列化/反序列化逻辑。
    """

    _custom_serializers: ClassVar[dict[type, CustomSerializer]] = {}

    @staticmethod
    def _is_sqlalchemy_model(obj: Any) -> bool:
        """判断对象是否为 SQLAlchemy 模型（实例或类）

        SQLAlchemy 模型通过 __table__ 属性标识，是 SQLAlchemy 的标准接口。
        同时检查 __mapper__ 以排除偶然拥有 __table__ 属性的普通对象。

        参数:
            obj: 待检测对象（实例或类）

        返回:
            bool: 是否为 SQLAlchemy 模型
        """
        return hasattr(obj, "__table__") and hasattr(obj, "__mapper__")

    @classmethod
    def register_serializer(
        cls,
        target_type: type,
        serializer: CustomSerializer,
    ) -> None:
        """注册自定义类型序列化器

        参数:
            target_type: 目标类型
            serializer: 自定义序列化器实例

        示例:
            ```python
            class MyObjectSerializer(CustomSerializer):
                def serialize(self, value):
                    return {"__type__": "MyObject", "data": value.to_dict()}

                def deserialize(self, value):
                    return MyObject.from_dict(value["data"])

            CacheSerializer.register_serializer(MyObject, MyObjectSerializer())
            ```
        """
        cls._custom_serializers[target_type] = serializer
        logger.debug(f"注册自定义序列化器: {target_type.__name__}", LOG_COMMAND)

    @classmethod
    def unregister_serializer(cls, target_type: type) -> bool:
        """注销自定义类型序列化器

        参数:
            target_type: 目标类型

        返回:
            bool: 是否成功注销
        """
        if target_type not in cls._custom_serializers:
            return False
        del cls._custom_serializers[target_type]
        logger.debug(f"注销自定义序列化器: {target_type.__name__}", LOG_COMMAND)
        return True

    @classmethod
    def clear_serializers(cls) -> None:
        """清除所有自定义序列化器"""
        cls._custom_serializers.clear()
        logger.debug("清除所有自定义序列化器", LOG_COMMAND)

    @classmethod
    def _find_custom_serializer(cls, value: Any) -> CustomSerializer | None:
        """查找值的自定义序列化器

        按类型 MRO（方法解析顺序）查找，保证子类优先于父类匹配。

        参数:
            value: 需要序列化的值

        返回:
            CustomSerializer | None: 自定义序列化器，未找到返回None
        """
        custom = cls._custom_serializers
        for value_type in type(value).__mro__:
            if serializer := custom.get(value_type):
                return serializer
        return None

    @classmethod
    def serialize(cls, value: Any, strict: bool = False) -> Any:
        """序列化值

        参数:
            value: 需要序列化的值
            strict: 严格模式，为True时无法序列化的类型会抛出异常

        返回:
            Any: 序列化后的值

        异常:
            SerializationError: 严格模式下无法序列化时抛出
        """
        if value is None:
            return None

        custom_serializer = cls._find_custom_serializer(value)
        if custom_serializer:
            try:
                return custom_serializer.serialize(value)
            except Exception as e:
                if strict:
                    raise SerializationError(
                        f"自定义序列化失败: {type(value).__name__}"
                    ) from e
                logger.warning(
                    f"自定义序列化失败: {type(value).__name__}",
                    LOG_COMMAND,
                    e=e,
                )
                return None

        match value:
            case int() | float() | str() | bool():
                return value
            case bytes() | bytearray():
                return {
                    "__bytes__": True,
                    "value": base64.b64encode(value).decode("ascii"),
                }
            case Enum():
                return {
                    "__enum__": True,
                    "type": type(value).__name__,
                    "value": value.value,
                }
            case datetime():
                return {"__datetime__": True, "value": value.isoformat()}
            case BaseModel():
                return value.model_dump()
            case _ if dataclasses.is_dataclass(value) and not isinstance(value, type):
                return dataclasses.asdict(value)
            case _ if cls._is_sqlalchemy_model(value):
                result: dict[str, Any] = {}
                for column in value.__table__.columns:
                    try:
                        field_value = getattr(value, column.name)
                        result[column.name] = cls.serialize(field_value, strict)
                    except AttributeError:
                        continue
                return result
            case dict():
                return {str(k): cls.serialize(v, strict) for k, v in value.items()}
            case list():
                return [cls.serialize(item, strict) for item in value]
            case tuple():
                return {
                    "__tuple__": True,
                    "value": [cls.serialize(item, strict) for item in value],
                }
            case set():
                return {
                    "__set__": True,
                    "value": [cls.serialize(item, strict) for item in value],
                }
            case _:
                if strict:
                    raise SerializationError(f"无法序列化类型: {type(value).__name__}")
                logger.debug(
                    f"类型 {type(value).__name__} 无法序列化，将转换为字符串",
                    LOG_COMMAND,
                )
                return {"__str__": True, "value": str(value)}

    @classmethod
    def deserialize(cls, value: Any, target_type: type | None = None) -> Any:
        """反序列化值

        参数:
            value: 需要反序列化的值
            target_type: 目标类型

        返回:
            Any: 反序列化后的值
        """
        if value is None:
            return None

        match value:
            case dict():
                return cls._deserialize_dict(value, target_type)
            case int() | float() | str() | bool():
                return cls._deserialize_primitive(value, target_type)
            case list():
                return cls._deserialize_list(value, target_type)
            case _:
                return value

    @classmethod
    def _deserialize_dict(cls, value: dict[str, Any], target_type: type | None) -> Any:
        """反序列化字典类型值

        参数:
            value: 字典数据
            target_type: 目标类型

        返回:
            Any: 反序列化后的值
        """
        if value.get("__enum__") and target_type:
            try:
                if isinstance(target_type, type) and issubclass(target_type, Enum):
                    return target_type(value["value"])
            except (ValueError, KeyError, TypeError):
                pass

        if value.get("__datetime__"):
            try:
                return datetime.fromisoformat(value["value"])
            except (ValueError, TypeError):
                pass

        if value.get("__bytes__"):
            try:
                return base64.b64decode(value["value"])
            except (ValueError, TypeError):
                pass

        if value.get("__tuple__"):
            return tuple(cls.deserialize(item) for item in value["value"])

        if value.get("__set__"):
            return {cls.deserialize(item) for item in value["value"]}

        if value.get("__str__"):
            return value["value"]

        if target_type:
            if target_type in cls._custom_serializers:
                try:
                    return cls._custom_serializers[target_type].deserialize(value)
                except Exception as e:
                    logger.debug(
                        f"自定义反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

            deserialized = cls._deserialize_dict_to_type(value, target_type)
            if deserialized is not None:
                return deserialized

        return {k: cls.deserialize(v) for k, v in value.items()}

    @classmethod
    def _deserialize_primitive(
        cls, value: float | str | bool, target_type: type | None
    ) -> Any:
        """反序列化原始类型值

        参数:
            value: 原始类型值
            target_type: 目标类型

        返回:
            Any: 反序列化后的值
        """
        if (
            target_type
            and isinstance(target_type, type)
            and issubclass(target_type, Enum)
        ):
            try:
                return target_type(value)
            except (ValueError, KeyError, TypeError):
                return value
        return value

    @classmethod
    def _deserialize_list(cls, value: list[Any], target_type: type | None) -> list[Any]:
        """反序列化列表类型值

        参数:
            value: 列表数据
            target_type: 目标类型

        返回:
            list[Any]: 反序列化后的列表
        """
        if not value:
            return value

        is_list_type = (
            target_type
            and hasattr(target_type, "__origin__")
            and target_type.__origin__ is list
        )
        if is_list_type:
            item_type = target_type.__args__[0]
            return [cls.deserialize(item, item_type) for item in value]

        return [cls.deserialize(item) for item in value]

    @classmethod
    def _deserialize_dict_to_type(
        cls, value: dict[str, Any], target_type: type
    ) -> Any | None:
        """将字典反序列化为指定类型

        按优先级尝试不同的反序列化策略，失败时记录调试日志。

        参数:
            value: 字典数据
            target_type: 目标类型

        返回:
            Any | None: 反序列化结果，无法反序列化时返回None
        """
        match target_type:
            case _ if hasattr(target_type, "model_validate"):
                try:
                    return target_type.model_validate(value)
                except Exception as e:
                    logger.debug(
                        f"Pydantic模型反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

            case _ if cls._is_sqlalchemy_model(target_type):
                try:
                    instance = target_type()
                    for column in target_type.__table__.columns:
                        if column.name in value:
                            setattr(instance, column.name, value[column.name])
                    return instance
                except Exception as e:
                    logger.debug(
                        f"SQLAlchemy模型反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

            case _ if (
                dataclasses.is_dataclass(target_type) and isinstance(target_type, type)
            ):
                try:
                    valid_fields = {
                        f.name: value[f.name]
                        for f in dataclasses.fields(target_type)
                        if f.name in value
                    }
                    return target_type(**valid_fields)
                except Exception as e:
                    logger.debug(
                        f"dataclass反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

            case _ if (isinstance(target_type, type) and issubclass(target_type, Enum)):
                try:
                    return target_type(value.get("value", value))
                except (ValueError, KeyError, TypeError) as e:
                    logger.debug(
                        f"枚举反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

            case _:
                try:
                    return target_type(**value)
                except Exception as e:
                    logger.debug(
                        f"通用构造器反序列化失败: {target_type.__name__}",
                        LOG_COMMAND,
                        e=e,
                    )

        return None
