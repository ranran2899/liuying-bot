"""用户自定义任务数据模型

定义 UserTask，存储用户创建的定时任务。
支持 cron 表达式调度，任务执行时向用户发送提醒消息。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_MAX_TASK_NO = 9999
"""任务序号上限"""


class UserTask(Model):
    """用户自定义任务模型

    存储用户创建的定时任务，包括 cron 表达式、动作类型、参数等。
    通过 task_no 字段实现用户内的任务编号（如 task_001）。
    """

    __tablename__ = "ai_user_task"
    __table_args__: ClassVar[dict] = {
        "comment": "AI用户自定义定时任务表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="创建者用户ID"
    )
    """创建者用户ID"""

    group_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="群组ID"
    )
    """群组ID（为空时私聊发送）"""

    task_no: Mapped[int] = mapped_column(
        Integer, comment="用户内任务序号"
    )
    """用户内任务序号（1开始）"""

    description: Mapped[str] = mapped_column(
        String(255), default="", comment="任务描述"
    )
    """任务描述"""

    cron_expr: Mapped[str] = mapped_column(
        String(128), comment="cron表达式（5段式）"
    )
    """cron表达式（分 时 日 月 周）"""

    action: Mapped[str] = mapped_column(
        String(32), default="remind", comment="动作类型"
    )
    """动作类型（remind/未来扩展）"""

    params_json: Mapped[str] = mapped_column(
        Text, default="{}", comment="动作参数JSON"
    )
    """动作参数JSON（如消息内容）"""

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用"
    )
    """是否启用（取消时置False）"""

    is_paused: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否暂停"
    )
    """是否暂停（暂停时跳过执行但保留调度）"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    """创建时间"""

    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="上次执行时间"
    )
    """上次执行时间"""

    last_status: Mapped[str] = mapped_column(
        String(16), default="pending", comment="上次执行状态"
    )
    """上次执行状态（pending/sent/failed）"""

    cache_type = "AI_USER_TASK"
    """缓存类型"""

    cache_key_field = ("user_id", "task_no")
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本

        为旧表补齐 is_paused 列，兼容 SQLite/MySQL/PostgreSQL。
        若列已存在，ADD COLUMN 会失败并被捕获回滚，安全幂等。
        """
        return [
            "ALTER TABLE ai_user_task "
            "ADD COLUMN is_paused BOOLEAN DEFAULT 0;",
        ]

    @classmethod
    async def next_task_no(cls, user_id: str) -> int:
        """获取用户下一个任务序号

        参数:
            user_id: 用户ID

        返回:
            int: 下一个任务序号（从1开始）
        """
        last = await (
            cls.filter(user_id=user_id)
            .order_by("-task_no")
            .first()
        )
        if last is None:
            return 1
        return min(last.task_no + 1, _MAX_TASK_NO)

    @classmethod
    async def get_by_no(
        cls, user_id: str, task_no: int
    ) -> "UserTask | None":
        """按用户ID和任务序号查询

        参数:
            user_id: 用户ID
            task_no: 任务序号

        返回:
            UserTask | None: 任务记录
        """
        return await cls.filter(
            user_id=user_id, task_no=task_no
        ).first()

    @classmethod
    async def list_user_tasks(
        cls, user_id: str, active_only: bool = False
    ) -> list["UserTask"]:
        """列出用户所有任务

        参数:
            user_id: 用户ID
            active_only: 是否只列出启用的任务

        返回:
            list[UserTask]: 任务列表（按序号升序）
        """
        query = cls.filter(user_id=user_id)
        if active_only:
            query = query.filter(is_active=True)
        return await query.order_by("task_no").all()

    @classmethod
    async def list_active_tasks(cls) -> list["UserTask"]:
        """列出所有启用且未暂停的任务（启动恢复用）

        返回:
            list[UserTask]: 全局活跃任务列表
        """
        return await cls.filter(
            is_active=True, is_paused=False
        ).all()
