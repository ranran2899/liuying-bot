"""群上下文与时间上下文管理

提供群风格管理、时间时段判断、活动状态描述等。
"""

from datetime import datetime
from typing import ClassVar

from ...models.group_context import GroupContextSnapshot


class ContextManager:
    """上下文管理器

    管理群上下文和时间上下文，为AI对话提供场景信息。
    """

    _TIME_PERIODS: ClassVar[list[tuple[int, int, str]]] = [
        (0, 6, "深夜"),
        (6, 9, "清晨"),
        (9, 12, "上午"),
        (12, 14, "中午"),
        (14, 18, "下午"),
        (18, 22, "傍晚"),
        (22, 24, "夜晚"),
    ]
    """时段定义表（start, end, name）"""

    _TIME_FLAVOR_MAP: ClassVar[dict[str, str]] = {
        "深夜": "\n[时段氛围] 深夜到凌晨，正常应该在休息或准备睡觉，"
                "话题更安静、慵懒，不宜太亢奋。",
        "清晨": "\n[时段氛围] 清晨，刚起床，适合迷糊地冒一句。",
        "上午": "\n[时段氛围] 上午，通常在工作或学习。",
        "中午": "\n[时段氛围] 午休时间，适合轻松话题。",
        "下午": "\n[时段氛围] 下午时段，工作学习间隙。",
        "傍晚": "\n[时段氛围] 晚上自由时间，"
                "适合聊游戏、番剧、随便扯淡。",
        "夜晚": "\n[时段氛围] 夜深了，应该准备休息，或者已经在熬夜。",
    }
    """时段氛围提示映射表"""

    _REST_START = 0
    """休息开始时间"""

    _REST_END = 6
    """休息结束时间"""

    _NIGHT_START = 23
    """深夜开始时间"""

    _NIGHT_END = 6
    """深夜结束时间"""

    _GROUP_QUIET_START = 0
    """群深夜静默开始时间"""

    _GROUP_QUIET_END = 7
    """群深夜静默结束时间"""

    def get_current_time_period(self) -> str:
        """获取当前时段

        返回:
            str: 时段名称（深夜/清晨/上午/中午/下午/傍晚/夜晚）
        """
        hour = datetime.now().hour
        for start, end, name in self._TIME_PERIODS:
            if start <= hour < end:
                return name
        return "夜晚"

    def get_activity_status(self) -> str:
        """获取活动状态描述

        返回:
            str: 活动状态描述文本
        """
        period = self.get_current_time_period()
        match period:
            case "深夜":
                return "现在是深夜，大部分人都在休息"
            case "清晨":
                return "清晨时分，新的一天开始了"
            case "上午":
                return "上午时段，大家应该在工作或学习"
            case "中午":
                return "午休时间"
            case "下午":
                return "下午时段"
            case "傍晚":
                return "傍晚时分，一天的工作接近尾声"
            case "夜晚":
                return "夜晚时光"
            case _:
                return ""

    def build_time_prompt(self) -> str:
        """构建时间提示注入块

        返回:
            str: 时间提示文本，用于注入系统提示词
        """
        now = datetime.now()
        period = self.get_current_time_period()
        time_str = now.strftime("%H:%M")
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
            now.weekday()
        ]
        return (
            f"\n\n[当前时间上下文]\n"
            f"时间: {weekday} {time_str}\n"
            f"时段: {period}\n"
            f"状态: {self.get_activity_status()}"
        )

    def is_rest_time(self) -> bool:
        """判断是否休息时间

        返回:
            bool: 是否在休息时段（深夜0-6点）
        """
        hour = datetime.now().hour
        return self._REST_START <= hour < self._REST_END

    def is_night_time(self) -> bool:
        """判断是否深夜时段

        返回:
            bool: 是否在深夜时段（23-7点，跨午夜）
        """
        hour = datetime.now().hour
        return hour >= self._NIGHT_START or hour < self._NIGHT_END

    def is_group_active_hour(
        self,
        group_id: str | None,
        quiet_start: int | None = None,
        quiet_end: int | None = None,
    ) -> bool:
        """判断群活跃时段（跨午夜支持）

        参数:
            group_id: 群组ID
            quiet_start: 静默开始小时，None时用默认_GROUP_QUIET_START
            quiet_end: 静默结束小时，None时用默认_GROUP_QUIET_END

        返回:
            bool: True表示活跃可发，False表示处于深夜静默时段
        """
        start = (
            int(quiet_start)
            if quiet_start is not None
            else self._GROUP_QUIET_START
        )
        end = (
            int(quiet_end)
            if quiet_end is not None
            else self._GROUP_QUIET_END
        )
        hour = datetime.now().hour
        if start < end:
            return not (start <= hour < end)
        if start > end:
            return not (hour >= start or hour < end)
        return True

    def get_time_flavor_prompt(self) -> str:
        """获取时段氛围提示文本

        基于 _TIME_FLAVOR_MAP 映射表查找当前时段氛围，
        复用 get_current_time_period() 避免重复的时段判断。

        返回:
            str: 时段氛围提示，用于注入系统提示词
        """
        period = self.get_current_time_period()
        return self._TIME_FLAVOR_MAP.get(period, "")

    async def get_group_style(self, group_id: str) -> str:
        """获取群风格

        参数:
            group_id: 群组ID

        返回:
            str: 群风格描述，无则返回空串
        """
        ctx = await GroupContextSnapshot.get_context(group_id)
        return ctx.style if ctx else ""

    async def set_group_style(
        self, group_id: str, style: str
    ) -> GroupContextSnapshot:
        """设置群风格

        参数:
            group_id: 群组ID
            style: 群风格描述

        返回:
            GroupContextSnapshot: 更新后的群上下文
        """
        return await GroupContextSnapshot.update_context(
            group_id=group_id, style=style
        )

    async def get_group_context(
        self, group_id: str
    ) -> GroupContextSnapshot | None:
        """获取群上下文

        参数:
            group_id: 群组ID

        返回:
            GroupContextSnapshot | None: 群上下文快照
        """
        return await GroupContextSnapshot.get_context(group_id)

    async def update_group_activity(
        self, group_id: str
    ) -> GroupContextSnapshot:
        """更新群活动时间

        参数:
            group_id: 群组ID

        返回:
            GroupContextSnapshot: 更新后的群上下文
        """
        return await GroupContextSnapshot.update_context(group_id=group_id)

    def build_group_prompt(self, group_id: str | None) -> str:
        """构建群上下文提示（同步部分）

        参数:
            group_id: 群组ID，None为私聊

        返回:
            str: 群上下文提示文本
        """
        if not group_id:
            return "\n\n[会话场景] 私聊"
        return f"\n\n[会话场景] 群组: {group_id}"

    async def build_full_context_prompt(
        self, group_id: str | None
    ) -> str:
        """构建完整上下文提示

        参数:
            group_id: 群组ID

        返回:
            str: 完整上下文提示
        """
        prompt = self.build_time_prompt()
        if group_id:
            style = await self.get_group_style(group_id)
            if style:
                prompt += f"\n群风格: {style}"
            prompt += self.build_group_prompt(group_id)
        else:
            prompt += self.build_group_prompt(None)
        return prompt


context_manager = ContextManager()
"""上下文管理器单例"""
