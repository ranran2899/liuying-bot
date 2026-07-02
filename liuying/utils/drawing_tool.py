from io import BytesIO
from math import cos, pi, sin
from pathlib import Path
from typing import Self

import numpy as np
from PIL import Image, ImageFilter, ImageFont

from .image._build_image import BuildImage


class DrawingTool:
    """高级绘图工具类，为开发者提供更便捷的绘图接口和常用图形模板"""

    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        background_color: str | tuple[int, int, int] = "white",
    ):
        """初始化绘图工具

        参数:
            width: 画布宽度
            height: 画布高度
            background_color: 背景颜色
        """
        self.canvas = BuildImage(width=width, height=height, color=background_color)
        self.width = width
        self.height = height
        self.draw = self.canvas.draw

    @classmethod
    def from_image(cls, image_path: str | Path | bytes) -> Self:
        """从现有图片创建绘图工具

        参数:
            image_path: 图片路径或字节数据

        返回:
            DrawingTool: 绘图工具实例
        """
        if isinstance(image_path, bytes):
            img = Image.open(BytesIO(image_path))
        else:
            img = Image.open(image_path)
        tool = cls(width=img.width, height=img.height)
        tool.canvas.paste(BuildImage.open(image_path))
        return tool

    def draw_text_box(
        self,
        text: str,
        pos: tuple[int, int],
        box_width: int,
        box_height: int,
        font_size: int = 16,
        text_color: str | tuple[int, int, int] = "black",
        bg_color: str | tuple[int, int, int, int] | None = None,
        border_color: str | tuple[int, int, int] | None = None,
        border_width: int = 1,
        align: str = "center",
        vertical_align: str = "middle",
        padding: int = 10,
    ) -> Self:
        """绘制文本框

        参数:
            text: 文本内容
            pos: 文本框左上角位置
            box_width: 文本框宽度
            box_height: 文本框高度
            font_size: 字体大小
            text_color: 文本颜色
            bg_color: 背景颜色
            border_color: 边框颜色
            border_width: 边框宽度
            align: 文本水平对齐方式 (left, center, right)
            vertical_align: 文本垂直对齐方式 (top, middle, bottom)
            padding: 内边距

        返回:
            DrawingTool: 自身实例，支持链式调用
        """
        if bg_color is not None:
            self.canvas.rectangle(
                (pos[0], pos[1], pos[0] + box_width, pos[1] + box_height),
                fill=bg_color,
            )

        if border_color is not None:
            self.canvas.rectangle(
                (pos[0], pos[1], pos[0] + box_width, pos[1] + box_height),
                outline=border_color,
                width=border_width,
            )

        available_width = box_width - padding * 2
        font = BuildImage.load_font(font_size=font_size)

        lines: list[str] = []
        current_line = ""
        for word in text.split(" "):
            test_line = current_line + (" " if current_line else "") + word
            if BuildImage.get_text_size(test_line, font)[0] <= available_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                if BuildImage.get_text_size(word, font)[0] > available_width:
                    temp_line = ""
                    for char in word:
                        if (
                            BuildImage.get_text_size(temp_line + char, font)[0]
                            > available_width
                        ):
                            lines.append(temp_line)
                            temp_line = char
                        else:
                            temp_line += char
                    lines.append(temp_line)
                else:
                    current_line = word

        if current_line:
            lines.append(current_line)

        line_height = BuildImage.get_text_size("Tg", font)[1]
        total_text_height = line_height * len(lines)

        match vertical_align:
            case "top":
                y = pos[1] + padding
            case "middle":
                y = pos[1] + (box_height - total_text_height) // 2
            case _:
                y = pos[1] + box_height - padding - total_text_height

        for line in lines:
            text_width, _ = BuildImage.get_text_size(line, font)
            match align:
                case "left":
                    x = pos[0] + padding
                case "center":
                    x = pos[0] + (box_width - text_width) // 2
                case _:
                    x = pos[0] + box_width - padding - text_width
            self.canvas.text((x, y), line, fill=text_color, font=font)
            y += line_height

        return self

    def draw_chart(
        self,
        data: list[float],
        pos: tuple[int, int],
        width: int,
        height: int,
        chart_type: str = "bar",
        colors: list[str | tuple[int, int, int]] | None = None,
        labels: list[str] | None = None,
        legend: bool = True,
        title: str | None = None,
    ) -> Self:
        """绘制简单图表

        参数:
            data: 数据列表
            pos: 图表左上角位置
            width: 图表宽度
            height: 图表高度
            chart_type: 图表类型 (bar, line, pie)
            colors: 自定义颜色列表
            labels: 数据标签
            legend: 是否显示图例
            title: 图表标题

        返回:
            DrawingTool: 自身实例，支持链式调用
        """
        default_colors = [
            (255, 99, 132), (54, 162, 235), (255, 206, 86),
            (75, 192, 192), (153, 102, 255), (255, 159, 64),
        ]
        if colors is None:
            colors = [default_colors[i % len(default_colors)] for i in range(len(data))]

        if title:
            title_font = BuildImage.load_font(font_size=18)
            self.canvas.text(
                (pos[0] + width // 2, pos[1] - 30),
                title,
                fill="black",
                font=title_font,
                center_type="center",
            )

        match chart_type:
            case "bar":
                self._draw_bar_chart(data, pos, width, height, colors)
            case "line":
                self._draw_line_chart(data, pos, width, height, colors)
            case "pie":
                self._draw_pie_chart(data, pos, width, height, colors)

        if legend and labels:
            self._draw_legend(labels, colors, pos, width)

        return self

    def _draw_bar_chart(
        self,
        data: list[float],
        pos: tuple[int, int],
        width: int,
        height: int,
        colors: list[str | tuple[int, int, int]],
    ):
        """绘制柱状图"""
        bar_width = width / len(data) * 0.7
        gap = width / len(data) * 0.3 / 2
        max_value = max(data) if data else 1

        for i, value in enumerate(data):
            bar_height = (value / max_value) * height
            bar_x = pos[0] + i * (bar_width + gap * 2) + gap
            bar_y = pos[1] + height - bar_height
            self.canvas.rectangle(
                (bar_x, bar_y, bar_x + bar_width, pos[1] + height),
                fill=colors[i],
            )

    def _draw_line_chart(
        self,
        data: list[float],
        pos: tuple[int, int],
        width: int,
        height: int,
        colors: list[str | tuple[int, int, int]],
    ):
        """绘制折线图"""
        if len(data) < 2:
            return

        max_value = max(data) if data else 1

        self.canvas.line(
            (pos[0], pos[1], pos[0], pos[1] + height), fill="black", width=2
        )
        self.canvas.line(
            (pos[0], pos[1] + height, pos[0] + width, pos[1] + height),
            fill="black",
            width=2,
        )

        points: list[tuple[float, float]] = []
        for i, value in enumerate(data):
            x = pos[0] + (i / (len(data) - 1)) * width
            y = pos[1] + height - (value / max_value) * height
            points.append((x, y))
            self.canvas.ellipse(
                (x - 3, y - 3, x + 3, y + 3), fill=colors[i % len(colors)]
            )

        for i in range(len(points) - 1):
            self.canvas.line(
                (*points[i], *points[i + 1]),
                fill=colors[i % len(colors)],
                width=2,
            )

    def _draw_pie_chart(
        self,
        data: list[float],
        pos: tuple[int, int],
        width: int,
        height: int,
        colors: list[str | tuple[int, int, int]],
    ):
        """绘制饼图"""
        total = sum(data)
        if total == 0:
            return

        center_x = pos[0] + width // 2
        center_y = pos[1] + height // 2
        radius = min(width, height) // 2 - 10

        current_angle = 0.0
        for i, value in enumerate(data):
            angle = (value / total) * 360
            self._draw_pie_slice(
                center_x, center_y, radius,
                current_angle, current_angle + angle,
                colors[i % len(colors)],
            )
            current_angle += angle

    def _draw_legend(
        self,
        labels: list[str],
        colors: list[str | tuple[int, int, int]],
        pos: tuple[int, int],
        width: int,
    ):
        """绘制图例"""
        legend_x = pos[0] + width + 10
        legend_y = pos[1]
        legend_item_height = 20
        font = BuildImage.load_font(font_size=12)

        for i, label in enumerate(labels):
            self.canvas.rectangle(
                (legend_x, legend_y + i * legend_item_height,
                 legend_x + 15, legend_y + i * legend_item_height + 15),
                fill=colors[i % len(colors)],
            )
            self.canvas.text(
                (legend_x + 20, legend_y + i * legend_item_height + 2),
                label,
                fill="black",
                font=font,
            )

    def _draw_pie_slice(
        self,
        center_x: int,
        center_y: int,
        radius: int,
        start_angle: float,
        end_angle: float,
        color: str | tuple[int, int, int],
    ) -> None:
        """绘制饼图的一个扇区

        参数:
            center_x: 中心点x坐标
            center_y: 中心点y坐标
            radius: 半径
            start_angle: 起始角度
            end_angle: 结束角度
            color: 填充颜色
        """
        start_rad = (start_angle - 90) * pi / 180
        end_rad = (end_angle - 90) * pi / 180
        points: list[tuple[float, float]] = [(center_x, center_y)]

        num_points = 30
        for i in range(num_points + 1):
            angle = start_rad + (end_rad - start_rad) * i / num_points
            points.append((
                center_x + radius * cos(angle),
                center_y + radius * sin(angle),
            ))

        points.append((center_x, center_y))
        self.canvas.polygon(points, fill=color)

    def draw_gradient_background(
        self,
        start_color: str | tuple[int, int, int],
        end_color: str | tuple[int, int, int],
        direction: str = "vertical",
    ) -> Self:
        """绘制渐变背景

        参数:
            start_color: 起始颜色
            end_color: 结束颜色
            direction: 渐变方向 (vertical, horizontal, diagonal)

        返回:
            DrawingTool: 自身实例，支持链式调用
        """
        w, h = self.width, self.height
        gradient = np.zeros((h, w, 3), dtype=np.uint8)

        if isinstance(start_color, str):
            start_color = self._hex_to_rgb(start_color)
        if isinstance(end_color, str):
            end_color = self._hex_to_rgb(end_color)

        match direction:
            case "vertical":
                ratios_y = np.linspace(0, 1, h).reshape(h, 1)
                ratios = np.broadcast_to(ratios_y, (h, w))
            case "horizontal":
                ratios_x = np.linspace(0, 1, w).reshape(1, w)
                ratios = np.broadcast_to(ratios_x, (h, w))
            case _:
                ratios = np.fromfunction(
                    lambda y, x: (x + y) / (w + h - 2), (h, w), dtype=float
                )

        sc = np.array(start_color, dtype=np.float64)
        ec = np.array(end_color, dtype=np.float64)
        gradient = (
            sc * (1 - ratios[..., np.newaxis]) + ec * ratios[..., np.newaxis]
        ).astype(np.uint8)

        gradient_img = Image.fromarray(gradient)
        gradient_build_img = BuildImage(
            width=w, height=h, background=gradient_img.tobytes()
        )
        self.canvas.paste(gradient_build_img)

        return self

    def draw_sticker(
        self,
        image_path: str | Path | bytes,
        pos: tuple[int, int],
        size: tuple[int, int] | None = None,
        rotate: float = 0,
        opacity: float = 1.0,
        rounded: bool = False,
        radius: int = 20,
    ) -> Self:
        """绘制贴纸效果的图片

        参数:
            image_path: 图片路径或字节数据
            pos: 贴纸位置
            size: 贴纸大小 (width, height)
            rotate: 旋转角度
            opacity: 透明度 (0.0-1.0)
            rounded: 是否为圆角
            radius: 圆角半径

        返回:
            DrawingTool: 自身实例，支持链式调用
        """
        sticker = BuildImage.open(image_path)

        if size:
            sticker.resize(width=size[0], height=size[1])
        if opacity < 1.0:
            sticker.transparent(alpha_ratio=opacity)
        if rounded:
            sticker.circle_corner(radius=radius)
        if rotate != 0:
            sticker.rotate(rotate, expand=True)

        self.canvas.paste(sticker, pos)
        return self

    def draw_avatar_frame(
        self,
        avatar_path: str | Path | bytes,
        pos: tuple[int, int],
        size: int,
        frame_type: str = "circle",
        border_width: int = 5,
        border_color: str | tuple[int, int, int] = "#FFD700",
        shadow: bool = True,
    ) -> Self:
        """绘制带边框的头像

        参数:
            avatar_path: 头像图片路径或字节数据
            pos: 头像位置（中心点）
            size: 头像大小
            frame_type: 边框类型
            border_width: 边框宽度
            border_color: 边框颜色
            shadow: 是否添加阴影

        返回:
            DrawingTool: 自身实例，支持链式调用
        """
        avatar = BuildImage.open(avatar_path)
        avatar.resize(width=size - border_width * 2, height=size - border_width * 2)

        frame_pos = (pos[0] - size // 2, pos[1] - size // 2)

        if shadow:
            shadow_layer = BuildImage(
                width=size + 10, height=size + 10, color=(0, 0, 0, 0)
            )
            shadow_pos = (frame_pos[0] - 5, frame_pos[1] - 5)
            if frame_type == "circle":
                shadow_layer.ellipse((5, 5, size + 5, size + 5), fill=(0, 0, 0, 80))
            else:
                shadow_layer.rectangle((5, 5, size + 5, size + 5), fill=(0, 0, 0, 80))
                if frame_type == "rounded_square":
                    shadow_layer.circle_corner(radius=30)
            shadow_layer.mark_img = shadow_layer.mark_img.filter(
                ImageFilter.GaussianBlur(radius=5)
            )
            self.canvas.paste(shadow_layer, shadow_pos)

        frame_layer = BuildImage(width=size, height=size, color=(0, 0, 0, 0))

        match frame_type:
            case "circle":
                frame_layer.ellipse((0, 0, size, size), fill=border_color)
                avatar.circle()
            case "rounded_square":
                frame_layer.rectangle((0, 0, size, size), fill=border_color)
                frame_layer.circle_corner(radius=30)
                avatar.circle_corner(radius=30 - border_width)
            case _:
                frame_layer.rectangle((0, 0, size, size), fill=border_color)

        self.canvas.paste(frame_layer, frame_pos)
        self.canvas.paste(
            avatar, (frame_pos[0] + border_width, frame_pos[1] + border_width)
        )

        return self

    def save(self, path: str | Path) -> None:
        """保存图像到文件

        参数:
            path: 保存路径
        """
        self.canvas.save(path)

    def get_bytes(self) -> bytes:
        """获取图像字节数据

        返回:
            bytes: 图像字节数据
        """
        return self.canvas.pic2bytes()

    def get_base64(self) -> str:
        """获取图像base64编码

        返回:
            str: base64编码的图像
        """
        return self.canvas.pic2bs4()

    def show(self) -> None:
        """显示图像"""
        self.canvas.show()

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """将十六进制颜色转换为RGB

        参数:
            hex_color: 十六进制颜色字符串

        返回:
            tuple[int, int, int]: RGB颜色值
        """
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def create_text_image(
    text: str,
    font_size: int = 20,
    text_color: str | tuple[int, int, int] = "black",
    background_color: str | tuple[int, int, int] = "white",
    padding: int = 20,
    align: str = "center",
    font_path: str | None = None,
    shadow: bool = False,
    shadow_color: str | tuple[int, int, int] = "#888888",
    shadow_offset: tuple[int, int] = (2, 2),
    border: bool = False,
    border_color: str | tuple[int, int, int] = "black",
    border_width: int = 1,
) -> bytes:
    """创建文本图像，支持多种样式

    参数:
        text: 文本内容
        font_size: 字体大小
        text_color: 文本颜色
        background_color: 背景颜色
        padding: 内边距
        align: 文本对齐方式 (left, center, right)
        font_path: 自定义字体路径
        shadow: 是否添加阴影
        shadow_color: 阴影颜色
        shadow_offset: 阴影偏移量
        border: 是否添加边框
        border_color: 边框颜色
        border_width: 边框宽度

    返回:
        bytes: 图像字节数据
    """
    font = (
        ImageFont.truetype(font_path, font_size)
        if font_path
        else BuildImage.load_font(font_size=font_size)
    )
    text_width, text_height = BuildImage.get_text_size(text, font)

    tool = DrawingTool(
        width=text_width + padding * 2,
        height=text_height + padding * 2,
        background_color=background_color,
    )

    match align:
        case "left":
            x = padding
        case "center":
            x = (tool.width - text_width) // 2
        case _:
            x = tool.width - padding - text_width
    y = (tool.height - text_height) // 2

    if shadow:
        tool.canvas.text(
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            fill=shadow_color,
            font=font,
        )

    tool.canvas.text((x, y), text, fill=text_color, font=font)

    if border:
        tool.canvas.rectangle(
            (0, 0, tool.width - 1, tool.height - 1),
            outline=border_color,
            width=border_width,
        )

    return tool.get_bytes()


def create_combined_image(
    images: list[str | Path | bytes],
    layout: str = "horizontal",
    spacing: int = 20,
    background_color: str | tuple[int, int, int] = "white",
    grid_cols: int = 2,
) -> bytes:
    """创建组合图像

    参数:
        images: 图像路径或字节数据列表
        layout: 布局方式 (horizontal, vertical, grid)
        spacing: 图像间距
        background_color: 背景颜色
        grid_cols: 网格布局的列数

    返回:
        bytes: 图像字节数据
    """
    build_images = [BuildImage.open(img) for img in images]

    match layout:
        case "horizontal":
            total_width = (
                sum(img.width for img in build_images)
                + spacing * (len(build_images) - 1)
            )
            max_height = max(img.height for img in build_images)
            tool = DrawingTool(
                width=total_width,
                height=max_height,
                background_color=background_color,
            )
            current_x = 0
            for img in build_images:
                tool.canvas.paste(img, (current_x, (max_height - img.height) // 2))
                current_x += img.width + spacing
        case "vertical":
            max_width = max(img.width for img in build_images)
            total_height = (
                sum(img.height for img in build_images)
                + spacing * (len(build_images) - 1)
            )
            tool = DrawingTool(
                width=max_width,
                height=total_height,
                background_color=background_color,
            )
            current_y = 0
            for img in build_images:
                tool.canvas.paste(img, ((max_width - img.width) // 2, current_y))
                current_y += img.height + spacing
        case _:
            max_width = max(img.width for img in build_images)
            max_height = max(img.height for img in build_images)
            rows = (len(build_images) + grid_cols - 1) // grid_cols
            total_width = max_width * grid_cols + spacing * (grid_cols - 1)
            total_height = max_height * rows + spacing * (rows - 1)
            tool = DrawingTool(
                width=total_width,
                height=total_height,
                background_color=background_color,
            )
            for i, img in enumerate(build_images):
                x = (i % grid_cols) * (max_width + spacing)
                y = (i // grid_cols) * (max_height + spacing)
                tool.canvas.paste(img, (x, y))

    return tool.get_bytes()


__all__ = ["DrawingTool", "create_combined_image", "create_text_image"]
