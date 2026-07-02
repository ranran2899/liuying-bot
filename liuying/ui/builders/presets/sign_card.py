from typing import Any

from ...models.presets.sign_card import SignCardData
from ..base import BaseBuilder


class SignCardBuilder(BaseBuilder[SignCardData]):
    """
    签到卡片构建器。
    """

    def __init__(self, user_id: str, user_name: str, avatar_url: str):
        super().__init__(
            SignCardData(user_id=user_id, user_name=user_name, avatar_url=avatar_url),
            template_name="presets/sign_card",
        )

    def set_total_days(self, days: int) -> "SignCardBuilder":
        """
        设置累计签到天数。
        """
        self._data.total_days = days
        return self

    def set_consecutive_days(self, days: int) -> "SignCardBuilder":
        """
        设置连续签到天数。
        """
        self._data.consecutive_days = days
        return self

    def set_favor(self, level: int, exp: int, next_level_exp: int) -> "SignCardBuilder":
        """
        设置好感度信息。
        """
        self._data.favor_level = level
        self._data.favor_exp = exp
        self._data.next_level_exp = next_level_exp
        return self

    def set_reward(self, gold: int, favor: int) -> "SignCardBuilder":
        """
        设置奖励。
        """
        self._data.reward_gold = gold
        self._data.reward_favor = favor
        return self

    def set_duplicate(self, is_duplicate: bool) -> "SignCardBuilder":
        """
        设置是否重复签到。
        """
        self._data.is_duplicate = is_duplicate
        return self

    def set_greeting(self, greeting: str) -> "SignCardBuilder":
        """
        设置问候语。
        """
        self._data.greeting = greeting
        return self

    def set_current_time(self, time: str) -> "SignCardBuilder":
        """
        设置当前时间。
        """
        self._data.current_time = time
        return self

    def set_first_sign_date(self, date: str, meet_days: int) -> "SignCardBuilder":
        """
        设置首次签到日期。
        """
        self._data.first_sign_date = date
        self._data.meet_days = meet_days
        return self

    def set_extra_data(self, data: dict[str, Any]) -> "SignCardBuilder":
        """
        设置额外数据。
        """
        self._data.extra_data = data
        return self
