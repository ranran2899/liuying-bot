"""Bot控制台模型"""
from typing import Literal, overload

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db.base_model import Model
from liuying.utils.enum import CacheType



class BotConsole(Model):
    """Bot控制台数据模型"""

    __tablename__ = "bot_console"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="自增id")
    """自增id"""
    bot_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="bot_id")
    """bot_id"""
    status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, comment="Bot状态")
    """Bot状态"""
    create_time: Mapped[str | None] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    """创建时间"""
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="平台")
    """平台"""
    block_plugins: Mapped[str] = mapped_column(Text, default="", comment="禁用插件")
    """禁用插件"""
    block_tasks: Mapped[str] = mapped_column(Text, default="", comment="禁用被动技能")
    """禁用被动技能"""
    available_plugins: Mapped[str] = mapped_column(Text, default="", comment="可用插件")
    """可用插件"""
    available_tasks: Mapped[str] = mapped_column(Text, default="", comment="可用被动技能")
    """可用被动技能"""

    cache_type = CacheType.BOT
    """缓存类型"""
    cache_key_field = "bot_id"
    """缓存键字段"""

    @staticmethod
    def format(name: str) -> str:
        """格式化模块名称"""
        return f"<{name},"

    @overload
    @classmethod
    async def get_bot_status(cls) -> list[tuple[str, bool]]: ...

    @overload
    @classmethod
    async def get_bot_status(cls, bot_id: str) -> bool: ...

    @classmethod
    async def get_bot_status(
        cls, bot_id: str | None = None
    ) -> list[tuple[str, bool]] | bool:
        """
        获取bot状态

        参数:
            bot_id (str, optional): bot_id. Defaults to None.

        返回:
            list[tuple[str, bool]] | bool: bot状态
        """
        if not bot_id:
            bots = await cls.filter().all()
            return [(bot.bot_id, bot.status) for bot in bots]
        else:
            bot = await cls.filter(bot_id=bot_id).first()
            return bot.status if bot else False

    @overload
    @classmethod
    async def get_tasks(cls) -> dict[str, list[str]]: ...

    @overload
    @classmethod
    async def get_tasks(cls, bot_id: str) -> list[str]: ...

    @overload
    @classmethod
    async def get_tasks(cls, *, status: bool) -> dict[str, list[str]]: ...

    @overload
    @classmethod
    async def get_tasks(cls, bot_id: str, status: bool = True) -> list[str]: ...

    @classmethod
    async def get_tasks(cls, bot_id: str | None = None, status: bool | None = True):
        """
        获取bot被动技能

        参数:
            bot_id (str | None, optional): bot_id. Defaults to None.
            status (bool | None, optional): 被动状态. Defaults to True.

        返回:
            dict[str, list[str]] | list[str]: 被动技能
        """
        if not bot_id:
            bots = await cls.filter().all()
            task_field: Literal["available_tasks", "block_tasks"] = (
                "available_tasks" if status else "block_tasks"
            )
            return {bot.bot_id: cls.convert_module_format(getattr(bot, task_field)) for bot in bots}
        else:
            bot = await cls.filter(bot_id=bot_id).first()
            if bot:
                tasks = bot.available_tasks if status else bot.block_tasks
                return cls.convert_module_format(tasks)
            return []

    @overload
    @classmethod
    async def get_plugins(cls) -> dict[str, list[str]]: ...

    @overload
    @classmethod
    async def get_plugins(cls, bot_id: str) -> list[str]: ...

    @overload
    @classmethod
    async def get_plugins(cls, *, status: bool) -> dict[str, list[str]]: ...

    @overload
    @classmethod
    async def get_plugins(cls, bot_id: str, status: bool = True) -> list[str]: ...

    @classmethod
    async def get_plugins(cls, bot_id: str | None = None, status: bool = True):
        """
        获取bot插件

        参数:
            bot_id (str | None, optional): bot_id. Defaults to None.
            status (bool, optional): 插件状态. Defaults to True.

        返回:
            dict[str, list[str]] | list[str]: 插件
        """
        if not bot_id:
            bots = await cls.filter().all()
            plugin_field = "available_plugins" if status else "block_plugins"
            return {bot.bot_id: cls.convert_module_format(getattr(bot, plugin_field)) for bot in bots}
        else:
            bot = await cls.filter(bot_id=bot_id).first()
            if bot:
                plugins = bot.available_plugins if status else bot.block_plugins
                return cls.convert_module_format(plugins)
            return []

    @classmethod
    async def set_bot_status(cls, status: bool, bot_id: str | None = None) -> None:
        """
        设置bot状态

        参数:
            status (bool): 状态
            bot_id (str, optional): bot_id. Defaults to None.

        Raises:
            ValueError: 未找到 bot_id
        """
        if bot_id:
            bot = await cls.filter(bot_id=bot_id).first()
            if not bot:
                raise ValueError(f"未找到 bot_id: {bot_id}")
            bot.status = status
            await bot.save()
        else:
            bots = await cls.filter().all()
            for bot in bots:
                bot.status = status
                await bot.save()

    @overload
    @classmethod
    def convert_module_format(cls, data: str) -> list[str]: ...

    @overload
    @classmethod
    def convert_module_format(cls, data: list[str]) -> str: ...

    @classmethod
    def convert_module_format(cls, data: str | list[str]) -> str | list[str]:
        """
        在 `<aaa,<bbb,<ccc,` 和 `["aaa", "bbb", "ccc"]` 之间进行相互转换。

        参数:
            data (str | list[str]): 输入数据，可能是格式化字符串或字符串列表。

        返回:
            str | list[str]: 根据输入类型返回转换后的数据。
        """
        if isinstance(data, str):
            return [item.strip(",") for item in data.split("<") if item]
        elif isinstance(data, list):
            return "".join(cls.format(item) for item in data)

    @classmethod
    async def _toggle_field(
        cls,
        bot_id: str,
        from_field: str,
        to_field: str,
        data: str,
    ) -> None:
        """
        在 from_field 和 to_field 之间移动指定的 data

        参数:
            bot_id (str): bot_id
            from_field (str): 源字段
            to_field (str): 目标字段
            data (str): 要移动的数据
        """
        bot = await cls.filter(bot_id=bot_id).first()
        
        if not bot:
            return
            
        from_value = getattr(bot, from_field)
        to_value = getattr(bot, to_field)
        
        from_list = cls.convert_module_format(from_value)
        if data in from_list:
            from_list.remove(data)
            from_value = cls.convert_module_format(from_list)
            setattr(bot, from_field, from_value)
        
        to_list = cls.convert_module_format(to_value)
        if data not in to_list:
            to_list.append(data)
            to_value = cls.convert_module_format(to_list)
            setattr(bot, to_field, to_value)
        
        await bot.save()

    @classmethod
    async def enable_plugin(cls, bot_id: str, module: str) -> None:
        """
        启用插件

        参数:
            bot_id (str): bot_id
            module (str): 模块名
        """
        await cls._toggle_field(bot_id, "block_plugins", "available_plugins", module)

    @classmethod
    async def disable_plugin(cls, bot_id: str, module: str) -> None:
        """
        禁用插件

        参数:
            bot_id (str): bot_id
            module (str): 模块名
        """
        await cls._toggle_field(bot_id, "available_plugins", "block_plugins", module)

    @classmethod
    async def enable_task(cls, bot_id: str, module: str) -> None:
        """
        启用被动技能

        参数:
            bot_id (str): bot_id
            module (str): 模块名
        """
        await cls._toggle_field(bot_id, "block_tasks", "available_tasks", module)

    @classmethod
    async def disable_task(cls, bot_id: str, module: str) -> None:
        """
        禁用被动技能

        参数:
            bot_id (str): bot_id
            module (str): 模块名
        """
        await cls._toggle_field(bot_id, "available_tasks", "block_tasks", module)

    @classmethod
    async def disable_all(cls, bot_id: str, func_type: str | None = None) -> None:
        """
        禁用所有插件和被动技能

        参数:
            bot_id (str): bot_id
            func_type (str | None): 功能类型，"tasks" 或 "plugins"，如果为None则禁用所有
        """
        bot = await cls.filter(bot_id=bot_id).first()
        
        if not bot:
            return
        
        if func_type == "plugins":
            available_plugins = cls.convert_module_format(bot.available_plugins)
            if available_plugins:
                block_plugins = cls.convert_module_format(bot.block_plugins)
                block_plugins.extend(available_plugins)
                bot.block_plugins = cls.convert_module_format(block_plugins)
                bot.available_plugins = ""
        elif func_type == "tasks":
            available_tasks = cls.convert_module_format(bot.available_tasks)
            if available_tasks:
                block_tasks = cls.convert_module_format(bot.block_tasks)
                block_tasks.extend(available_tasks)
                bot.block_tasks = cls.convert_module_format(block_tasks)
                bot.available_tasks = ""
        else:
            available_plugins = cls.convert_module_format(bot.available_plugins)
            if available_plugins:
                block_plugins = cls.convert_module_format(bot.block_plugins)
                block_plugins.extend(available_plugins)
                bot.block_plugins = cls.convert_module_format(block_plugins)
                bot.available_plugins = ""
            
            available_tasks = cls.convert_module_format(bot.available_tasks)
            if available_tasks:
                block_tasks = cls.convert_module_format(bot.block_tasks)
                block_tasks.extend(available_tasks)
                bot.block_tasks = cls.convert_module_format(block_tasks)
                bot.available_tasks = ""
        
        await bot.save()

    @classmethod
    async def enable_all(cls, bot_id: str, func_type: str | None = None) -> None:
        """
        启用所有插件和被动技能

        参数:
            bot_id (str): bot_id
            func_type (str | None): 功能类型，"tasks" 或 "plugins"，如果为None则启用所有
        """
        bot = await cls.filter(bot_id=bot_id).first()
        
        if not bot:
            return
        
        if func_type == "plugins":
            block_plugins = cls.convert_module_format(bot.block_plugins)
            if block_plugins:
                available_plugins = cls.convert_module_format(bot.available_plugins)
                available_plugins.extend(block_plugins)
                bot.available_plugins = cls.convert_module_format(available_plugins)
                bot.block_plugins = ""
        elif func_type == "tasks":
            block_tasks = cls.convert_module_format(bot.block_tasks)
            if block_tasks:
                available_tasks = cls.convert_module_format(bot.available_tasks)
                available_tasks.extend(block_tasks)
                bot.available_tasks = cls.convert_module_format(available_tasks)
                bot.block_tasks = ""
        else:
            block_plugins = cls.convert_module_format(bot.block_plugins)
            if block_plugins:
                available_plugins = cls.convert_module_format(bot.available_plugins)
                available_plugins.extend(block_plugins)
                bot.available_plugins = cls.convert_module_format(available_plugins)
                bot.block_plugins = ""
            
            block_tasks = cls.convert_module_format(bot.block_tasks)
            if block_tasks:
                available_tasks = cls.convert_module_format(bot.available_tasks)
                available_tasks.extend(block_tasks)
                bot.available_tasks = cls.convert_module_format(available_tasks)
                bot.block_tasks = ""
        
        await bot.save()

    @classmethod
    async def is_block_plugin(cls, bot_id: str, module: str) -> bool:
        """
        检查插件是否被禁用

        参数:
            bot_id (str): bot_id
            module (str): 模块名

        返回:
            bool: 是否被禁用
        """
        bot = await cls.filter(bot_id=bot_id).first()
        
        if not bot:
            return False
            
        block_plugins = cls.convert_module_format(bot.block_plugins)
        return module in block_plugins

    @classmethod
    async def is_block_task(cls, bot_id: str, module: str) -> bool:
        """
        检查被动技能是否被禁用

        参数:
            bot_id (str): bot_id
            module (str): 模块名

        返回:
            bool: 是否被禁用
        """
        bot = await cls.filter(bot_id=bot_id).first()
        
        if not bot:
            return False
            
        block_tasks = cls.convert_module_format(bot.block_tasks)
        return module in block_tasks
