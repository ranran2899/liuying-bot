"""用户定时任务命令处理

注册查看、创建、取消、暂停、恢复用户定时任务的命令。
cron 表达式用逗号分隔 5 段（如 0,8,*,*,* 表示每天8点）。
"""

from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.message import MessageUtils

from ...config import get_config
from ...core.tasks_service import task_service

__all__ = ["setup_task_commands"]

_CRON_HELP = (
    "cron格式(逗号分隔5段): 分,时,日,月,周\n"
    "示例: 0,8,*,*,* = 每天8点\n"
    "      30,9,*,*,1-5 = 工作日9:30\n"
    "      0,*,*,*,* = 每小时"
)


def setup_task_commands() -> None:
    """注册用户定时任务相关matcher"""
    if not get_config("USER_TASKS_ENABLED", True):
        return

    list_cmd = on_alconna(
        Alconna("bot任务列表"),
        aliases={"AI任务列表", "bot定时任务", "AI定时任务"},
        priority=49,
        block=True,
    )

    create_cmd = on_alconna(
        Alconna(
            "bot任务创建",
            Args["cron", str]["message", str],
        ),
        aliases={"AI任务创建"},
        priority=49,
        block=True,
    )

    cancel_cmd = on_alconna(
        Alconna("bot任务取消", Args["task_no", str]),
        aliases={"AI任务取消"},
        priority=49,
        block=True,
    )

    pause_cmd = on_alconna(
        Alconna("bot任务暂停", Args["task_no", str]),
        aliases={"AI任务暂停"},
        priority=49,
        block=True,
    )

    resume_cmd = on_alconna(
        Alconna("bot任务恢复", Args["task_no", str]),
        aliases={"AI任务恢复"},
        priority=49,
        block=True,
    )

    @list_cmd.handle()
    async def _handle_list(session: Uninfo) -> None:
        """列出用户的所有定时任务"""
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
            status = TaskCommandsHelper._format_status(task)
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

    @create_cmd.handle()
    async def _handle_create(
        session: Uninfo,
        cron: str = "",
        message: str = "",
    ) -> None:
        """创建定时任务"""
        if not cron or not message:
            await MessageUtils.build_message(
                "格式: bot任务创建 <cron> <消息>\n"
                f"{_CRON_HELP}\n"
                "示例: bot任务创建 0,8,*,*,* 喝水"
            ).finish()
            return

        user_id = session.user.id
        group_id = (
            session.scene.id
            if session.scene.is_group
            else None
        )
        cron_expr = cron.replace(",", " ")
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

        await MessageUtils.build_message(
            f"任务已创建 #{task.task_no}\n"
            f"cron: {task.cron_expr}\n"
            f"消息: {message}\n"
            f"发送到: {'群' if group_id else '私聊'}"
        ).finish()

    @cancel_cmd.handle()
    async def _handle_cancel(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """取消定时任务"""
        no = TaskCommandsHelper._parse_no(task_no)
        if no is None:
            await MessageUtils.build_message(
                "请输入任务编号，如: bot任务取消 1"
            ).finish()
            return

        ok = await task_service.cancel_task(
            session.user.id, no
        )
        msg = (
            f"任务 #{no} 已取消"
            if ok
            else f"未找到任务 #{no} 或已取消"
        )
        await MessageUtils.build_message(msg).finish()

    @pause_cmd.handle()
    async def _handle_pause(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """暂停定时任务"""
        no = TaskCommandsHelper._parse_no(task_no)
        if no is None:
            await MessageUtils.build_message(
                "请输入任务编号，如: bot任务暂停 1"
            ).finish()
            return

        ok = await task_service.pause_task(
            session.user.id, no
        )
        msg = (
            f"任务 #{no} 已暂停"
            if ok
            else f"未找到任务 #{no} 或已暂停"
        )
        await MessageUtils.build_message(msg).finish()

    @resume_cmd.handle()
    async def _handle_resume(
        session: Uninfo, task_no: str = ""
    ) -> None:
        """恢复定时任务"""
        no = TaskCommandsHelper._parse_no(task_no)
        if no is None:
            await MessageUtils.build_message(
                "请输入任务编号，如: bot任务恢复 1"
            ).finish()
            return

        ok = await task_service.resume_task(
            session.user.id, no
        )
        msg = (
            f"任务 #{no} 已恢复"
            if ok
            else f"未找到任务 #{no} 或未暂停"
        )
        await MessageUtils.build_message(msg).finish()


class TaskCommandsHelper:
    """任务命令辅助工具类"""

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
