"""图片构建工具模块

提供快捷生成图片与操作图片的 BuildImage 类
支持多种图片操作：贴图、文字、形状绘制、滤镜等
"""

import base64
import contextlib
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import TypeAlias, overload
import uuid

from nonebot.utils import run_sync
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.Image import Image as tImage
from PIL.Image import Resampling, Transpose
from PIL.ImageFont import FreeTypeFont

from liuying.configs.path_config import FONT_PATH
from liuying.utils.enum import CenterType, FilterType, ModeType

ColorAlias: TypeAlias = str | tuple[int, int, int] | tuple[int, int, int, int] | None


@cache
def _load_cached_font(font_path: str, font_size: int) -> FreeTypeFont:
    """缓存字体加载

    参数:
        font_path: 字体路径
        font_size: 字体大小

    返回:
        FreeTypeFont: 字体对象
    """
    return ImageFont.truetype(font_path, font_size)


@cache
def _get_measure_draw() -> ImageDraw.ImageDraw:
    """获取用于测量文本尺寸的共享 ImageDraw 对象

    通过 @cache 实现单例，避免模块级可变状态

    返回:
        ImageDraw.ImageDraw: 共享的测量用 draw 对象
    """
    return ImageDraw.Draw(Image.new("RGB", (1, 1), (255, 255, 255)))


class BuildImage:
    """快捷生成图片与操作图片的工具类"""

    __slots__ = ("color", "draw", "font", "height", "mark_img", "uid", "width")

    def __init__(
        self,
        width: int = 0,
        height: int = 0,
        color: ColorAlias = (255, 255, 255),
        mode: ModeType | str = "RGBA",
        font: str | Path | FreeTypeFont = "HYWenHei-85W.ttf",
        font_size: int = 20,
        background: str | BytesIO | Path | bytes | None = None,
    ) -> None:
        self.uid = uuid.uuid4()
        self.width = width
        self.height = height
        self.color = color
        self.font = (
            font if isinstance(font, FreeTypeFont) else self.load_font(font, font_size)
        )
        mode_val = mode.value if isinstance(mode, ModeType) else mode
        match background:
            case bytes():
                self.mark_img = Image.open(BytesIO(background))
            case str() | Path() | BytesIO():
                self.mark_img = Image.open(background)
            case None if width and height:
                self.mark_img = Image.new(mode_val, (width, height), color)
            case None:
                raise ValueError("长度和宽度不能为空...")
            case _:
                self.mark_img = Image.open(background)

        if background and width and height:
            self.mark_img = self.mark_img.resize(
                (width, height), Resampling.LANCZOS
            )
        elif background:
            self.width = self.mark_img.width
            self.height = self.mark_img.height

        self.draw = ImageDraw.Draw(self.mark_img)

    @property
    def size(self) -> tuple[int, int]:
        return self.mark_img.size

    @classmethod
    def open(cls, path: str | Path | bytes) -> "BuildImage":
        """打开图片

        参数:
            path: 图片路径

        返回:
            BuildImage: BuildImage
        """
        return cls(background=path)

    @classmethod
    async def build_text_image(
        cls,
        text: str,
        font: str | FreeTypeFont | Path = "HYWenHei-85W.ttf",
        size: int = 10,
        font_color: str | tuple[int, int, int] = (0, 0, 0),
        color: ColorAlias = None,
        padding: int | tuple[int, int, int, int] | None = None,
    ) -> "BuildImage":
        """构建文本图片

        参数:
            text: 文本
            font: 字体路径
            size: 字体大小
            font_color: 字体颜色.
            color: 背景颜色
            padding: 外边距

        返回:
            BuildImage: Self
        """
        if not text.strip():
            return cls(1, 1)

        _font = (
            font
            if isinstance(font, FreeTypeFont)
            else cls.load_font(font, size)
            if isinstance(font, str | Path)
            else None
        )

        width, height = cls.get_text_size(text, _font)

        match padding:
            case int():
                width += padding * 2
                height += padding * 2
            case (int(top), int(left), int(bottom), int(right)):
                width += left + right
                height += top + bottom
            case None:
                pass

        mark_img = cls(width, height, color, font=_font)
        await mark_img.text(
            (0, 0), text, fill=font_color, font=_font, center_type="center"
        )
        return mark_img

    @classmethod
    async def auto_paste(
        cls,
        img_list: list["BuildImage | tImage"],
        row: int,
        space: int = 10,
        padding: int = 50,
        color: ColorAlias = (255, 255, 255),
        background: str | BytesIO | Path | None = None,
    ) -> "BuildImage":
        """自动贴图，按行排列

        参数:
            img_list: 图片列表
            row: 一行图片的数量
            space: 图片之间的间距.
            padding: 外边距.
            color: 图片背景颜色.
            background: 图片背景图片.

        返回:
            BuildImage: Self
        """
        if not img_list:
            raise ValueError("贴图类别为空...")

        max_w = max(img.size[0] for img in img_list)
        max_h = max(img.size[1] for img in img_list)
        row_count = (len(img_list) + row - 1) // row

        bg_width = (
            sum(img.width for img in img_list) + space * (row - 1) + padding * 2
            if row_count == 1
            else max_w * row + space * (row - 1) + padding * 2
        )
        bg_height = max_h * row_count + space * (row_count - 1) + padding * 2

        background_image = cls(
            bg_width, bg_height, color=color, background=background
        )
        cur_x = cur_y = padding
        col_count = 0

        for i, img in enumerate(img_list):
            await background_image.paste(img, (cur_x, cur_y))
            cur_x += space + img.width
            col_count += 1
            next_w = img_list[i + 1].width if i < len(img_list) - 1 else 0

            if col_count == row or cur_x + padding + next_w > bg_width:
                cur_y += space + img.height
                cur_x = padding
                col_count = 0

        return background_image

    @classmethod
    def load_font(
        cls, font: str | Path = "HYWenHei-85W.ttf", font_size: int = 10
    ) -> FreeTypeFont:
        """加载字体（带缓存）

        参数:
            font: 字体名称
            font_size: 字体大小

        返回:
            FreeTypeFont: 字体
        """
        path = FONT_PATH / font if isinstance(font, str) else font
        return _load_cached_font(str(path), font_size)

    @overload
    @classmethod
    def get_text_size(
        cls, text: str, font: FreeTypeFont | None = None
    ) -> tuple[int, int]: ...

    @overload
    @classmethod
    def get_text_size(
        cls, text: str, font: str | None = None, font_size: int = 10
    ) -> tuple[int, int]: ...

    @classmethod
    def get_text_size(
        cls,
        text: str,
        font: str | FreeTypeFont | None = "HYWenHei-85W.ttf",
        font_size: int = 10,
    ) -> tuple[int, int]:
        """获取该字体下文本需要的长宽

        参数:
            text: 文本内容
            font: 字体名称或FreeTypeFont
            font_size: 字体大小

        返回:
            tuple[int, int]: 长宽
        """
        _font = cls.load_font(font, font_size) if isinstance(font, str) else font
        text_box = _get_measure_draw().textbbox((0, 0), str(text), font=_font)
        return text_box[2] - text_box[0], text_box[3] - text_box[1] + 10

    def getsize(self, msg: str) -> tuple[int, int]:
        """获取文字在该图片 font_size 下所需要的空间

        参数:
            msg: 文本

        返回:
            tuple[int, int]: 长宽
        """
        text_box = _get_measure_draw().textbbox((0, 0), str(msg), font=self.font)
        return text_box[2] - text_box[0], text_box[3] - text_box[1] + 10

    def _center_xy(
        self,
        pos: tuple[int, int],
        width: int,
        height: int,
        center_type: CenterType | str | None,
    ) -> tuple[int, int]:
        """根据居中类型定位xy

        参数:
            pos: 定位
            width: 宽度
            height: 高度
            center_type: 居中类型

        返回:
            tuple[int, int]: 定位
        """
        if not (self.width and self.height):
            return width, height

        match CenterType(center_type) if center_type else None:
            case CenterType.CENTER:
                return int((self.width - width) / 2), int(
                    (self.height - height) / 2
                )
            case CenterType.WIDTH:
                return int((self.width - width) / 2), pos[1]
            case CenterType.HEIGHT:
                return pos[0], int((self.height - height) / 2)
            case _:
                return width, height

    @run_sync
    def paste(
        self,
        image: "BuildImage | tImage",
        pos: tuple[int, int] = (0, 0),
        center_type: CenterType | str | None = None,
    ) -> "BuildImage":
        """贴图

        参数:
            image: BuildImage 或 Image
            pos: 定位.
            center_type: 居中.

        返回:
            BuildImage: Self

        异常:
            ValueError: 居中类型错误
        """
        if center_type and center_type not in {
            CenterType.CENTER,
            CenterType.HEIGHT,
            CenterType.WIDTH,
        }:
            raise ValueError("center_type must be 'center', 'width' or 'height'")

        _image = image.mark_img if isinstance(image, BuildImage) else image

        if _image.width and _image.height and center_type:
            pos = self._center_xy(pos, _image.width, _image.height, center_type)

        with contextlib.suppress(ValueError):
            self.mark_img.paste(_image, pos, _image)
            return self

        self.mark_img.paste(_image, pos)
        return self

    @run_sync
    def point(
        self, pos: tuple[int, int], fill: tuple[int, int, int] | None = None
    ) -> "BuildImage":
        """绘制多个或单独的像素"""
        self.draw.point(pos, fill=fill)
        return self

    @run_sync
    def ellipse(
        self,
        pos: tuple[int, int, int, int],
        fill: tuple[int, int, int] | None = None,
        outline: tuple[int, int, int] | None = None,
        width: int = 1,
    ) -> "BuildImage":
        """绘制圆"""
        self.draw.ellipse(pos, fill, outline, width)
        return self

    @run_sync
    def text(
        self,
        pos: tuple[int, int],
        text: str,
        fill: str | tuple[int, int, int] = (0, 0, 0),
        center_type: CenterType | str | None = None,
        font: FreeTypeFont | str | Path | None = None,
        font_size: int = 10,
    ) -> "BuildImage":
        """在图片上添加文字

        参数:
            pos: 文字位置
            text: 文字内容
            fill: 文字颜色.
            center_type: 居中类型.
            font: 字体.
            font_size: 字体大小.

        返回:
            BuildImage: Self

        异常:
            ValueError: 居中类型错误
        """
        if center_type and center_type not in {
            CenterType.CENTER,
            CenterType.HEIGHT,
            CenterType.WIDTH,
        }:
            raise ValueError("center_type must be 'center', 'width' or 'height'")

        sentence = str(text).split("\n")
        max_length_text = max(sentence, key=len, default="")

        _font = (
            self.load_font(font, font_size)
            if font and not isinstance(font, FreeTypeFont)
            else font if isinstance(font, FreeTypeFont) else self.font
        )

        if center_type:
            ttf_w, ttf_h = self.getsize(max_length_text)
            pos = self._center_xy(pos, ttf_w, ttf_h, center_type)

        self.draw.text(pos, str(text), fill=fill, font=_font)
        return self

    @run_sync
    def wrap_text(
        self,
        pos: tuple[int, int],
        text: str,
        max_width: int,
        fill: str | tuple[int, int, int] = (0, 0, 0),
        font: FreeTypeFont | str | Path | None = None,
        font_size: int = 10,
        line_spacing: int = 5,
    ) -> "BuildImage":
        """自动换行绘制文本

        参数:
            pos: 起始位置
            text: 文本内容
            max_width: 最大宽度（像素）
            fill: 文字颜色.
            font: 字体.
            font_size: 字体大小.
            line_spacing: 行间距.

        返回:
            BuildImage: Self
        """
        _font = (
            self.load_font(font, font_size)
            if font and not isinstance(font, FreeTypeFont)
            else font if isinstance(font, FreeTypeFont) else self.font
        )
        cur_x, cur_y = pos
        for line in str(text).split("\n"):
            line_text = ""
            for char in line:
                test = line_text + char
                w, _ = self.getsize(test)
                if w > max_width and line_text:
                    self.draw.text((cur_x, cur_y), line_text, fill=fill, font=_font)
                    cur_y += self.getsize(line_text)[1] + line_spacing
                    line_text = char
                else:
                    line_text = test
            if line_text:
                self.draw.text((cur_x, cur_y), line_text, fill=fill, font=_font)
                cur_y += self.getsize(line_text)[1] + line_spacing
        return self

    @run_sync
    def save(self, path: str | Path):
        """保存图片

        参数:
            path: 图片路径
        """
        self.mark_img.save(path)

    def show(self):
        """显示图片"""
        self.mark_img.show()

    @run_sync
    def resize(self, ratio: float = 0, width: int = 0, height: int = 0) -> "BuildImage":
        """压缩图片

        参数:
            ratio: 压缩倍率.
            width: 压缩图片宽度至 width.
            height: 压缩图片高度至 height.

        返回:
            BuildImage: Self

        异常:
            ValueError: 缺少参数
        """
        if not width and not height and not ratio:
            raise ValueError("缺少参数...")

        if self.width and self.height:
            if not width and not height:
                width = int(self.width * ratio)
                height = int(self.height * ratio)
            self.mark_img = self.mark_img.resize(
                (width, height), Resampling.LANCZOS
            )
            self.width, self.height = self.mark_img.size
            self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def crop(self, box: tuple[int, int, int, int]) -> "BuildImage":
        """裁剪图片

        参数:
            box: 左上角坐标，右下角坐标 (left, upper, right, lower)

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.crop(box)
        self.width, self.height = self.mark_img.size
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def transparent(self, alpha_ratio: float = 1, n: int = 0) -> "BuildImage":
        """图片透明化（使用 alpha 通道批量操作，性能优化）

        参数:
            alpha_ratio: 透明化程度.
            n: 透明化大小内边距.

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.convert("RGBA")
        x, y = self.mark_img.size
        alpha_value = int(100 * alpha_ratio)

        if 0 < n < min(x, y) // 2:
            alpha = self.mark_img.split()[-1].copy()
            region = Image.new("L", (x - 2 * n, y - 2 * n), alpha_value)
            alpha.paste(region, (n, n))
            self.mark_img.putalpha(alpha)
        else:
            self.mark_img.putalpha(Image.new("L", (x, y), alpha_value))

        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def composite(
        self,
        image: "BuildImage | tImage",
        pos: tuple[int, int] = (0, 0),
        alpha: int = 255,
    ) -> "BuildImage":
        """合成图片（带透明度控制）

        参数:
            image: 要合成的图片
            pos: 合成位置.
            alpha: 合成透明度 0-255.

        返回:
            BuildImage: Self
        """
        _image = image.mark_img if isinstance(image, BuildImage) else image
        if alpha < 255:
            _image = _image.copy()
            _image.putalpha(
                Image.new("L", _image.size, max(0, min(255, alpha)))
            )
        self.mark_img = Image.alpha_composite(
            self.mark_img.convert("RGBA"), _image.convert("RGBA")
        )
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def add_watermark(
        self,
        text: str,
        font_size: int = 30,
        fill: str | tuple[int, int, int] = (128, 128, 128, 128),
        opacity: float = 0.3,
        spacing: int = 100,
    ) -> "BuildImage":
        """添加平铺水印

        参数:
            text: 水印文本
            font_size: 字体大小.
            fill: 水印颜色.
            opacity: 透明度 0-1.
            spacing: 水印间距.

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.convert("RGBA")
        watermark_layer = Image.new("RGBA", self.mark_img.size, (0, 0, 0, 0))
        w_draw = ImageDraw.Draw(watermark_layer)
        _font = self.load_font("HYWenHei-85W.ttf", font_size)
        text_w, text_h = self.getsize(text)
        alpha_val = int(255 * opacity)

        for y in range(0, self.height + text_h, spacing):
            for x in range(0, self.width + text_w, spacing):
                w_draw.text((x, y), text, fill=(*_to_rgb(fill), alpha_val), font=_font)

        self.mark_img = Image.alpha_composite(self.mark_img, watermark_layer)
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def get_dominant_colors(self, n: int = 3) -> list[tuple[int, int, int]]:
        """提取图片主色调

        参数:
            n: 返回颜色数量

        返回:
            list[tuple[int, int, int]]: 主色调列表
        """
        img = self.mark_img.convert("RGB").resize((100, 100), Resampling.LANCZOS)
        pixels = list(img.getdata())
        bucket: dict[tuple[int, int, int], int] = {}
        for r, g, b in pixels:
            key = (r // 32 * 32, g // 32 * 32, b // 32 * 32)
            bucket[key] = bucket.get(key, 0) + 1
        sorted_colors = sorted(bucket.items(), key=lambda x: x[1], reverse=True)
        return [color for color, _ in sorted_colors[:n]]

    def pic2bs4(self) -> str:
        """BuildImage 转 base64

        返回:
            str: base64
        """
        buf = BytesIO()
        self.mark_img.save(buf, format="PNG")
        return f"base64://{base64.b64encode(buf.getvalue()).decode()}"

    def pic2bytes(self) -> bytes:
        """获取bytes

        返回:
            bytes: bytes
        """
        buf = BytesIO()
        img_format = self.mark_img.format.upper() if self.mark_img.format else "PNG"

        if img_format == "GIF":
            self.mark_img.save(buf, format="GIF", save_all=True, loop=0)
        else:
            self.mark_img.save(buf, format="PNG")

        return buf.getvalue()

    @run_sync
    def convert(self, type_: ModeType | str) -> "BuildImage":
        """修改图片类型

        参数:
            type_: ModeType

        返回:
            BuildImage: Self
        """
        mode_val = type_.value if isinstance(type_, ModeType) else type_
        self.mark_img = self.mark_img.convert(mode_val)
        self.width, self.height = self.mark_img.size
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def rectangle(
        self,
        xy: tuple[int, int, int, int],
        fill: tuple[int, int, int] | None = None,
        outline: str | None = None,
        width: int = 1,
    ) -> "BuildImage":
        """画框"""
        self.draw.rectangle(xy, fill, outline, width)
        return self

    @run_sync
    def polygon(
        self,
        xy: list[tuple[int, int]],
        fill: tuple[int, int, int] = (0, 0, 0),
        outline: int = 1,
    ) -> "BuildImage":
        """画多边形"""
        self.draw.polygon(xy, fill, outline)
        return self

    @run_sync
    def line(
        self,
        xy: tuple[int, int, int, int],
        fill: tuple[int, int, int] | str = "#D8DEE4",
        width: int = 1,
    ) -> "BuildImage":
        """画线"""
        self.draw.line(xy, fill, width)
        return self

    @run_sync
    def circle(self) -> "BuildImage":
        """图像变圆

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.convert("RGBA")
        size = self.mark_img.size
        r2 = min(size[0], size[1])
        if size[0] != size[1]:
            self.mark_img = self.mark_img.resize((r2, r2), Resampling.LANCZOS)
            self.width, self.height = self.mark_img.size
        width = 1
        antialias = 4
        ellipse_box = [0, 0, r2 - 2, r2 - 2]
        mask = Image.new(
            size=[int(dim * antialias) for dim in self.mark_img.size],
            mode="L",
            color="black",
        )
        draw = ImageDraw.Draw(mask)
        for offset, fill in ((width / -2.0, "black"), (width / 2.0, "white")):
            left, top = ((value + offset) * antialias for value in ellipse_box[:2])
            right, bottom = ((value - offset) * antialias for value in ellipse_box[2:])
            draw.ellipse([left, top, right, bottom], fill=fill)
        mask = mask.resize(self.mark_img.size, Resampling.LANCZOS)
        with contextlib.suppress(ValueError):
            self.mark_img.putalpha(mask)
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def circle_corner(
        self,
        radii: int = 30,
        point_list: list[str] | None = None,
    ) -> "BuildImage":
        """矩形四角变圆

        参数:
            radii: 半径.
            point_list: 需要变化的角（lt/rt/lb/rb）.

        返回:
            BuildImage: Self
        """
        points = point_list or ["lt", "rt", "lb", "rb"]

        img = self.mark_img.convert("RGBA")
        alpha = img.split()[-1]
        circle = Image.new("L", (radii * 2, radii * 2), 0)
        draw = ImageDraw.Draw(circle)
        draw.ellipse((0, 0, radii * 2, radii * 2), fill=255)
        w, h = img.size

        corner_positions = {
            "lt": ((0, 0), (0, 0, radii, radii)),
            "rt": ((w - radii, 0), (radii, 0, radii * 2, radii)),
            "lb": ((0, h - radii), (0, radii, radii, radii * 2)),
            "rb": ((w - radii, h - radii), (radii, radii, radii * 2, radii * 2)),
        }

        for corner in points:
            if corner in corner_positions:
                pos, crop_box = corner_positions[corner]
                alpha.paste(circle.crop(crop_box), pos)

        img.putalpha(alpha)
        self.mark_img = img
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def rotate(self, angle: int, expand: bool = False) -> "BuildImage":
        """旋转图片

        参数:
            angle: 角度
            expand: 放大图片适应角度.

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.rotate(angle, expand=expand)
        self.width, self.height = self.mark_img.size
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def transpose(self, angle: Transpose) -> "BuildImage":
        """旋转图片(包括边框)

        参数:
            angle: 角度

        返回:
            BuildImage: Self
        """
        self.mark_img = self.mark_img.transpose(angle)
        self.width, self.height = self.mark_img.size
        self.draw = ImageDraw.Draw(self.mark_img)
        return self

    @run_sync
    def filter(self, filter_: FilterType | str, aud: int | None = None) -> "BuildImage":
        """图片滤镜

        参数:
            filter_: 滤镜类型
            aud: 强度参数.

        返回:
            BuildImage: Self
        """
        match FilterType(filter_) if isinstance(filter_, str) else filter_:
            case FilterType.GAUSSIAN_BLUR:
                self.mark_img = self.mark_img.filter(
                    ImageFilter.GaussianBlur(aud) if aud else ImageFilter.GaussianBlur()
                )
            case FilterType.EDGE_ENHANCE:
                self.mark_img = self.mark_img.filter(ImageFilter.EDGE_ENHANCE())
            case FilterType.SMOOTH:
                self.mark_img = self.mark_img.filter(ImageFilter.SMOOTH())

        if isinstance(self.mark_img, Image.Image):
            self.draw = ImageDraw.Draw(self.mark_img)
        return self


def _to_rgb(color: str | tuple[int, ...]) -> tuple[int, int, int]:
    """颜色转 RGB 元组

    参数:
        color: 颜色值（字符串或元组）

    返回:
        tuple[int, int, int]: RGB 元组
    """
    if isinstance(color, tuple):
        return color[:3]
    if color.startswith("#"):
        hex_color = color.lstrip("#")
        if len(hex_color) == 3:
            hex_color = "".join(c * 2 for c in hex_color)
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )
    return (0, 0, 0)
