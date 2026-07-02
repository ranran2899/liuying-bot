from collections.abc import Iterable
from typing import Any

from pydantic import Field

from ..core.base import ContainerComponent, RenderableComponent


class SignCardData(ContainerComponent):
    """
    签到卡片组件的数据模型。
    """

    user_id: str = Field(..., description="用户ID")
    user_name: str = Field(..., description="用户名")
    avatar_url: str = Field(..., description="头像URL")
    total_days: int = Field(0, description="累计签到天数")
    consecutive_days: int = Field(0, description="连续签到天数")
    favor_level: int = Field(1, description="好感度等级")
    favor_exp: int = Field(0, description="当前好感度经验")
    next_level_exp: int = Field(100, description="下一级所需经验")
    reward_gold: int = Field(0, description="奖励金币")
    reward_favor: int = Field(0, description="奖励好感度")
    is_duplicate: bool = Field(False, description="是否重复签到")
    greeting: str = Field("", description="问候语")
    current_time: str = Field("", description="当前时间")
    first_sign_date: str | None = Field(None, description="首次签到日期")
    meet_days: int = Field(0, description="相遇天数")
    extra_data: dict[str, Any] | None = Field(None, description="额外数据")

    @property
    def template_name(self) -> str:
        return "presets/sign_card"

    def get_children(self) -> Iterable[RenderableComponent]:
        """
        返回子组件。
        """
        return []

    @property
    def progress_percentage(self) -> float:
        """
        计算进度百分比。
        """
        if self.next_level_exp <= 0:
            return 100
        return min(100, (self.favor_exp / self.next_level_exp) * 100)
