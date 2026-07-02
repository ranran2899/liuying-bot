"""二维码生成模块

提供标准二维码、带 Logo 二维码、样式化二维码生成能力
基于 qrcode 库生成矩阵，使用 PIL 自定义渲染点阵样式
"""

from dataclasses import dataclass, replace
from io import BytesIO

from PIL import Image, ImageDraw
import qrcode
from qrcode.constants import (
    ERROR_CORRECT_H,
    ERROR_CORRECT_L,
    ERROR_CORRECT_M,
    ERROR_CORRECT_Q,
)

from liuying.utils.enum import ModuleStyle
from liuying.utils.image._build_image import BuildImage, _to_rgb


class ErrorCorrectionLevel:
    """二维码容错等级

    属性:
        L: 低（7%）
        M: 中（15%，默认）
        Q: 较高（25%）
        H: 高（30%，支持 Logo 遮挡）
    """

    L = ERROR_CORRECT_L
    M = ERROR_CORRECT_M
    Q = ERROR_CORRECT_Q
    H = ERROR_CORRECT_H


@dataclass(slots=True)
class QrConfig:
    """二维码生成配置

    属性:
        size: 输出图片尺寸（像素）
        border: 边框空白宽度（模块数）
        color: 二维码颜色
        bg_color: 背景颜色
        error_correction: 容错等级
        box_size: 每个模块的像素大小
    """

    size: int = 400
    border: int = 2
    color: str | tuple[int, int, int] = (0, 0, 0)
    bg_color: str | tuple[int, int, int] = (255, 255, 255)
    error_correction: int = ERROR_CORRECT_M
    box_size: int = 10


class QrGenerator:
    """二维码生成工具类

    提供基础、带 Logo、样式化二维码生成能力
    所有方法均为静态方法，返回 BuildImage
    """

    @staticmethod
    def generate(data: str, config: QrConfig | None = None) -> BuildImage:
        """生成基础二维码

        参数:
            data: 二维码内容（URL/文本）
            config: 生成配置（None 使用默认）

        返回:
            BuildImage: 二维码图片
        """
        cfg = config or QrConfig()
        matrix = _build_matrix(data, cfg.error_correction, cfg.border)

        img = _render_matrix(
            matrix,
            box_size=cfg.box_size,
            border=cfg.border,
            color=cfg.color,
            bg_color=cfg.bg_color,
            style=ModuleStyle.SQUARE,
        )

        img = _resize_to(img, cfg.size)
        return _to_build_image(img)

    @staticmethod
    def generate_with_logo(
        data: str,
        logo: BuildImage | bytes,
        config: QrConfig | None = None,
        logo_ratio: float = 0.2,
    ) -> BuildImage:
        """生成带 Logo 的二维码

        使用高容错等级（H，30%）以支持 Logo 遮挡

        参数:
            data: 二维码内容
            logo: Logo 图片（BuildImage 或 bytes）
            config: 生成配置（None 使用默认，强制 H 容错）
            logo_ratio: Logo 占比（0.05-0.3）

        返回:
            BuildImage: 带 Logo 的二维码图片
        """
        logo_ratio = max(0.05, min(0.3, logo_ratio))
        # 使用 replace 创建副本，避免修改入参产生副作用
        cfg = replace(config or QrConfig(), error_correction=ERROR_CORRECT_H)

        matrix = _build_matrix(data, cfg.error_correction, cfg.border)
        img = _render_matrix(
            matrix,
            box_size=cfg.box_size,
            border=cfg.border,
            color=cfg.color,
            bg_color=cfg.bg_color,
            style=ModuleStyle.SQUARE,
        )

        logo_pil = _to_pil(logo).convert("RGBA")
        logo_size = int(cfg.size * logo_ratio)
        logo_pil.thumbnail((logo_size, logo_size))

        img = _resize_to(img, cfg.size)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        logo_pos = (
            (img.width - logo_pil.width) // 2,
            (img.height - logo_pil.height) // 2,
        )
        img.alpha_composite(logo_pil, logo_pos)

        return _to_build_image(img)

    @staticmethod
    def generate_styled(
        data: str,
        config: QrConfig | None = None,
        style: ModuleStyle | str = ModuleStyle.ROUNDED,
    ) -> BuildImage:
        """生成样式化二维码

        参数:
            data: 二维码内容
            config: 生成配置（None 使用默认）
            style: 点阵样式（SQUARE/ROUNDED/CIRCLE/GAPPED）

        返回:
            BuildImage: 样式化二维码图片
        """
        cfg = config or QrConfig()
        style_val = (
            style if isinstance(style, ModuleStyle) else ModuleStyle(style)
        )

        matrix = _build_matrix(data, cfg.error_correction, cfg.border)
        img = _render_matrix(
            matrix,
            box_size=cfg.box_size,
            border=cfg.border,
            color=cfg.color,
            bg_color=cfg.bg_color,
            style=style_val,
        )

        img = _resize_to(img, cfg.size)
        return _to_build_image(img)


def _build_matrix(data: str, error_correction: int, border: int):
    """构建二维码矩阵

    参数:
        data: 数据内容
        error_correction: 容错等级
        border: 边框宽度

    返回:
        qrcode.QRCode: 二维码对象（已 make）
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=1,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr


def _render_matrix(
    qr,
    box_size: int,
    border: int,
    color: str | tuple[int, int, int],
    bg_color: str | tuple[int, int, int],
    style: ModuleStyle,
) -> Image.Image:
    """渲染二维码矩阵为 PIL Image

    参数:
        qr: 二维码对象
        box_size: 模块像素大小
        border: 边框宽度
        color: 二维码颜色
        bg_color: 背景颜色
        style: 点阵样式

    返回:
        Image.Image: 渲染后的图片
    """
    matrix = qr.modules
    n = len(matrix)
    total_size = (n + border * 2) * box_size

    color_rgb = _to_rgb(color)
    bg_rgb = _to_rgb(bg_color)

    img = Image.new("RGBA", (total_size, total_size), (*bg_rgb, 255))
    draw = ImageDraw.Draw(img)
    radius = max(1, box_size // 2)

    for y, row in enumerate(matrix):
        for x, is_dark in enumerate(row):
            if not is_dark:
                continue
            px = (x + border) * box_size
            py = (y + border) * box_size
            box = [px, py, px + box_size, py + box_size]
            match style:
                case ModuleStyle.SQUARE:
                    draw.rectangle(box, fill=(*color_rgb, 255))
                case ModuleStyle.ROUNDED:
                    draw.rounded_rectangle(box, radius=radius, fill=(*color_rgb, 255))
                case ModuleStyle.CIRCLE:
                    draw.ellipse(box, fill=(*color_rgb, 255))
                case ModuleStyle.GAPPED:
                    gap = max(1, box_size // 5)
                    draw.rectangle(
                        [box[0] + gap, box[1] + gap, box[2] - gap, box[3] - gap],
                        fill=(*color_rgb, 255),
                    )
    return img


def _resize_to(img: Image.Image, size: int) -> Image.Image:
    """调整图片到指定尺寸

    参数:
        img: 原图
        size: 目标尺寸

    返回:
        Image.Image: 调整后的图片
    """
    if img.width != size or img.height != size:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def _to_pil(image: BuildImage | bytes) -> Image.Image:
    """统一转换为 PIL Image

    参数:
        image: BuildImage 或 bytes

    返回:
        Image.Image: PIL Image 对象
    """
    if isinstance(image, BuildImage):
        return image.mark_img.copy()
    with Image.open(BytesIO(image)) as img:
        return img.convert("RGBA")


def _to_build_image(img: Image.Image) -> BuildImage:
    """PIL Image 转换为 BuildImage

    参数:
        img: PIL Image 对象

    返回:
        BuildImage: BuildImage 对象
    """
    buf = BytesIO()
    img.save(buf, format="PNG")
    return BuildImage.open(buf.getvalue())
