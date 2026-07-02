"""通用排行榜图片生成工具模块

提供专门用于排行榜图片生成的 BuildRankMat 类
基于 BuildImage 类扩展，针对排行榜场景优化

功能特性：
- 支持自定义表头文字和数量
- 支持多键排名显示，可同时展示多个数据维度
- 支持动态列宽计算，根据表头数量自动调整布局
- 提供通用数据格式化接口，支持自定义格式化函数
- 支持自定义颜色主题和样式
- 支持头像列、趋势箭头、进度条扩展
"""

from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar, TypeAlias

from PIL import Image

from liuying.utils.image._build_image import BuildImage, _to_rgb

ColorValue: TypeAlias = str | tuple[int, int, int]
DataValue: TypeAlias = int | str | float

TREND_ARROW_UP = "↑"
TREND_ARROW_DOWN = "↓"
TREND_ARROW_FLAT = "→"


class BuildRankMat:
    """通用排行榜图片生成类

    用于生成各种排行榜的图片，支持动态列数、自定义列宽和表头文字
    """

    __slots__ = ("canvas", "colors", "content_font", "height", "title_font", "width")

    DEFAULT_COLORS: ClassVar[dict[str, ColorValue]] = {
        "background": "#FFFFFF",
        "header": "#333333",
        "rank1": "#FFD700",
        "rank2": "#C0C0C0",
        "rank3": "#CD7F32",
        "normal": "#333333",
        "zebra": (250, 250, 250),
    }

    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        background_color: ColorValue = "#FFFFFF",
        font_path: str | None = None,
        font_size: int = 24,
        colors: dict[str, ColorValue] | None = None,
    ):
        """初始化排行榜图片生成器

        参数:
            width: 图片宽度
            height: 图片高度
            background_color: 背景颜色
            font_path: 字体文件路径
            font_size: 字体大小
            colors: 自定义颜色配置
        """
        self.width = width
        self.height = height
        font_name = font_path or "HYWenHei-85W.ttf"
        self.canvas = BuildImage(width, height, font=font_name, font_size=font_size)

        self.colors = self.DEFAULT_COLORS | {"background": background_color}
        if colors:
            self.colors |= colors

        self.title_font = BuildImage.load_font(
            font=font_name, font_size=int(font_size * 1.5)
        )
        self.content_font = BuildImage.load_font(font=font_name, font_size=font_size)

    def _get_color(self, color_key: str) -> tuple[int, int, int]:
        """获取颜色值，支持16进制颜色转换为RGB

        参数:
            color_key: 颜色键名

        返回:
            tuple[int, int, int]: RGB颜色元组
        """
        color = self.colors.get(color_key, "#000000")
        return _to_rgb(color)

    def _calculate_column_widths(
        self, num_columns: int, custom_widths: list[int] | None = None
    ) -> list[int]:
        """计算列宽

        参数:
            num_columns: 列数
            custom_widths: 自定义列宽列表

        返回:
            list[int]: 列宽列表
        """
        if custom_widths and len(custom_widths) == num_columns:
            return custom_widths

        rank_column_width = 80
        available_width = self.width - 100 - rank_column_width
        other_columns_width = (
            available_width // (num_columns - 1) if num_columns > 1 else available_width
        )

        return [rank_column_width] + [other_columns_width] * (num_columns - 1)

    def _format_data_value(
        self, value: DataValue, formatter: Callable[[Any], str] | None = None
    ) -> str:
        """格式化数据值

        参数:
            value: 原始数据值
            formatter: 自定义格式化函数

        返回:
            str: 格式化后的字符串
        """
        if formatter:
            return formatter(value)

        match value:
            case int():
                return f"{value:,}"
            case float():
                return f"{value:.2f}"
            case _:
                return str(value)

    def _get_trend_arrow(self, current: DataValue, previous: DataValue | None) -> str:
        """获取趋势箭头

        参数:
            current: 当前值
            previous: 上次值

        返回:
            str: 趋势箭头字符
        """
        if previous is None:
            return ""
        try:
            if current > previous:
                return TREND_ARROW_UP
            if current < previous:
                return TREND_ARROW_DOWN
            return TREND_ARROW_FLAT
        except TypeError:
            return ""

    async def _draw_table_header(
        self, y_position: int, header_texts: list[str], column_widths: list[int]
    ):
        """绘制表头

        参数:
            y_position: Y坐标位置
            header_texts: 表头文字列表
            column_widths: 列宽列表
        """
        header_height = 40
        bg_color = self._get_color("background")

        await self.canvas.rectangle(
            (50, y_position, self.width - 50, y_position + header_height), fill=bg_color
        )

        header_color = self._get_color("header")
        current_x = 60

        for text, column_width in zip(header_texts, column_widths):
            text_width, text_height = BuildImage.get_text_size(text, self.content_font)
            text_x = current_x + (column_width - text_width) // 2
            text_y = y_position + (header_height - text_height) // 2

            await self.canvas.text(
                (text_x, text_y), text, fill=header_color, font=self.content_font
            )

            current_x += column_width

    async def _draw_rank_row(
        self,
        rank: int,
        user_id: str,
        data_values: list[DataValue] | DataValue,
        y_position: int,
        row_height: int,
        header_texts: list[str],
        column_widths: list[int],
        formatters: list[Callable[[Any], str] | None] | None = None,
        avatars: dict[str, BuildImage | bytes | None] | None = None,
        trends: list[DataValue | None] | None = None,
    ):
        """绘制排行榜行

        参数:
            rank: 排名
            user_id: 用户ID
            data_values: 数据值或数据值列表
            y_position: Y坐标位置
            row_height: 行高
            header_texts: 表头文字列表
            column_widths: 列宽列表
            formatters: 数据格式化函数列表
            avatars: 用户头像映射（user_id -> BuildImage/bytes/None）
            trends: 趋势数据列表，与多列数据对应
        """
        values = [data_values] if not isinstance(data_values, list) else data_values
        rank_color = self._get_color(f"rank{rank}" if rank <= 3 else "normal")

        if rank % 2 == 0:
            zebra_color = self._get_color("zebra")
            await self.canvas.rectangle(
                (50, y_position, self.width - 50, y_position + row_height),
                fill=zebra_color,
            )

        normal_color = self._get_color("normal")
        current_x = 60

        for i, (header_text, column_width) in enumerate(
            zip(header_texts, column_widths)
        ):
            match i:
                case 0:
                    cell_text = str(rank)
                    cell_color = rank_color
                case 1:
                    if avatars and user_id in avatars:
                        await self._draw_avatar(
                            avatars[user_id], current_x, y_position, row_height
                        )
                    cell_text = (
                        user_id if len(user_id) <= 15 else f"{user_id[:12]}..."
                    )
                    cell_color = normal_color
                case _:
                    data_index = i - 2
                    if data_index < len(values):
                        data_value = values[data_index]
                        formatter = (
                            formatters[data_index]
                            if formatters and data_index < len(formatters)
                            else None
                        )
                        cell_text = self._format_data_value(data_value, formatter)
                        if trends and data_index < len(trends):
                            arrow = self._get_trend_arrow(
                                data_value, trends[data_index]
                            )
                            if arrow:
                                cell_text = f"{cell_text} {arrow}"
                    else:
                        cell_text = "-"
                    cell_color = normal_color

            text_width, text_height = BuildImage.get_text_size(
                cell_text, self.content_font
            )
            text_x = current_x + (column_width - text_width) // 2
            text_y = y_position + (row_height - text_height) // 2

            await self.canvas.text(
                (text_x, text_y), cell_text, fill=cell_color, font=self.content_font
            )

            current_x += column_width

    async def _draw_avatar(
        self,
        avatar: BuildImage | bytes,
        x: int,
        y: int,
        row_height: int,
        size: int = 30,
    ):
        """绘制头像

        参数:
            avatar: 头像数据（BuildImage 或 bytes）
            x: X坐标
            y: Y坐标
            row_height: 行高
            size: 头像尺寸
        """
        match avatar:
            case bytes():
                avatar_img = BuildImage(size, size, background=BytesIO(avatar))
            case BuildImage():
                avatar_img = avatar
            case _:
                return
        await avatar_img.circle()
        avatar_y = y + (row_height - size) // 2
        await self.canvas.paste(avatar_img, (x, avatar_y))

    async def _draw_title(self, rank_name: str) -> int:
        """绘制标题并返回表头 Y 坐标

        参数:
            rank_name: 排行榜名称

        返回:
            int: 表头起始 Y 坐标
        """
        title_width, title_height = BuildImage.get_text_size(rank_name, self.title_font)
        title_x = (self.width - title_width) // 2
        title_y = 30
        title_color = self._get_color("normal")

        await self.canvas.text(
            (title_x, title_y), rank_name, fill=title_color, font=self.title_font
        )
        return title_y + title_height + 30

    def _create_canvas_with_background(self, background_image: str | Path | bytes):
        """创建带有背景图片的画布

        参数:
            background_image: 背景图片路径或字节数据
        """
        match background_image:
            case bytes():
                bg_img = Image.open(BytesIO(background_image))
            case _:
                bg_img = Image.open(background_image)

        canvas = BuildImage(width=self.width, height=self.height, color="#FFFFFF")

        bg_width, bg_height = bg_img.size
        width_ratio = self.width / bg_width
        height_ratio = self.height / bg_height
        scale_ratio = max(width_ratio, height_ratio)

        new_width = int(bg_width * scale_ratio)
        new_height = int(bg_height * scale_ratio)
        resized_bg = bg_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        crop_height = min(new_height, self.height)
        cropped_bg = (
            resized_bg.crop((0, 0, new_width, crop_height))
            if new_height > self.height
            else resized_bg
        )

        x_offset = (self.width - cropped_bg.width) // 2
        canvas.mark_img.paste(cropped_bg, (x_offset, 0))
        self.canvas = canvas

    async def generate_rank(
        self,
        user_ids: list[str],
        user_data: list[DataValue] | list[list[DataValue]],
        rank_name: str,
        header_texts: list[str] | None = None,
        column_widths: list[int] | None = None,
        formatters: list[Callable[[Any], str] | None] | None = None,
        num: int = 10,
        background_image: str | Path | bytes | None = None,
        avatars: dict[str, BuildImage | bytes | None] | None = None,
        trends: list[list[DataValue | None]] | None = None,
        sort_column: int = 0,
    ) -> BuildImage:
        """生成通用排行榜（统一支持单键与多键排名）

        参数:
            user_ids: 用户ID列表
            user_data: 用户数据列表，单列时为一维列表，多列时为二维列表
            rank_name: 排行榜名称
            header_texts: 自定义表头文字列表
            column_widths: 自定义列宽列表
            formatters: 数据格式化函数列表
            num: 显示数量
            background_image: 背景图片路径或字节数据
            avatars: 用户头像映射（user_id -> 头像数据）
            trends: 趋势数据（与多列数据对应，每个用户一个列表）
            sort_column: 排序依据的列索引

        返回:
            BuildImage: 生成的排行榜图片
        """
        multi_mode = bool(user_data) and isinstance(user_data[0], list)
        headers = header_texts or (
            ["排名", "用户", "数据值"] if not multi_mode else ["排名", "用户", "数据1"]
        )
        column_widths = self._calculate_column_widths(len(headers), column_widths)

        if background_image:
            self._create_canvas_with_background(background_image)

        num = min(num, len(user_ids))
        ranked_data = self._sort_rank_data(
            user_ids, user_data, sort_column, multi_mode
        )[:num]

        header_y = await self._draw_title(rank_name)
        await self._draw_table_header(header_y, headers, column_widths)

        row_height = 40
        current_y = header_y + 50

        for rank, (user_id, data_value) in enumerate(ranked_data, 1):
            user_trends = (
                trends[rank - 1] if trends and rank - 1 < len(trends) else None
            )
            await self._draw_rank_row(
                rank=rank,
                user_id=user_id,
                data_values=data_value,
                y_position=current_y,
                row_height=row_height,
                header_texts=headers,
                column_widths=column_widths,
                formatters=formatters,
                avatars=avatars,
                trends=user_trends,
            )
            current_y += row_height

        return self.canvas

    async def generate_multi_rank(
        self,
        user_ids: list[str],
        user_data_list: list[list[DataValue]],
        rank_name: str,
        header_texts: list[str],
        column_widths: list[int] | None = None,
        formatters: list[Callable[[Any], str] | None] | None = None,
        num: int = 10,
        background_image: str | Path | bytes | None = None,
        sort_column: int = 0,
    ) -> BuildImage:
        """生成多键排行榜（兼容入口，内部委托 generate_rank）

        参数:
            user_ids: 用户ID列表
            user_data_list: 用户数据列表，每个元素是一个包含多个数据值的列表
            rank_name: 排行榜名称
            header_texts: 表头文字列表
            column_widths: 自定义列宽列表
            formatters: 数据格式化函数列表
            num: 显示数量
            background_image: 背景图片路径或字节数据
            sort_column: 排序依据的列索引

        返回:
            BuildImage: 生成的排行榜图片
        """
        return await self.generate_rank(
            user_ids=user_ids,
            user_data=user_data_list,
            rank_name=rank_name,
            header_texts=header_texts,
            column_widths=column_widths,
            formatters=formatters,
            num=num,
            background_image=background_image,
            sort_column=sort_column,
        )

    def _sort_rank_data(
        self,
        user_ids: list[str],
        user_data: list[DataValue] | list[list[DataValue]],
        sort_column: int,
        multi_mode: bool,
    ) -> list[tuple[str, DataValue | list[DataValue]]]:
        """排序排行榜数据（统一处理单键与多键）

        参数:
            user_ids: 用户ID列表
            user_data: 用户数据列表
            sort_column: 排序列索引
            multi_mode: 是否多键模式

        返回:
            list: 排序后的 (user_id, data) 列表
        """
        if multi_mode:
            return sorted(
                zip(user_ids, user_data),
                key=lambda x: (
                    x[1][sort_column]
                    if len(x[1]) > sort_column
                    and isinstance(x[1][sort_column], int | float)
                    else 0
                ),
                reverse=True,
            )
        return sorted(
            zip(user_ids, user_data),
            key=lambda x: x[1] if isinstance(x[1], int | float) else 0,
            reverse=True,
        )

    def pic2bs4(self) -> str:
        """将图片转换为base64格式

        返回:
            str: base64格式的图片数据
        """
        return self.canvas.pic2bs4()

    def pic2bytes(self) -> bytes:
        """将图片转换为bytes格式

        返回:
            bytes: 图片字节数据
        """
        return self.canvas.pic2bytes()

    async def save(self, path: str | Path):
        """保存图片到文件

        参数:
            path: 保存路径
        """
        await self.canvas.save(path)


BuildMat = BuildRankMat
