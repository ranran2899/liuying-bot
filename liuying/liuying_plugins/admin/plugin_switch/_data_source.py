from liuying.models._group import GroupConsole
from liuying.models.plugin_info import PluginInfo
from liuying.models.task_info import TaskInfo
from liuying.services.cache import CacheRoot
from liuying.utils.common_utils import CommonUtils
from liuying.utils.enum import BlockType, CacheType, PluginType
from liuying.utils.exception import GroupInfoNotFound
from liuying.utils.image import BuildImage, ImageTemplate, RowStyle


def plugin_row_style(column: str, text: str) -> RowStyle:
    """被动技能文本风格

    参数:
        column: 表头
        text: 文本内容

    返回:
        RowStyle: RowStyle
    """
    style = RowStyle()
    if (column == "全局状态" and text == "开启") or (
        column != "全局状态" and column == "加载状态" and text == "SUCCESS"
    ):
        style.font_color = "#67C23A"
    elif column in {"全局状态", "加载状态"}:
        style.font_color = "#F56C6C"
    return style


async def build_plugin() -> BuildImage:
    column_name = [
        "ID",
        "模块",
        "名称",
        "全局状态",
        "禁用类型",
        "加载状态",
        "菜单分类",
        "作者",
        "版本",
        "金币花费",
    ]

    plugin_list = await PluginInfo.filter(
        PluginInfo.plugin_type != PluginType.HIDDEN
    ).all()

    column_data = [
        [
            plugin.id,
            plugin.module,
            plugin.name,
            "开启" if plugin.status else "关闭",
            plugin.block_type,
            "SUCCESS" if plugin.load_status else "ERROR",
            plugin.menu_type,
            plugin.author,
            plugin.version,
            plugin.cost_gold,
        ]
        for plugin in plugin_list
    ]
    return await ImageTemplate.table_page(
        "Plugin",
        "插件状态",
        column_name,
        column_data,
        text_style=plugin_row_style,
    )


def task_row_style(column: str, text: str) -> RowStyle:
    """被动技能文本风格

    参数:
        column: 表头
        text: 文本内容

    返回:
        RowStyle: RowStyle
    """
    style = RowStyle()
    if column in {"群组状态", "全局状态"}:
        style.font_color = "#67C23A" if text == "开启" else "#F56C6C"
    return style


async def build_task(group_id: str | None) -> BuildImage:
    """构造被动技能状态图片

    参数:
        group_id: 群组id

    异常:
        GroupInfoNotFound: 未找到群组

    返回:
        BuildImage: 被动技能状态图片
    """
    task_list = await TaskInfo.filter().all()

    column_name = ["ID", "模块", "名称", "群组状态", "全局状态", "运行时间"]
    group = None
    if group_id:
        group = await GroupConsole.get_group(group_id=group_id)
        if not group:
            raise GroupInfoNotFound()
    else:
        column_name.remove("群组状态")

    column_data = []
    for task in task_list:
        if group:
            column_data.append(
                [
                    task.id,
                    task.module,
                    task.name,
                    "开启" if f"<{task.module}," not in group.block_task else "关闭",
                    "开启" if task.status else "关闭",
                    task.run_time or "-",
                ]
            )
        else:
            column_data.append(
                [
                    task.id,
                    task.module,
                    task.name,
                    "开启" if task.status else "关闭",
                    task.run_time or "-",
                ]
            )
    return await ImageTemplate.table_page(
        "Task",
        "被动技能状态",
        column_name,
        column_data,
        text_style=task_row_style,
    )


class PluginManager:
    # ==================== 插件查找 ====================

    @classmethod
    async def _find_plugin(cls, plugin_name: str):
        """查找插件

        参数:
            plugin_name: 插件名称或ID

        返回:
            PluginInfo | None: 插件对象，不存在返回None
        """
        if plugin_name.isdigit():
            return await PluginInfo.filter(PluginInfo.id == int(plugin_name)).first()
        return await PluginInfo.filter(
            PluginInfo.name == plugin_name,
            PluginInfo.load_status == True,  # noqa: E712
            PluginInfo.plugin_type != PluginType.PARENT,
        ).first()

    # ==================== 插件全局状态 ====================

    @classmethod
    async def set_default_status(cls, plugin_name: str, status: bool) -> str:
        """设置插件进群默认状态

        参数:
            plugin_name: 插件名称
            status: 状态

        返回:
            str: 返回信息
        """
        plugin = await cls._find_plugin(plugin_name)
        if plugin:
            plugin.default_status = status
            await plugin.save()
            status_text = "开启" if status else "关闭"
            return f"成功将 {plugin.name} 进群默认状态修改为: {status_text}"
        return "没有找到这个功能喔..."

    @classmethod
    async def set_all_plugin_status(
        cls, status: bool, is_default: bool = False, group_id: str | None = None
    ) -> str:
        """修改所有插件状态

        参数:
            status: 状态
            is_default: 是否进群默认.
            group_id: 指定群组id.

        返回:
            str: 返回信息
        """
        if is_default:
            plugins = await PluginInfo.filter(
                PluginInfo.plugin_type == PluginType.NORMAL
            ).all()
            for plugin in plugins:
                plugin.default_status = status
                await plugin.save()
            return f"成功将所有功能进群默认状态修改为: {'开启' if status else '关闭'}"

        if group_id:
            group = await GroupConsole.get_group(group_id, channel_id=None)
            if group:
                module_list = await PluginInfo.filter(
                    PluginInfo.plugin_type == PluginType.NORMAL
                ).values_list("module", flat=True)
                if status:
                    group.block_plugin = ""
                else:
                    group.block_plugin = CommonUtils.convert_module_format(module_list)
                await group.save()
                return f"成功将此群组所有功能状态修改为: {'开启' if status else '关闭'}"
            return "获取群组失败..."

        plugins = await PluginInfo.filter(
            PluginInfo.plugin_type == PluginType.NORMAL
        ).all()
        for plugin in plugins:
            plugin.status = status
            plugin.block_type = None if status else BlockType.ALL
            await plugin.save()

        await CacheRoot.invalidate_cache(CacheType.PLUGINS)
        return f"成功将所有功能全局状态修改为: {'开启' if status else '关闭'}"

    @classmethod
    async def block(cls, module: str):
        """禁用

        参数:
            module: 模块名
        """
        if plugin := await PluginInfo.get_plugin(module=module):
            plugin.status = False
            await plugin.save()
            await CacheRoot.invalidate_cache(CacheType.PLUGINS)

    @classmethod
    async def unblock(cls, module: str):
        """启用

        参数:
            module: 模块名
        """
        if plugin := await PluginInfo.get_plugin(module=module):
            plugin.status = True
            await plugin.save()
            await CacheRoot.invalidate_cache(CacheType.PLUGINS)

    # ==================== 插件群组状态 ====================

    @classmethod
    async def block_group_plugin(cls, plugin_name: str, group_id: str) -> str:
        """禁用群组插件

        参数:
            plugin_name: 插件名称
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_plugin(plugin_name, group_id, False)

    @classmethod
    async def unblock_group_plugin(cls, plugin_name: str, group_id: str) -> str:
        """启用群组插件

        参数:
            plugin_name: 插件名称
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_plugin(plugin_name, group_id, True)

    @classmethod
    async def _change_group_plugin(
        cls, plugin_name: str, group_id: str, status: bool
    ) -> str:
        """修改群组插件状态

        参数:
            plugin_name: 插件名称
            group_id: 群组id
            status: 插件状态

        返回:
            str: 返回信息
        """
        plugin = await cls._find_plugin(plugin_name)
        if plugin:
            status_str = "开启" if status else "关闭"
            if status:
                if await GroupConsole.is_normal_block_plugin(group_id, plugin.module):
                    await GroupConsole.set_unblock_plugin(group_id, plugin.module)
                    return f"已成功{status_str} {plugin.name} 功能!"
            elif not await GroupConsole.is_normal_block_plugin(group_id, plugin.module):
                await GroupConsole.set_block_plugin(group_id, plugin.module)
                return f"已成功{status_str} {plugin.name} 功能!"
            return f"该功能已经{status_str}了喔，不要重复{status_str}..."
        return "没有找到这个功能喔..."

    # ==================== 被动技能全局状态 ====================

    @classmethod
    async def _set_global_task_status(
        cls, name: str, status: bool, is_default: bool = False
    ) -> str:
        """设置全局被动技能状态

        参数:
            name: 被动技能名称
            status: 状态值（True=开启，False=关闭）
            is_default: 是否为默认状态

        返回:
            str: 操作结果消息
        """
        task = await TaskInfo.filter(TaskInfo.name == name).first()
        if task:
            if is_default:
                task.default_status = status
            else:
                task.status = status
            await task.save()
            action = "开启" if status else "禁用"
            scope = "被动进群默认状态" if is_default else "被动状态"
            return f"已全局{action}{scope} {name}"
        return "没有找到这个被动技能..."

    @classmethod
    async def block_global_task(cls, name: str, is_default: bool = False) -> str:
        """禁用全局被动技能

        参数:
            name: 被动技能名称

        返回:
            str: 返回信息
        """
        return await cls._set_global_task_status(name, False, is_default)

    @classmethod
    async def unblock_global_task(cls, name: str, is_default: bool = False) -> str:
        """开启全局被动技能

        参数:
            name: 被动技能名称
            is_default: 是否为默认状态

        返回:
            str: 返回信息
        """
        return await cls._set_global_task_status(name, True, is_default)

    @classmethod
    async def _set_all_global_tasks_status(
        cls, status: bool, is_default: bool = False
    ) -> str:
        """设置所有全局被动技能状态

        参数:
            status: 状态值（True=开启，False=关闭）
            is_default: 是否为默认状态

        返回:
            str: 操作结果消息
        """
        tasks = await TaskInfo.filter().all()
        for task in tasks:
            if is_default:
                task.default_status = status
            else:
                task.status = status
            await task.save()
        action = "开启" if status else "禁用"
        scope = "被动进群默认状态" if is_default else "被动状态"
        return f"已{action}所有{scope}"

    @classmethod
    async def block_global_all_task(cls, is_default: bool) -> str:
        """禁用全局被动技能

        返回:
            str: 返回信息
        """
        return await cls._set_all_global_tasks_status(False, is_default)

    @classmethod
    async def unblock_global_all_task(cls, is_default: bool) -> str:
        """开启全局被动技能

        参数:
            is_default: 是否为默认状态

        返回:
            str: 返回信息
        """
        return await cls._set_all_global_tasks_status(True, is_default)

    # ==================== 被动技能群组状态 ====================

    @classmethod
    async def block_group_task(cls, task_name: str, group_id: str) -> str:
        """禁用被动技能

        参数:
            task_name: 被动技能名称
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_task(task_name, group_id, True)

    @classmethod
    async def unblock_group_task(cls, task_name: str, group_id: str) -> str:
        """启用被动技能

        参数:
            task_name: 被动技能名称
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_task(task_name, group_id, False)

    @classmethod
    async def block_group_all_task(cls, group_id: str) -> str:
        """禁用所有被动技能

        参数:
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_task("", group_id, True, True)

    @classmethod
    async def unblock_group_all_task(cls, group_id: str) -> str:
        """启用所有被动技能

        参数:
            group_id: 群组id

        返回:
            str: 返回信息
        """
        return await cls._change_group_task("", group_id, False, True)

    @classmethod
    async def _change_group_task(
        cls, task_name: str, group_id: str, status: bool, is_all: bool = False
    ) -> str:
        """改变群组被动技能状态

        参数:
            task_name: 被动技能名称
            group_id: 群组Id
            status: 状态，为True时是关闭
            is_all: 所有群被动

        返回:
            str: 返回信息
        """
        status_str = "关闭" if status else "开启"
        if is_all:
            module_list = await TaskInfo.filter().values_list("module", flat=True)
            if module_list:
                group = await GroupConsole.filter(
                    GroupConsole.group_id == group_id, GroupConsole.channel_id is None
                ).first()

                if not group:
                    group = GroupConsole(
                        group_id=group_id,
                        channel_id=None,
                        block_plugin="",
                        block_task="",
                    )
                    await group.save()

                if status:
                    group.block_task = CommonUtils.convert_module_format(module_list)
                else:
                    group.block_task = ""
                await group.save()
                return f"已成功{status_str}全部被动技能!"
        else:
            task = await TaskInfo.filter(TaskInfo.name == task_name).first()
            if task:
                if status:
                    await GroupConsole.set_block_task(group_id, task.module)
                elif await GroupConsole.is_superuser_block_task(group_id, task.module):
                    return (
                        f"{status_str} {task_name} 被动技能失败，"
                        f"当前群组该被动已被管理员禁用"
                    )
                else:
                    await GroupConsole.set_unblock_task(group_id, task.module)
                return f"已成功{status_str} {task_name} 被动技能!"
        return "没有找到这个被动技能喔..."

    # ==================== 群组休眠/醒来 ====================

    @classmethod
    async def is_wake(cls, group_id: str) -> bool:
        """是否醒来

        参数:
            group_id: 群组id

        返回:
            bool: 是否醒来
        """
        group = await GroupConsole.get_group(group_id=group_id)
        return group.status if group else False

    @classmethod
    async def sleep(cls, group_id: str):
        """休眠

        参数:
            group_id: 群组id
        """
        await cls._set_group_status(group_id, False)

    @classmethod
    async def wake(cls, group_id: str):
        """醒来

        参数:
            group_id: 群组id
        """
        await cls._set_group_status(group_id, True)

    @classmethod
    async def _set_group_status(cls, group_id: str, status: bool):
        """设置群组状态（休眠/醒来）

        参数:
            group_id: 群组id
            status: 状态
        """
        group = await GroupConsole.filter(
            GroupConsole.group_id == group_id, GroupConsole.channel_id is None
        ).first()

        if not group:
            group = GroupConsole(
                group_id=group_id,
                channel_id=None,
                status=status,
                block_plugin="",
                block_task="",
                superuser_block_plugin="",
            )
            await group.save()
        else:
            group.status = status
            await group.save()

    # ==================== 超级用户操作 ====================

    @classmethod
    async def superuser_block(
        cls, plugin_name: str, block_type: BlockType | None, group_id: str | None
    ) -> str:
        """超级用户禁用插件

        参数:
            plugin_name: 插件名称
            block_type: 禁用类型
            group_id: 群组id

        返回:
            str: 返回信息
        """
        plugin = await cls._find_plugin(plugin_name)
        if not plugin:
            return "没有找到这个功能喔..."

        if group_id:
            return await cls._handle_superuser_group_plugin(
                group_id, plugin.module, plugin_name, True
            )

        plugin.block_type = block_type
        plugin.status = not bool(block_type)
        await plugin.save()
        await CacheRoot.invalidate_cache(CacheType.PLUGINS)
        return cls._get_block_type_message(plugin.name, block_type, is_block=True)

    @classmethod
    async def superuser_unblock(
        cls, plugin_name: str, block_type: BlockType | None, group_id: str | None
    ) -> str:
        """超级用户开启插件

        参数:
            plugin_name: 插件名称
            block_type: 禁用类型
            group_id: 群组id

        返回:
            str: 返回信息
        """
        plugin = await cls._find_plugin(plugin_name)
        if not plugin:
            return "没有找到这个功能喔..."

        if group_id:
            return await cls._handle_superuser_group_plugin(
                group_id, plugin.module, plugin_name, False
            )

        plugin.block_type = block_type
        plugin.status = not bool(block_type)
        await plugin.save()
        await CacheRoot.invalidate_cache(CacheType.PLUGINS)
        return cls._get_block_type_message(plugin.name, block_type, is_block=False)

    @classmethod
    async def superuser_task_handle(
        cls, task_name: str, group_id: str | None, status: bool
    ) -> str:
        """超级用户禁用被动技能

        参数:
            task_name: 被动技能名称
            group_id: 群组id
            status: 状态

        返回:
            str: 返回信息
        """
        task = await TaskInfo.filter(TaskInfo.name == task_name).first()
        if not task:
            return "没有找到这个功能喔..."
        if group_id:
            if status:
                await GroupConsole.set_unblock_task(group_id, task.module, True)
            else:
                await GroupConsole.set_block_task(group_id, task.module, True)
            status_str = "开启" if status else "关闭"
            return f"已成功将群组 {group_id} 被动技能 {task_name} {status_str}!"
        return "没有找到这个群组喔..."

    @classmethod
    def _get_block_type_message(
        cls, plugin_name: str, block_type: BlockType | None, *, is_block: bool
    ) -> str:
        """根据禁用类型生成消息

        参数:
            plugin_name: 插件名称
            block_type: 禁用类型
            is_block: 是否为禁用操作

        返回:
            str: 操作结果消息
        """
        action = "关闭" if is_block else "开启"
        match block_type:
            case None:
                return f"已成功将 {plugin_name} 全局启用!"
            case BlockType.ALL:
                return f"已成功将 {plugin_name} 全局{action}!"
            case BlockType.GROUP:
                return f"已成功将 {plugin_name} 全局群组{action}!"
            case BlockType.PRIVATE:
                return f"已成功将 {plugin_name} 全局私聊{action}!"

    @classmethod
    async def _handle_superuser_group_plugin(
        cls, group_id: str, plugin_module: str, plugin_name: str, block: bool
    ) -> str:
        """处理超级用户群组插件操作

        参数:
            group_id: 群组ID
            plugin_module: 插件模块名
            plugin_name: 插件名称
            block: 是否禁用

        返回:
            str: 操作结果消息
        """
        is_blocked = await GroupConsole.is_superuser_block_plugin(
            group_id, plugin_module
        )
        if block and is_blocked:
            return "此群组该功能已被超级用户关闭，不要重复关闭..."
        if not block and not is_blocked:
            return "此群组该功能已被超级用户开启，不要重复开启..."

        if block:
            await GroupConsole.set_block_plugin(group_id, plugin_module, True)
        else:
            await GroupConsole.set_unblock_plugin(group_id, plugin_module, True)
        action = "关闭" if block else "开启"
        return f"已成功{action}群组 {group_id} 的 {plugin_name} 功能!"
