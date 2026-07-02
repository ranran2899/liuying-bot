from collections import Counter
from datetime import datetime, timedelta
from typing import ClassVar, Literal, TypeAlias

from liuying.models._group import GroupConsole
from liuying.models._group import GroupInfoUser
from liuying.models.plugin_info import PluginInfo
from liuying.models.statistics import Statistics
from liuying.utils.drawing_tool import DrawingTool, create_text_image
from liuying.utils.enum import PluginType
from liuying.utils.image import BuildImage

SearchType: TypeAlias = Literal["day", "week", "month"] | None


class StatisticsManage:
    """统计数据管理类"""

    _DAY_CONFIG: ClassVar[dict[SearchType, tuple[int, str]]] = {
        "day": (1, "日"),
        "week": (7, "周"),
        "month": (30, "月"),
        None: (None, ""),
    }

    @classmethod
    async def get_statistics(
        cls,
        plugin_name: str | None,
        is_global: bool,
        search_type: SearchType,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> bytes | str | None:
        """获取统计数据。

        参数:
            plugin_name: 插件名称
            is_global: 是否全局统计
            search_type: 搜索类型 (day/week/month)
            user_id: 用户ID
            group_id: 群组ID

        返回:
            bytes | str | None: 图像字节数据或错误消息
        """
        day, day_type = cls._DAY_CONFIG.get(search_type, (None, ""))
        title = await cls._build_title(user_id, group_id, day_type, day, is_global)

        if is_global and not user_id:
            return await cls._query_statistics(
                plugin_name, day, None, None, title
            )

        if user_id:
            return await cls._query_statistics(
                plugin_name, day, user_id, group_id, title
            )

        if group_id:
            return await cls._query_statistics(
                plugin_name, day, None, group_id, title
            )

        return None

    @classmethod
    async def _build_title(
        cls,
        user_id: str | None,
        group_id: str | None,
        day_type: str,
        day: int | None,
        is_global: bool,
    ) -> str:
        """构建统计标题。

        参数:
            user_id: 用户ID
            group_id: 群组ID
            day_type: 时间类型描述
            day: 天数
            is_global: 是否全局统计

        返回:
            str: 标题字符串
        """
        day_desc = f"{day_type}({day}天)" if day_type and day else ""
        prefix = "全局 " if is_global and not user_id else ""

        match (user_id, group_id):
            case (uid, _) if uid:
                user = await GroupInfoUser.filter(user_id=uid).first()
                name = user.user_name if user else uid
                return f"{prefix}{name} {day_desc}功能调用统计"
            case (_, gid) if gid:
                group = await GroupConsole.get_group(group_id=gid)
                name = group.group_name if group else gid
                return f"{prefix}{name} {day_desc}功能调用统计"
            case _:
                return f"{prefix}功能调用统计"

    @classmethod
    async def _query_statistics(
        cls,
        plugin_name: str | None,
        day: int | None,
        user_id: str | None,
        group_id: str | None,
        title: str,
    ) -> bytes | str:
        """查询统计数据。

        参数:
            plugin_name: 插件名称
            day: 天数
            user_id: 用户ID
            group_id: 群组ID
            title: 标题

        返回:
            bytes | str: 图像字节数据或错误消息
        """
        query = Statistics.filter()

        if user_id:
            query = query.filter(user_id=user_id)
        if group_id:
            query = query.filter(group_id=group_id)
        if plugin_name:
            query = query.filter(plugin_name=plugin_name)
        if day:
            start_time = datetime.now() - timedelta(days=day)
            query = query.where_gte("create_time", start_time)

        data_list = await query.all()
        plugin_count = Counter(data.plugin_name for data in data_list)

        if not plugin_count:
            return "统计数据为空..."

        return await cls._build_image(list(plugin_count.items()), title)

    @classmethod
    async def _build_image(
        cls, data_list: list[tuple[str, int]], title: str
    ) -> bytes:
        """构建统计图表。

        参数:
            data_list: 数据列表 [(插件名称, 调用次数), ...]
            title: 标题

        返回:
            bytes: 图像字节数据
        """
        module2count = dict(data_list)
        plugin_info = await PluginInfo.filter(
            load_status=True,
            plugin_type=PluginType.NORMAL,
        ).where_in("module", list(module2count.keys())).all()

        data = [
            (plugin.name, module2count.get(plugin.module, 0))
            for plugin in plugin_info
        ]

        if not data:
            return create_text_image("统计数据为空...", font_size=20)

        return await cls._draw_barh(data, title)

    @classmethod
    async def _draw_barh(
        cls, data: list[tuple[str, int]], title: str
    ) -> bytes:
        """绘制横向柱状图。

        参数:
            data: 数据列表 [(标签, 数值), ...]
            title: 标题

        返回:
            bytes: 图像字节数据
        """
        bar_height = 40
        gap = 20
        padding = 50
        label_width = 150
        chart_width = 400

        max_value = max(v for _, v in data) if data else 1
        total_height = padding * 2 + len(data) * (bar_height + gap)
        total_width = padding * 2 + label_width + chart_width

        tool = DrawingTool(
            width=total_width, height=total_height, background_color="white"
        )

        title_font = BuildImage.load_font(font_size=18)
        await tool.canvas.text(
            (total_width // 2, 20),
            title,
            fill="black",
            font=title_font,
            center_type="width",
        )

        label_font = BuildImage.load_font(font_size=14)
        value_font = BuildImage.load_font(font_size=12)

        for i, (label, value) in enumerate(data):
            y = padding + i * (bar_height + gap)

            await tool.canvas.text(
                (padding, y + bar_height // 2),
                label,
                fill="black",
                font=label_font,
            )

            bar_width = (value / max_value) * chart_width
            bar_x = padding + label_width
            await tool.canvas.rectangle(
                (bar_x, y, bar_x + bar_width, y + bar_height),
                fill=(54, 162, 235),
            )

            await tool.canvas.text(
                (bar_x + bar_width + 10, y + bar_height // 2),
                str(value),
                fill="black",
                font=value_font,
            )

        return tool.get_bytes()
