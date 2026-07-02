from abc import ABC, abstractmethod
from collections.abc import Callable

import nonebot
from nonebot.utils import is_coroutine_callable
from pydantic import BaseModel

from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

driver = nonebot.get_driver()


class PluginInit(ABC):
    """插件安装与卸载模块"""

    def __init_subclass__(cls, **kwargs):
        module_path = cls.__module__
        install_func = getattr(cls, "install", None)
        remove_func = getattr(cls, "remove", None)
        if install_func or remove_func:
            PluginInitManager.plugins[module_path] = PluginInitData(
                module_path=module_path,
                install=install_func,
                remove=remove_func,
                class_=cls,
            )

    @abstractmethod
    async def install(self):
        raise NotImplementedError

    @abstractmethod
    async def remove(self):
        raise NotImplementedError


class PluginInitData(BaseModel):
    module_path: str
    """模块名"""
    install: Callable | None
    """安装方法"""
    remove: Callable | None
    """卸载方法"""
    class_: type[PluginInit]
    """类"""


class PluginInitManager:
    plugins: dict[str, PluginInitData] = {}  # noqa: RUF012

    @classmethod
    async def _execute_hook(
        cls, module_path: str, model: PluginInitData, hook_name: str
    ):
        """执行插件生命周期钩子的通用方法

        参数:
            module_path: 模块路径
            model: 插件初始化数据
            hook_name: 钩子名称 (install/remove)
        """
        hook_func = getattr(model, hook_name)
        if not hook_func:
            return
        instance = model.class_()
        try:
            logger.debug(f"开始执行: {module_path}:{hook_name} 方法")
            func = getattr(instance, hook_name)
            if is_coroutine_callable(func):
                await func()
            else:
                func()  # type: ignore
                logger.debug(f"执行: {module_path}:{hook_name} 完成")
        except Exception as e:
            logger.error(f"执行: {module_path}:{hook_name} 失败", e=e)

    @classmethod
    async def install_all(cls):
        """运行所有插件安装方法"""
        if not cls.plugins:
            return
        for module_path, model in cls.plugins.items():
            await cls._execute_hook(module_path, model, "install")

    @classmethod
    async def install(cls, module_path: str):
        """运行指定插件安装方法

        参数:
            module_path: 模块路径
        """
        if model := cls.plugins.get(module_path):
            await cls._execute_hook(module_path, model, "install")

    @classmethod
    async def remove(cls, module_path: str):
        """运行指定插件移除方法

        参数:
            module_path: 模块路径
        """
        if model := cls.plugins.get(module_path):
            await cls._execute_hook(module_path, model, "remove")


@PriorityLifecycle.on_startup(priority=5)
async def _():
    await PluginInitManager.install_all()
