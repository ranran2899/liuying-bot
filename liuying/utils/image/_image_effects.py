"""图片特效模块

提供装饰性边框、阴影、渐变背景、毛玻璃、文字描边/阴影、艺术滤镜等特效
基于 PIL ImageFilter 与 ImageDraw 实现，所有方法均为静态异步方法

约定
----

所有特效方法统一返回 ``BuildImage`` 对象：

- ``add_border``/``add_shadow`` 返回新建的 ``BuildImage``，不修改入参
- ``glass_blur``/``apply_art_filter`` 因是同尺寸变换，原地修改入参
- ``gradient_background`` 创建全新的 ``BuildImage``
"""

from itertools import product

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from PIL.ImageFont import FreeTypeFont

from liuying.utils.enum import ArtFilter, GradientDirection
from liuying.utils.image._build_image import BuildImage, _to_rgb


class ImageEffects:
    """图片特效工具类

    提供装饰性与艺术化图片处理能力，增强视觉表现
    """

    @staticmethod
    async def add_border(
        image: BuildImage,
        width: int = 2,
        color: str | tuple[int, int, int] = "#C2CEFE",
        radius: int = 0,
    ) -> BuildImage:
        """添加装饰性边框（返回新对象）

        参数:
            image: 目标图片
            width: 边框宽度
            color: 边框颜色
            radius: 圆角半径（0 表示直角）

        返回:
            BuildImage: 添加边框后的新图片
        """
        rgb_color = _to_rgb(color)
        new_w = image.width + width * 2
        new_h = image.height + width * 2
        canvas = BuildImage(new_w, new_h, color=rgb_color)

        if radius > 0:
            await canvas.circle_corner(radius)

        await canvas.paste(image, (width, width))
        return canvas

    @staticmethod
    async def add_shadow(
        image: BuildImage,
        offset: tuple[int, int] = (4, 4),
        blur: int = 10,
        opacity: float = 0.5,
        color: str | tuple[int, int, int] = (0, 0, 0),
        padding: int | None = None,
    ) -> BuildImage:
        """添加投影阴影（返回新对象）

        支持任意方向偏移（包括负偏移），画布尺寸容纳完整阴影

        参数:
            image: 目标图片
            offset: 阴影偏移 (x, y)，可为负值
            blur: 模糊半径
            opacity: 不透明度 0-1
            color: 阴影颜色
            padding: 阴影画布外边距（None 时自动计算）

        返回:
            BuildImage: 带阴影的新图片
        """
        if padding is None:
            padding = blur * 2 + max(abs(offset[0]), abs(offset[1]))

        rgb_color = _to_rgb(color)
        alpha_val = int(255 * max(0.0, min(1.0, opacity)))

        img_rgba = image.mark_img.convert("RGBA")
        abs_dx, abs_dy = abs(offset[0]), abs(offset[1])

        # 画布需容纳原图 + 两侧偏移空间 + 两侧 padding
        canvas_w = image.width + abs_dx * 2 + padding * 2
        canvas_h = image.height + abs_dy * 2 + padding * 2

        # 阴影矩形与原图位置（偏移方向一致）
        off_x = padding + abs_dx + offset[0]
        off_y = padding + abs_dy + offset[1]

        shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rectangle(
            [off_x, off_y, off_x + image.width, off_y + image.height],
            fill=(*rgb_color, alpha_val),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
        shadow.alpha_composite(img_rgba, (off_x, off_y))

        new_image = BuildImage(canvas_w, canvas_h, color=(0, 0, 0, 0), mode="RGBA")
        new_image.mark_img = shadow
        new_image.draw = ImageDraw.Draw(shadow)
        return new_image

    @staticmethod
    async def gradient_background(
        size: tuple[int, int],
        start_color: str | tuple[int, int, int],
        end_color: str | tuple[int, int, int],
        direction: GradientDirection | str = GradientDirection.VERTICAL,
    ) -> BuildImage:
        """生成渐变背景

        参数:
            size: 画布尺寸 (width, height)
            start_color: 起始颜色
            end_color: 结束颜色
            direction: 渐变方向

        返回:
            BuildImage: 渐变背景图片
        """
        w, h = size
        start_rgb = _to_rgb(start_color)
        end_rgb = _to_rgb(end_color)
        direction_val = (
            direction
            if isinstance(direction, GradientDirection)
            else GradientDirection(direction)
        )

        match direction_val:
            case GradientDirection.HORIZONTAL:
                # 水平渐变：1 像素高的横向渐变拉伸到全画布
                gradient = Image.new("L", (w, 1))
                span = max(w - 1, 1)
                gradient.putdata([x * 255 // span for x in range(w)])
                gradient = gradient.resize((w, h))
            case GradientDirection.VERTICAL:
                gradient = Image.new("L", (1, h))
                span = max(h - 1, 1)
                gradient.putdata([y * 255 // span for y in range(h)])
                gradient = gradient.resize((w, h))
            case GradientDirection.DIAGONAL:
                gradient = Image.new("L", (w, h))
                max_pos = max(w + h - 2, 1)
                # 按行预计算 x 分量，避免逐像素重复运算
                xs = list(range(w))
                gradient.putdata(
                    [(x + y) * 255 // max_pos for y in range(h) for x in xs]
                )
            case GradientDirection.RADIAL:
                gradient = Image.new("L", (w, h))
                cx, cy = w // 2, h // 2
                max_dist = max((cx**2 + cy**2) ** 0.5, 1.0)
                # 预计算横向平方距离，纵向仅计算一次
                dx2 = [(x - cx) ** 2 for x in range(w)]
                gradient.putdata(
                    [
                        min(int(((d + dy2) ** 0.5) / max_dist * 255), 255)
                        for dy2 in ((y - cy) ** 2 for y in range(h))
                        for d in dx2
                    ]
                )

        result = Image.composite(
            Image.new("RGB", (w, h), end_rgb),
            Image.new("RGB", (w, h), start_rgb),
            gradient,
        )
        new_image = BuildImage(w, h, mode="RGB")
        new_image.mark_img = result.convert("RGBA")
        new_image.draw = ImageDraw.Draw(new_image.mark_img)
        return new_image

    @staticmethod
    async def glass_blur(image: BuildImage, radius: int = 8) -> BuildImage:
        """毛玻璃模糊背景效果（原地修改）

        将原图模糊后铺满画布，再叠加原图居中显示

        参数:
            image: 目标图片
            radius: 模糊半径

        返回:
            BuildImage: 毛玻璃效果图片（与入参同一对象）
        """
        src = image.mark_img.convert("RGBA")
        blurred = src.filter(ImageFilter.GaussianBlur(radius))
        canvas = Image.new("RGBA", src.size, (0, 0, 0, 0))
        canvas.alpha_composite(blurred, (0, 0))
        canvas.alpha_composite(src, (0, 0))
        image.mark_img = canvas
        image.draw = ImageDraw.Draw(canvas)
        return image

    @staticmethod
    def text_outline(
        draw: ImageDraw.ImageDraw,
        pos: tuple[float, float],
        text: str,
        font: FreeTypeFont,
        fill: str | tuple[int, int, int] = (255, 255, 255),
        outline: str | tuple[int, int, int] = (0, 0, 0),
        width: int = 2,
    ) -> None:
        """绘制带描边的文字

        参数:
            draw: ImageDraw 对象
            pos: 文字位置
            text: 文字内容
            font: 字体
            fill: 文字颜色
            outline: 描边颜色
            width: 描边宽度
        """
        x, y = pos
        outline_rgb = _to_rgb(outline)
        for dx, dy in product(range(-width, width + 1), repeat=2):
            if dx or dy:
                draw.text((x + dx, y + dy), text, fill=outline_rgb, font=font)
        draw.text(pos, text, fill=fill, font=font)

    @staticmethod
    def text_shadow(
        draw: ImageDraw.ImageDraw,
        pos: tuple[float, float],
        text: str,
        font: FreeTypeFont,
        fill: str | tuple[int, int, int] = (255, 255, 255),
        shadow: str | tuple[int, int, int] = (0, 0, 0),
        offset: tuple[int, int] = (2, 2),
    ) -> None:
        """绘制带阴影的文字

        参数:
            draw: ImageDraw 对象
            pos: 文字位置
            text: 文字内容
            font: 字体
            fill: 文字颜色
            shadow: 阴影颜色
            offset: 阴影偏移
        """
        x, y = pos
        shadow_rgb = _to_rgb(shadow)
        draw.text((x + offset[0], y + offset[1]), text, fill=shadow_rgb, font=font)
        draw.text(pos, text, fill=fill, font=font)

    @staticmethod
    async def apply_art_filter(
        image: BuildImage, filter_type: ArtFilter | str
    ) -> BuildImage:
        """应用艺术滤镜（原地修改）

        参数:
            image: 目标图片
            filter_type: 艺术滤镜类型

        返回:
            BuildImage: 处理后的图片（与入参同一对象）
        """
        filter_val = (
            filter_type
            if isinstance(filter_type, ArtFilter)
            else ArtFilter(filter_type)
        )
        src = image.mark_img.convert("RGB")

        match filter_val:
            case ArtFilter.VINTAGE:
                result = _apply_vintage(src)
            case ArtFilter.OIL_PAINTING:
                result = _apply_oil_painting(src)
            case ArtFilter.CARTOON:
                result = _apply_cartoon(src)
            case ArtFilter.SKETCH:
                result = _apply_sketch(src)
            case _:
                result = src

        image.mark_img = result.convert("RGBA")
        image.draw = ImageDraw.Draw(image.mark_img)
        return image


def _apply_vintage(img: Image.Image) -> Image.Image:
    """复古滤镜（向量化实现）

    参数:
        img: 原图

    返回:
        Image.Image: 处理后的图片
    """
    img = ImageEnhance.Color(img).enhance(0.6)
    img = ImageEnhance.Contrast(img).enhance(1.2)

    # 向量化调整通道，避免逐像素循环
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v * 1.1 + 20)))
    g = g.point(lambda v: min(255, int(v * 0.95)))
    b = b.point(lambda v: min(255, int(v * 0.85)))
    return Image.merge("RGB", (r, g, b))


def _apply_oil_painting(img: Image.Image) -> Image.Image:
    """油画效果

    参数:
        img: 原图

    返回:
        Image.Image: 处理后的图片
    """
    img = img.filter(ImageFilter.MedianFilter(size=3))
    img = img.filter(ImageFilter.SHARPEN)
    return img


def _apply_cartoon(img: Image.Image) -> Image.Image:
    """卡通化效果

    参数:
        img: 原图

    返回:
        Image.Image: 处理后的图片
    """
    edges = img.filter(ImageFilter.FIND_EDGES).convert("L")
    edges = edges.point(lambda p: 255 if p < 50 else 0)
    cartoon = img.convert("RGBA")
    cartoon.paste((0, 0, 0, 0), mask=edges)
    return cartoon


def _apply_sketch(img: Image.Image) -> Image.Image:
    """素描效果

    参数:
        img: 原图

    返回:
        Image.Image: 处理后的图片
    """
    gray = img.convert("L")
    inverted = Image.eval(gray, lambda x: 255 - x)
    blurred = inverted.filter(ImageFilter.GaussianBlur(15))
    result = Image.blend(gray, blurred, 0.5)
    return result.point(lambda p: 255 if p > 200 else p)
