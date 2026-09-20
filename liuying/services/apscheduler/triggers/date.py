"""
日期触发器
支持一次性定时任务的触发
"""

from datetime import datetime
from typing import Any, Self

from .base import BaseTrigger, register_trigger


@register_trigger("date")
class DateTrigger(BaseTrigger):
    """
    日期触发器

    用于一次性定时任务，在指定的日期时间执行一次任务。
    执行后触发器将不再返回有效的运行时间。
    """

    def __init__(
        self,
        run_date: datetime | str,
    ) -> None:
        super().__init__()

        self._run_date = self.parse_datetime(run_date)
        self._executed = False

    @property
    def run_date(self) -> datetime:
        """获取运行日期"""
        return self._run_date

    @property
    def is_executed(self) -> bool:
        """是否已执行"""
        return self._executed

    def mark_executed(self) -> None:
        """标记为已执行（防止暂停后恢复时重复执行）"""
        self._executed = True

    def get_next_run_time(
        self, previous_time: datetime | None = None
    ) -> datetime | None:
        """获取下次运行时间，已执行或无下次执行时返回 None"""
        return None if self._executed else self._run_date

    def to_config(self) -> dict[str, Any]:
        """转换为配置字典"""
        return {
            "run_date": self._run_date.isoformat(),
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Self:
        """从配置创建触发器"""
        return cls(run_date=config["run_date"])
