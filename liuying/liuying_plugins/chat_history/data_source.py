"""热门群聊数据源"""

from liuying.models._group import GroupConsole
from liuying.models.chat_history import ChatHistory
from liuying.utils.drawing_tool import DrawingTool
from liuying.utils.image import BuildImage

_MAX_RANK = 10

_DAY_DESC: dict[int, str] = {1: "今日", 7: "近7天", 30: "近30天"}


class ChatHistoryManager:
    """聊天记录统计管理类"""

    @classmethod
    async def get_hot_groups(cls, days: int | None = None) -> bytes | str:
        """获取热门群聊发言排行图。

        参数:
            days: 时间范围（天），为None时统计全部

        返回:
            bytes | str: 排行榜图片字节数据或提示消息
        """
        data_list = await ChatHistory.get_active_groups(days=days, limit=_MAX_RANK)
        if not data_list:
            return "暂无群聊发言数据..."

        data = []
        for group_id, count in data_list:
            group = await GroupConsole.get_group(group_id=group_id)
            name = group.group_name if group and group.group_name else group_id
            data.append((name, count))

        return await cls._draw_barh(data, cls._build_title(days))

    @classmethod
    def _build_title(cls, days: int | None) -> str:
        """构建排行标题。

        参数:
            days: 时间范围（天）

        返回:
            str: 标题字符串
        """
        desc = _DAY_DESC.get(days, f"近{days}天") if days else "全部"
        return f"{desc}热门群聊排行"

    @classmethod
    async def _draw_barh(
        cls, data: list[tuple[str, int]], title: str
    ) -> bytes:
        """绘制横向柱状排行图。

        参数:
            data: 数据列表 [(群名称, 发言次数), ...]
            title: 标题

        返回:
            bytes: 图像字节数据
        """
        bar_height = 40
        gap = 20
        padding = 50
        label_width = 260
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
                f"{i + 1}. {label}",
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
