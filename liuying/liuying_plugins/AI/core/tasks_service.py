"""用户自定义任务服务

提供用户级 cron 定时任务的创建、取消、暂停、恢复、执行与启动恢复。
任务执行时向用户发送提醒消息（私聊或群聊）。

cron 表达式为标准 5 段式：分 时 日 月 周
示例：`0 8 * * *` 表示每天 8 点执行
"""

from datetime import datetime
import json

from nonebot import get_bot
from nonebot_plugin_alconna import Target

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..models.user_task import UserTask

_TASK_GROUP = "ai_user_task"
"""用户任务调度分组"""

__all__ = ["TaskService", "task_service"]


class TaskService:
    """用户自定义任务管理服务

    封装任务的 CRUD、调度注册/移除、执行回调与启动恢复。
    纯 ORM 操作不包裹异常，仅调度器调用与消息发送允许降级。
    """

    @staticmethod
    def _build_task_id(user_id: str, task_no: int) -> str:
        """构建调度器任务ID

        参数:
            user_id: 用户ID
            task_no: 任务序号

        返回:
            str: 调度器任务ID
        """
        return f"ai_user_task_{user_id}_{task_no}"

    @staticmethod
    def _parse_cron(cron_expr: str) -> dict:
        """解析 5 段式 cron 表达式

        参数:
            cron_expr: cron 表达式（分 时 日 月 周）

        返回:
            dict: add_cron 参数字典

        异常:
            ValueError: 表达式不是 5 段
        """
        fields = cron_expr.split()
        if len(fields) != 5:
            raise ValueError(
                "cron表达式必须是5段式: 分 时 日 月 周"
            )
        return {
            "minute": fields[0],
            "hour": fields[1],
            "day": fields[2],
            "month": fields[3],
            "day_of_week": fields[4],
        }

    @staticmethod
    def _extract_message(task: UserTask) -> str:
        """从任务中提取消息内容

        优先使用 params_json.message，为空时回退到 description。

        参数:
            task: 任务记录

        返回:
            str: 消息内容
        """
        params = json.loads(task.params_json or "{}")
        message = str(params.get("message", "") or "").strip()
        if not message:
            message = task.description.strip()
        return message

    @classmethod
    async def create_task(
        cls,
        user_id: str,
        cron_expr: str,
        message: str,
        description: str = "",
        group_id: str | None = None,
    ) -> UserTask:
        """创建用户定时任务

        参数:
            user_id: 用户ID
            cron_expr: cron 表达式
            message: 提醒消息内容
            description: 任务描述（为空时用 message）
            group_id: 群组ID（为空时私聊发送）

        返回:
            UserTask: 创建的任务记录

        异常:
            ValueError: cron 表达式非法
        """
        # 验证 cron 表达式（仅校验格式，实际解析在注册时进行）
        cls._parse_cron(cron_expr)

        task_no = await UserTask.next_task_no(user_id)
        params_json = json.dumps(
            {"message": message}, ensure_ascii=False
        )
        task = await UserTask.create(
            user_id=user_id,
            group_id=group_id,
            task_no=task_no,
            description=description or message[:200],
            cron_expr=cron_expr,
            action="remind",
            params_json=params_json,
            is_active=True,
            is_paused=False,
        )

        try:
            await cls._register_cron(task)
        except Exception as e:
            # 调度注册失败，回滚任务记录
            await task.delete()
            raise ValueError(
                f"调度注册失败: {e}"
            ) from e

        logger.info(
            f"用户 {user_id} 创建任务 #{task_no}: {cron_expr}",
            command="AI",
        )
        return task

    @classmethod
    async def cancel_task(
        cls, user_id: str, task_no: int
    ) -> bool:
        """取消用户任务（不可恢复）

        参数:
            user_id: 用户ID
            task_no: 任务序号

        返回:
            bool: 是否成功
        """
        task = await UserTask.get_by_no(user_id, task_no)
        if task is None or not task.is_active:
            return False

        task.is_active = False
        task.is_paused = False
        await task.save(
            update_fields=["is_active", "is_paused"]
        )
        await cls._unregister_cron(user_id, task_no)
        logger.info(
            f"用户 {user_id} 取消任务 #{task_no}",
            command="AI",
        )
        return True

    @classmethod
    async def pause_task(
        cls, user_id: str, task_no: int
    ) -> bool:
        """暂停用户任务（可恢复）

        参数:
            user_id: 用户ID
            task_no: 任务序号

        返回:
            bool: 是否成功
        """
        task = await UserTask.get_by_no(user_id, task_no)
        if (
            task is None
            or not task.is_active
            or task.is_paused
        ):
            return False

        task.is_paused = True
        await task.save(update_fields=["is_paused"])
        await cls._unregister_cron(user_id, task_no)
        logger.info(
            f"用户 {user_id} 暂停任务 #{task_no}",
            command="AI",
        )
        return True

    @classmethod
    async def resume_task(
        cls, user_id: str, task_no: int
    ) -> bool:
        """恢复已暂停的任务

        参数:
            user_id: 用户ID
            task_no: 任务序号

        返回:
            bool: 是否成功
        """
        task = await UserTask.get_by_no(user_id, task_no)
        if (
            task is None
            or not task.is_active
            or not task.is_paused
        ):
            return False

        task.is_paused = False
        await task.save(update_fields=["is_paused"])
        await cls._register_cron(task)
        logger.info(
            f"用户 {user_id} 恢复任务 #{task_no}",
            command="AI",
        )
        return True

    @classmethod
    async def list_tasks(
        cls, user_id: str, active_only: bool = False
    ) -> list[UserTask]:
        """列出用户任务"""
        return await UserTask.list_user_tasks(
            user_id, active_only=active_only
        )

    @classmethod
    async def execute_task(
        cls, user_id: str, task_no: int
    ) -> None:
        """执行用户任务（发送提醒消息）

        由调度器回调触发，查询最新任务状态后发送消息。
        消息发送失败时更新 last_status 为 failed。

        参数:
            user_id: 用户ID
            task_no: 任务序号
        """
        task = await UserTask.get_by_no(user_id, task_no)
        if (
            task is None
            or not task.is_active
            or task.is_paused
        ):
            return

        message = cls._extract_message(task)
        if not message:
            logger.debug(
                f"任务 #{task_no} 无消息内容，跳过",
                command="AI",
            )
            return

        try:
            await cls._send_task_message(task, message)
            task.last_status = "sent"
        except Exception as e:
            task.last_status = "failed"
            logger.warning(
                f"任务 #{task_no} 执行失败: {e}",
                command="AI",
                e=e,
            )

        task.last_executed_at = datetime.now()
        await task.save(
            update_fields=["last_executed_at", "last_status"]
        )

    @classmethod
    async def restore_tasks_on_startup(cls) -> int:
        """启动时恢复所有活跃用户任务

        遍历 is_active=True 且 is_paused=False 的任务，
        重新注册到调度器。

        返回:
            int: 恢复的任务数
        """
        tasks = await UserTask.list_active_tasks()
        restored = 0
        for task in tasks:
            try:
                await cls._register_cron(task)
                restored += 1
            except Exception as e:
                logger.warning(
                    f"恢复任务 #{task.task_no} "
                    f"({task.user_id}) 失败: {e}",
                    command="AI",
                    e=e,
                )
        logger.info(
            f"用户定时任务恢复完成: {restored}/{len(tasks)}",
            command="AI",
        )
        return restored

    @classmethod
    async def _register_cron(
        cls, task: UserTask
    ) -> None:
        """注册任务到调度器

        参数:
            task: 任务记录
        """
        user_id = task.user_id
        task_no = task.task_no

        async def _callback() -> None:
            await cls.execute_task(user_id, task_no)

        cron_params = cls._parse_cron(task.cron_expr)
        await task_manager.add_cron(
            task_id=cls._build_task_id(user_id, task_no),
            func=_callback,
            name=f"用户任务#{task_no}",
            group=_TASK_GROUP,
            replace_existing=True,
            **cron_params,
        )

    @classmethod
    async def _unregister_cron(
        cls, user_id: str, task_no: int
    ) -> None:
        """从调度器移除任务

        参数:
            user_id: 用户ID
            task_no: 任务序号
        """
        task_id = cls._build_task_id(user_id, task_no)
        try:
            await task_manager.remove_task(task_id)
        except Exception as e:
            logger.debug(
                f"移除调度任务 {task_id} 失败: {e}",
                command="AI",
                e=e,
            )

    @classmethod
    async def _send_task_message(
        cls, task: UserTask, message: str
    ) -> None:
        """发送任务提醒消息

        群组任务发送到群，否则发送私聊。

        参数:
            task: 任务记录
            message: 消息内容
        """
        bot = get_bot()
        if task.group_id:
            target = Target(
                id=str(task.group_id), private=False
            )
        else:
            target = Target(
                id=str(task.user_id), private=True
            )
        await MessageUtils.build_message(message).send(
            target=target, bot=bot
        )


task_service = TaskService
"""用户任务服务单例（类方法形式，无需实例化）"""
