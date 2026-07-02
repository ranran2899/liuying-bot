"""初始化任务"""

import nonebot
from nonebot import get_loaded_plugins
from nonebot.drivers import Driver
from nonebot.plugin import Plugin
from nonebot.utils import is_coroutine_callable

from liuying.configs.utils import PluginExtraData, Task
from liuying.models._group import GroupConsole
from liuying.models.task_info import TaskInfo
from liuying.utils.apscheduler import task_manager
from liuying.utils.common_utils import CommonUtils
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

driver: Driver = nonebot.get_driver()


async def _handle_setting(
    plugin: Plugin,
    task_info_list: list[tuple[bool, TaskInfo]],
    task_list: list[Task],
) -> None:
    """处理插件设置

    参数:
        plugin: Plugin 实例
        task_info_list: 被动技能db数据列表
        task_list: 被动技能列表
    """
    metadata = plugin.metadata
    if not metadata:
        return

    extra = metadata.extra
    extra_data = PluginExtraData(**extra)

    if extra_data.tasks:
        task_info_list.extend(
            (
                task.create_status,
                TaskInfo(
                    module=task.module,
                    name=task.name,
                    status=task.status,
                    default_status=task.default_status,
                ),
            )
            for task in extra_data.tasks
        )
        task_list.extend(extra_data.tasks)


async def update_to_group(create_list: list[tuple[bool, TaskInfo]]) -> None:
    """根据创建时状态对群组进行被动技能更新

    参数:
        create_list: 被动技能创建列表
    """
    if not (blocks := [t[1].module for t in create_list if not t[0]]):
        return

    if not (group_list := await GroupConsole.filter().all()):
        return

    for group in group_list:
        block_tasks = list(
            set(CommonUtils.convert_module_format(group.block_task) + blocks)
        )
        group.block_task = CommonUtils.convert_module_format(block_tasks)

    await GroupConsole.filter().bulk_update(group_list, ["block_task"])


async def to_db(
    load_task: list[str],
    create_list: list[tuple[bool, TaskInfo]],
    update_list: list[TaskInfo],
) -> None:
    """将被动技能保存至数据库

    参数:
        load_task: 已加载的被动技能模块
        create_list: 被动技能创建列表
        update_list: 被动技能更新列表
    """
    if create_list:
        _create_list = [t[1] for t in create_list]
        await TaskInfo.filter().bulk_create(_create_list)
        await update_to_group(create_list)

    if update_list:
        await TaskInfo.filter().bulk_update(
            update_list,
            ["run_time", "name", "status"],
        )

    if load_task:
        await TaskInfo.filter(TaskInfo.module.in_(load_task)).update(load_status=True)
        await TaskInfo.filter(~TaskInfo.module.in_(load_task)).update(load_status=False)


async def get_run_task(task: Task, *args, **kwargs) -> None:
    """获取并运行任务

    参数:
        task: 任务实例
    """
    is_run = await _check_task_condition(task)

    if is_run and task.run_func:
        if is_coroutine_callable(task.run_func):
            await task.run_func(*args, **kwargs)
        else:
            task.run_func(*args, **kwargs)


async def _check_task_condition(task: Task) -> bool:
    """检查任务执行条件

    参数:
        task: 任务实例

    返回:
        是否满足执行条件
    """
    if task.check:
        if is_coroutine_callable(task.check):
            return bool(await task.check(*task.check_args))
        return bool(task.check(*task.check_args))

    if not task.check_args or len(task.check_args) < 2:
        logger.warning(
            f"被动技能 {task.name}({task.module}) 缺少 check_args 参数, "
            f"需要 [bot, group_id], 跳过执行"
        )
        return False

    bot = task.check_args[0]
    group_id = task.check_args[1]
    return not await CommonUtils.task_is_block(bot, task.module, group_id)


def _build_trigger_config(scheduler_model) -> dict[str, int]:
    """构建触发器配置

    参数:
        scheduler_model: 调度器模型

    返回:
        触发器配置字典
    """
    config = {}
    if scheduler_model.hour is not None:
        config["hour"] = scheduler_model.hour
    if scheduler_model.minute is not None:
        config["minute"] = scheduler_model.minute
    if scheduler_model.second is not None:
        config["second"] = scheduler_model.second
    return config


async def create_schedule(task: Task) -> None:
    """动态创建定时任务

    参数:
        task: 任务实例
    """
    scheduler_model = task.scheduler
    if not scheduler_model or not task.run_func:
        return

    try:
        trigger = scheduler_model.trigger
        base_kwargs = {
            "task_id": scheduler_model.id,
            "func": get_run_task,
            "name": task.name,
            "args": scheduler_model.args,
            "kwargs": scheduler_model.kwargs,
            "max_instances": scheduler_model.max_instances,
        }

        match trigger:
            case "cron":
                trigger_config = _build_trigger_config(scheduler_model)
                await task_manager.add_cron_task(**base_kwargs, **trigger_config)
            case "interval":
                trigger_config = _build_trigger_config(scheduler_model)
                interval_config = {
                    k.replace("minute", "minutes").replace("hour", "hours"): v
                    for k, v in trigger_config.items()
                }
                await task_manager.add_interval_task(**base_kwargs, **interval_config)
            case "date" if scheduler_model.run_date:
                await task_manager.add_date_task(
                    **base_kwargs,
                    run_date=scheduler_model.run_date,
                )

        logger.debug(f"成功动态创建定时任务: {task.name}({task.module})")
    except Exception as e:
        logger.error(f"动态创建定时任务 {task.name}({task.module}) 失败", e=e)


@PriorityLifecycle.on_startup(priority=5)
async def _() -> None:
    """初始化插件数据配置"""
    task_list: list[Task] = []
    task_info_list: list[tuple[bool, TaskInfo]] = []

    for plugin in get_loaded_plugins():
        await _handle_setting(plugin, task_info_list, task_list)

    if not task_info_list:
        await TaskInfo.filter().update(load_status=False)
        return

    module_dict = {
        t[1]: t[0] for t in await TaskInfo.filter().values_list("id", "module")
    }
    load_task = []
    create_list = []
    update_list = []

    for status, task in task_info_list:
        if task.module not in module_dict:
            create_list.append((status, task))
        else:
            task.id = module_dict[task.module]
            update_list.append(task)
        load_task.append(task.module)

    await to_db(load_task, create_list, update_list)

    for task in task_list:
        if task.scheduler and task.run_func:
            await create_schedule(task)
