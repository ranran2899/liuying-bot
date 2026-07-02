"""图片合成器模块

提供多图拼接、网格布局、对比并排、堆叠卡片等场景化合成能力
基于 BuildImage 类扩展，所有方法均为静态方法，便于链式调用
"""

from collections.abc import Sequence
from io import BytesIO

from PIL import Image

from liuying.utils.image._build_image import BuildImage, ColorAlias


class ImageComposer:
    """图片合成工具类

    提供横向、纵向、网格、对比、堆叠等多种合成方式
    所有方法均为静态异步方法，返回 BuildImage 对象便于后续操作
    """

    @staticmethod
    async def horizontal(
        images: Sequence[BuildImage | Image.Image],
        gap: int = 10,
        background: ColorAlias = (255, 255, 255),
        align: str = "center",
    ) -> BuildImage:
        """横向拼接图片

        参数:
            images: 图片序列（BuildImage 或 PIL Image）
            gap: 图片间距
            background: 背景颜色
            align: 垂直对齐方式（top/center/bottom）

        返回:
            BuildImage: 拼接后的图片

        异常:
            ValueError: 图片列表为空或对齐方式非法
        """
        if not images:
            raise ValueError("图片列表不能为空")
        if align not in {"top", "center", "bottom"}:
            raise ValueError("align 必须是 top/center/bottom")

        normalized = [_to_build_image(img) for img in images]
        total_width = sum(img.width for img in normalized) + gap * (len(normalized) - 1)
        max_height = max(img.height for img in normalized)

        canvas = BuildImage(total_width, max_height, color=background)
        cur_x = 0

        for img in normalized:
            match align:
                case "top":
                    y = 0
                case "bottom":
                    y = max_height - img.height
                case _:
                    y = (max_height - img.height) // 2
            await canvas.paste(img, (cur_x, y))
            cur_x += img.width + gap

        return canvas

    @staticmethod
    async def vertical(
        images: Sequence[BuildImage | Image.Image],
        gap: int = 10,
        background: ColorAlias = (255, 255, 255),
        align: str = "center",
    ) -> BuildImage:
        """纵向拼接图片

        参数:
            images: 图片序列
            gap: 图片间距
            background: 背景颜色
            align: 水平对齐方式（left/center/right）

        返回:
            BuildImage: 拼接后的图片

        异常:
            ValueError: 图片列表为空或对齐方式非法
        """
        if not images:
            raise ValueError("图片列表不能为空")
        if align not in {"left", "center", "right"}:
            raise ValueError("align 必须是 left/center/right")

        normalized = [_to_build_image(img) for img in images]
        total_height = (
            sum(img.height for img in normalized) + gap * (len(normalized) - 1)
        )
        max_width = max(img.width for img in normalized)

        canvas = BuildImage(max_width, total_height, color=background)
        cur_y = 0

        for img in normalized:
            match align:
                case "left":
                    x = 0
                case "right":
                    x = max_width - img.width
                case _:
                    x = (max_width - img.width) // 2
            await canvas.paste(img, (x, cur_y))
            cur_y += img.height + gap

        return canvas

    @staticmethod
    async def grid(
        images: Sequence[BuildImage | Image.Image],
        rows: int | None = None,
        cols: int | None = None,
        gap: int = 10,
        padding: int = 20,
        background: ColorAlias = (255, 255, 255),
    ) -> BuildImage:
        """网格布局合成

        参数:
            images: 图片序列
            rows: 行数（None 时自动计算）
            cols: 列数（None 时自动计算）
            gap: 图片间距
            padding: 外边距
            background: 背景颜色

        返回:
            BuildImage: 网格布局图片

        异常:
            ValueError: 图片列表为空或行列参数同时为空
        """
        if not images:
            raise ValueError("图片列表不能为空")
        if rows is None and cols is None:
            cols = _auto_columns(len(images))
            rows = (len(images) + cols - 1) // cols
        elif rows is None:
            rows = (len(images) + cols - 1) // cols
        elif cols is None:
            cols = (len(images) + rows - 1) // rows

        normalized = [_to_build_image(img) for img in images]
        max_w = max(img.width for img in normalized)
        max_h = max(img.height for img in normalized)

        canvas_w = max_w * cols + gap * (cols - 1) + padding * 2
        canvas_h = max_h * rows + gap * (rows - 1) + padding * 2

        canvas = BuildImage(canvas_w, canvas_h, color=background)

        for i, img in enumerate(normalized):
            col = i % cols
            row = i // cols
            x = padding + col * (max_w + gap) + (max_w - img.width) // 2
            y = padding + row * (max_h + gap) + (max_h - img.height) // 2
            await canvas.paste(img, (x, y))

        return canvas

    @staticmethod
    async def compare(
        before: BuildImage | Image.Image,
        after: BuildImage | Image.Image,
        labels: tuple[str, str] | None = None,
        gap: int = 20,
        label_height: int = 40,
        background: ColorAlias = (255, 255, 255),
    ) -> BuildImage:
        """前后对比并排展示

        参数:
            before: 前图
            after: 后图
            labels: 左右标签文本（如 ("Before", "After")）
            gap: 图片间距
            label_height: 标签区域高度（0 表示无标签）
            background: 背景颜色

        返回:
            BuildImage: 对比图
        """
        before_img = _to_build_image(before)
        after_img = _to_build_image(after)
        target_h = max(before_img.height, after_img.height)

        if before_img.height != target_h:
            ratio = target_h / before_img.height
            await before_img.resize(
                width=int(before_img.width * ratio),
                height=target_h,
            )
        if after_img.height != target_h:
            ratio = target_h / after_img.height
            await after_img.resize(
                width=int(after_img.width * ratio),
                height=target_h,
            )

        total_w = before_img.width + after_img.width + gap
        total_h = target_h + label_height if labels else target_h

        canvas = BuildImage(total_w, total_h, color=background)
        label_y = 0
        img_y = label_height if labels else 0

        if labels:
            left_label = await BuildImage.build_text_image(
                labels[0], size=18, font_color=(51, 51, 51)
            )
            right_label = await BuildImage.build_text_image(
                labels[1], size=18, font_color=(51, 51, 51)
            )
            await canvas.paste(
                left_label,
                ((before_img.width - left_label.width) // 2, label_y),
            )
            await canvas.paste(
                right_label,
                (
                    before_img.width + gap
                    + (after_img.width - right_label.width) // 2,
                    label_y,
                ),
            )

        await canvas.paste(before_img, (0, img_y))
        await canvas.paste(after_img, (before_img.width + gap, img_y))
        return canvas

    @staticmethod
    async def stack(
        images: Sequence[BuildImage | Image.Image],
        offset: tuple[int, int] = (15, 15),
        background: ColorAlias = (255, 255, 255),
    ) -> BuildImage:
        """堆叠卡片效果

        参数:
            images: 图片序列（按从下到上顺序）
            offset: 每层偏移量 (x, y)
            background: 背景颜色

        返回:
            BuildImage: 堆叠效果图片

        异常:
            ValueError: 图片列表为空
        """
        if not images:
            raise ValueError("图片列表不能为空")

        normalized = [_to_build_image(img) for img in images]
        dx, dy = offset
        total_w = normalized[0].width + dx * (len(normalized) - 1)
        total_h = normalized[0].height + dy * (len(normalized) - 1)

        canvas = BuildImage(
            total_w + abs(dx) * 2, total_h + abs(dy) * 2, color=background
        )

        for i, img in enumerate(reversed(normalized)):
            idx = len(normalized) - 1 - i
            x = abs(dx) + idx * dx
            y = abs(dy) + idx * dy
            await canvas.paste(img, (x, y))

        return canvas

    @staticmethod
    async def auto_layout(
        images: Sequence[BuildImage | Image.Image],
        max_width: int = 1080,
        gap: int = 10,
        padding: int = 20,
        background: ColorAlias = (255, 255, 255),
    ) -> BuildImage:
        """智能自动排版

        根据图片宽高比和目标宽度自动决定行/列布局

        参数:
            images: 图片序列
            max_width: 目标最大宽度
            gap: 图片间距
            padding: 外边距
            background: 背景颜色

        返回:
            BuildImage: 自动排版的图片
        """
        if not images:
            raise ValueError("图片列表不能为空")

        normalized = [_to_build_image(img) for img in images]
        cols = _auto_columns(len(normalized))
        rows = (len(normalized) + cols - 1) // cols

        cell_w = (max_width - padding * 2 - gap * (cols - 1)) // cols
        scaled = []
        for img in normalized:
            if img.width > cell_w:
                ratio = cell_w / img.width
                await img.resize(width=cell_w, height=int(img.height * ratio))
            scaled.append(img)

        max_h = max(img.height for img in scaled)
        canvas_w = max_width
        canvas_h = max_h * rows + gap * (rows - 1) + padding * 2

        canvas = BuildImage(canvas_w, canvas_h, color=background)
        for i, img in enumerate(scaled):
            col = i % cols
            row = i // cols
            x = padding + col * (cell_w + gap) + (cell_w - img.width) // 2
            y = padding + row * (max_h + gap) + (max_h - img.height) // 2
            await canvas.paste(img, (x, y))

        return canvas


def _to_build_image(image: BuildImage | Image.Image) -> BuildImage:
    """统一转换为 BuildImage

    参数:
        image: BuildImage 或 PIL Image 对象

    返回:
        BuildImage: 转换后的对象
    """
    if isinstance(image, BuildImage):
        return image
    buf = BytesIO()
    image.save(buf, format="PNG")
    return BuildImage.open(buf.getvalue())


def _auto_columns(count: int) -> int:
    """根据图片数量自动决定列数

    参数:
        count: 图片数量

    返回:
        int: 推荐列数
    """
    if count <= 1:
        return 1
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4
