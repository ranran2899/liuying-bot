"""适配器加载器基类"""

from abc import ABCMeta, abstractmethod

from .action import ActionExecutor
from .constraint import SupportAdapter
from .fetch import InfoFetcher


class BaseLoader(metaclass=ABCMeta):
    """适配器加载器，负责声明适配器名并提供抓取器与动作执行器实例"""

    @abstractmethod
    def get_adapter(self) -> SupportAdapter:
        """获取适配器名称"""
        raise NotImplementedError

    @abstractmethod
    def get_fetcher(self) -> InfoFetcher:
        """获取会话信息抓取器实例"""
        raise NotImplementedError

    def get_executor(self) -> ActionExecutor | None:
        """获取统一动作执行器实例，未实现的适配器返回 None"""
        return None
