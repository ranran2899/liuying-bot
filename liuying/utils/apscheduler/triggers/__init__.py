"""
触发器模块

提供三种类型的触发器：Cron、Interval、Date，
通过 register_trigger 装饰器自动注册到工厂注册表。
"""

from .base import BaseTrigger
from .cron import CronTrigger
from .date import DateTrigger
from .factory import TriggerFactory, trigger_factory
from .interval import IntervalTrigger

__all__ = [
    "BaseTrigger",
    "CronTrigger",
    "DateTrigger",
    "IntervalTrigger",
    "TriggerFactory",
    "trigger_factory",
]
