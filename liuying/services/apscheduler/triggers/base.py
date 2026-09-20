"""
触发器基类
定义触发器的核心接口和通用功能
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any, Self


class BaseTrigger(ABC):
    """
    触发器基类

    所有触发器必须实现 get_next_run_time 方法，
    用于计算下一次任务执行时间（naive datetime，无下次执行时返回 None）。
    """

    def __init__(
        self,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
    ) -> None:
        self._start_date = self.parse_datetime(start_date) if start_date else None
        self._end_date = self.parse_datetime(end_date) if end_date else None

    @staticmethod
    def parse_datetime(dt: datetime | str) -> datetime:
        """
        解析日期时间，返回 naive datetime

        参数:
            dt: datetime 对象或 ISO 格式字符串

        返回:
            去除时区信息的 naive datetime

        异常:
            ValueError: 无法解析的字符串或非法类型
        """
        if isinstance(dt, datetime):
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        if isinstance(dt, str):
            normalized = dt.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as e:
                raise ValueError(f"无法解析日期时间: {dt}") from e
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        raise ValueError(f"无法解析日期时间: {dt}")

    @abstractmethod
    def get_next_run_time(
        self, previous_time: datetime | None = None
    ) -> datetime | None:
        """
        获取下次运行时间

        参数:
            previous_time: 上次运行时间，None 表示首次运行

        返回:
            下次运行时间，无下次执行时返回 None
        """
        ...

    @abstractmethod
    def to_config(self) -> dict[str, Any]:
        """将触发器转换为配置字典"""
        ...

    @classmethod
    @abstractmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        """从配置字典创建触发器"""
        ...


# 触发器注册表（参考 LLM 模块的 register_provider 模式）
_TRIGGER_REGISTRY: dict[str, type[BaseTrigger]] = {}


def register_trigger(name: str) -> Callable[[type[BaseTrigger]], type[BaseTrigger]]:
    """
    触发器注册装饰器

    参数:
        name: 触发器类型名称（如 "cron"/"interval"/"date"）

    返回:
        类装饰器
    """

    def decorator(cls: type[BaseTrigger]) -> type[BaseTrigger]:
        _TRIGGER_REGISTRY[name] = cls
        return cls

    return decorator
