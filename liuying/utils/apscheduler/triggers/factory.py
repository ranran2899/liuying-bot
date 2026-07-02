"""
触发器工厂
提供统一的触发器创建接口，通过注册表查表解耦各模块对触发器创建的依赖
"""

from typing import Any

from liuying.utils.apscheduler.triggers.base import (
    _TRIGGER_REGISTRY,
    BaseTrigger,
)


class TriggerFactory:
    """
    触发器工厂类

    根据触发器类型名称查注册表创建对应的触发器实例。
    通过 register_trigger 装饰器注册的触发器自动可用，
    无需修改本工厂代码。
    """

    @staticmethod
    def create(
        trigger_type: str,
        trigger_config: dict[str, Any],
    ) -> BaseTrigger:
        """
        创建触发器实例

        参数:
            trigger_type: 触发器类型名称 (cron/interval/date 或自定义)
            trigger_config: 触发器配置字典

        返回:
            触发器实例

        异常:
            ValueError: 不支持的触发器类型
        """
        cls = _TRIGGER_REGISTRY.get(trigger_type)
        if cls is None:
            raise ValueError(f"不支持的触发器类型: {trigger_type}")
        return cls.from_config(trigger_config)


trigger_factory = TriggerFactory()
