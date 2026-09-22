"""任务命令逻辑

用户定时任务的查看、创建、取消、暂停与恢复业务处理。
cron 表达式用逗号分隔 5 段（如 0,8,*,*,* 表示每天8点）。
"""

from nonebot_plugin_uninfo import Uninfo

from liuying.utils.message import MessageUtils

from ..config import get_config
from ..core.runtime import Feature, runtime_switch
from ..core.tasks_service import task_service

__all__ = [
    "TaskCommands",
]

_CRON_HELP = (
    "cron格式(逗号分隔5段): 分,时,日,月,周\n"
    "示例: 0,8,*,*,* = 每天8点\n"
    "      30,9,*,*,1-5 = 工作日9:30\n"
    "      0,*,*,*,* = 每小时"
)

_MAX_TASKS_PER_USER = 10
"""每用户进行中任务数上限"""

_MAX_MESSAGE_LENGTH = 500
"""任务消息长度上限（字符）"""


class TaskCommands:
    """任务命令逻辑

    matcher 在插件 __init__ 统一注册，此处仅承接业务逻辑。
    """

    @staticmethod
    def _parse_no(task_no: str) -> int | None:
        """解析任务编号

        参数:
            task_no: 用户输入的任务编号字符串

        返回:
            int | None: 编号，非法返回 None
        """
        if not isinstance(task_no, str):
            return None
        stripped = task_no.strip()
        if not stripped.isdigit():
            return None
        no = int(stripped)
        return no if no > 0 else None

    @staticmethod
    def _format_status(task) -> str:
        """格式化任务状态标签

        参数:
            task: UserTask 记录

        返回:
            str: 状态标签文本
        """
        if not task.is_active:
            return "已取消"
        if task.is_paused:
            return "已暂停"
        return "运行中"

    @staticmethod
    async def _run_task_action(
        session: Uninfo,
        task_no: str,
        action: str,
        verb: str,
    ) -> str:
        """执行单个任务操作并生成结果文案

        参数:
            session: 会话信息
            task_no: 用户输入的任务编号字符串
            action: task_service 的操作名（cancel/pause/resume）
            verb: 操作动词，用于提示与结果文案

        返回:
            str: 结果文案
        """
        no = TaskCommands._parse_no(task_no)
        if no is None:
            return f"请输入任务编号，如: bot任务{verb} 1"
        service_fn = getattr(task_service, f"{action}_task")
        ok = await service_fn(session.user.id, no)
        fail_hint = "或未暂停" if action == "resume" else f"或已{verb}"
        if ok:
            return f"任务 #{no} 已{verb}"
        return f"未找到任务 #{no} {fail_hint}"

    @staticmethod
    async def handle_list(session: Uninfo) -> None:
        """列出用户的所有定时任务"""
        if not await TaskCommands._check_task_enabled(session):
            return

        user_id = session.user.id
        group_id = (
            session.scene.id
            if session.scene.is_group
            else None
        )
        tasks = await task_service.list_tasks(user_id)
        if not tasks:
            await MessageUtils.build_message(
                "暂无定时任务\n"
                "使用 bot任务创建 <cron> <消息> 创建\n"
                f"{_CRON_HELP}"
            ).finish()
            return

        lines = [f"定时任务列表（共{len(tasks)}个）:"]
        for task in tasks:
            status = TaskCommands._format_status(task)
            cron_display = task.cron_expr.replace(" ", ",")
            desc = task.description[:30] if task.description else ""
            lines.append(
                f"#{task.task_no} [{status}] "
                f"{cron_display} | {desc}"
            )
        lines.append(f"\n当前场景: {'群' if group_id else '私聊'}")
        await MessageUtils.build_message(
            "\n".join(lines)
        ).finish()

    @staticmethod
    async def handle_create(
        session: Uninfo,
        cron: str = "",
        message: str = "",
    ) -> None:
        """创建定时任务

        创建前依次执行三道防线：cron 分钟位频率限制、
        消息长度上限截断、每用户进行中任务数上限。
        """
        if not await TaskCommands._check_task_enabled(session):
            return

        if not cron or not message:
            await MessageUtils.build_message(
                "格式: bot任务创建 <cron> <消息>\n"
                f"{_CRON_HELP}\n"
                "示例: bot任务创建 0,8,*,*,* 喝水"
            ).finish()
            return

        # 防线一: 分钟位为 * 表示每分钟执行，拒绝以防刷屏
        cron_expr = cron.replace(",", " ")
        fields = cron_expr.split()
        if fields and fields[0] == "*":
            await MessageUtils.build_message(
                "创建失败: 每分钟执行会刷屏，任务间隔至少5分钟\n"
                "分钟位请使用具体数值或 */5 等间隔形式\n"
                f"{_CRON_HELP}"
            ).finish()
            return

        # 防线二: 消息超长时截断到上限
        truncated = len(message) > _MAX_MESSAGE_LENGTH
        if truncated:
            message = message[:_MAX_MESSAGE_LENGTH]

        user_id = session.user.id
        group_id = (
            session.scene.id
            if session.scene.is_group
            else None
        )

        # 防线三: 每用户进行中任务数上限
        active_tasks = await task_service.list_tasks(
            user_id, active_only=True
        )
        if len(active_tasks) >= _MAX_TASKS_PER_USER:
            await MessageUtils.build_message(
                "创建失败: 进行中的任务已达上限"
                f"{_MAX_TASKS_PER_USER}个\n"
                "可先用 bot任务取消 释放名额，"
                "bot任务列表 查看现有任务"
            ).finish()
            return

        try:
            task = await task_service.create_task(
                user_id=user_id,
                cron_expr=cron_expr,
                message=message,
                description=message,
                group_id=group_id,
            )
        except ValueError as e:
            await MessageUtils.build_message(
                f"创建失败: {e}\n{_CRON_HELP}"
            ).finish()
            return

        reply = (
            f"任务已创建 #{task.task_no}\n"
            f"cron: {task.cron_expr}\n"
            f"消息: {message}\n"
            f"发送到: {'群' if group_id else '私聊'}"
        )
        if truncated:
            reply += f"\n提示: 消息超过{_MAX_MESSAGE_LENGTH}字，已截断"
        await MessageUtils.build_message(reply).finish()

    @staticmethod
    async def handle_cancel(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """取消定时任务"""
        if not await TaskCommands._check_task_enabled(session):
            return
        msg = await TaskCommands._run_task_action(
            session, task_no, "cancel", "取消"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def handle_pause(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """暂停定时任务"""
        if not await TaskCommands._check_task_enabled(session):
            return
        msg = await TaskCommands._run_task_action(
            session, task_no, "pause", "暂停"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def handle_resume(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """恢复定时任务"""
        if not await TaskCommands._check_task_enabled(session):
            return
        msg = await TaskCommands._run_task_action(
            session, task_no, "resume", "恢复"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def _check_task_enabled(session: Uninfo) -> bool:
        """任务功能前置校验：AI总开关 + 任务开关

        用户/群组黑名单已由流萤本体 hooks/auth_ban 在事件级拦截。

        参数:
            session: 会话信息

        返回:
            bool: 是否允许继续处理
        """
        if not runtime_switch.is_enabled(Feature.AI):
            return False
        if not get_config("USER_TASKS_ENABLED", True):
            return False
        return True
