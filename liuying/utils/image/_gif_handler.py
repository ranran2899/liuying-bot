"""GIF 动图处理模块

提供 GIF 帧提取、合成、添加文字/图片水印、缩放、裁剪、倒放等帧级处理能力
基于 PIL Image 的 seek/tell/n_frames 接口实现

注意
----

GIF 处理后调色板会被重新量化，原始 ``transparency`` 索引可能失效
本模块统一使用 ``RGBA`` 模式处理帧数据，由 PIL 自动选择新的透明色索引
"""

from io import BytesIO

from PIL import Image, ImageDraw, ImageSequence

from liuying.utils.image._build_image import BuildImage, _to_rgb


class GifHandler:
    """GIF 动图处理工具类

    提供帧级编辑能力，支持给每帧添加文字/图片水印、缩放、裁剪、倒放等操作
    所有方法均为静态方法
    """

    @staticmethod
    def extract_frames(gif_bytes: bytes) -> list[BuildImage]:
        """提取 GIF 所有帧为 BuildImage 列表

        会自动合成 GIF 的 disposal 帧，避免透明区域出现空洞

        参数:
            gif_bytes: GIF 二进制数据

        返回:
            list[BuildImage]: 帧列表

        异常:
            ValueError: 数据不是动图
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            if not getattr(gif, "is_animated", False):
                raise ValueError("数据不是动图，无法提取帧")
            frames = list(_iter_full_frames(gif))
        return [_to_build_image(f) for f in frames]

    @staticmethod
    def extract_frame(gif_bytes: bytes, index: int = 0) -> BuildImage:
        """提取 GIF 单帧为静态图

        参数:
            gif_bytes: GIF 二进制数据
            index: 帧索引（从 0 开始）

        返回:
            BuildImage: 单帧图片

        异常:
            ValueError: 帧索引越界
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            n_frames = getattr(gif, "n_frames", 1)
            if index < 0 or index >= n_frames:
                raise ValueError(f"帧索引越界: {index}，有效范围 0-{n_frames - 1}")
            frames = list(_iter_full_frames(gif))
            return _to_build_image(frames[index])

    @staticmethod
    def build_gif(
        frames: list[bytes] | list[Image.Image] | list[BuildImage],
        duration: int = 100,
        loop: int = 0,
    ) -> bytes:
        """合成 GIF

        参数:
            frames: 帧列表（bytes/PIL Image/BuildImage）
            duration: 每帧时长（毫秒）
            loop: 循环次数（0 表示无限循环）

        返回:
            bytes: GIF 二进制数据

        异常:
            ValueError: 帧列表为空
        """
        if not frames:
            raise ValueError("帧列表不能为空")

        pil_frames = [_to_pil_image(f).convert("RGBA") for f in frames]
        return _save_gif(pil_frames, duration, loop)

    @staticmethod
    def add_text(
        gif_bytes: bytes,
        text: str,
        pos: tuple[int, int] = (10, 10),
        font_size: int = 24,
        fill: str | tuple[int, int, int] = (255, 0, 0),
        font: str = "HYWenHei-85W.ttf",
        outline: str | tuple[int, int, int] | None = None,
        outline_width: int = 2,
    ) -> bytes:
        """给 GIF 每帧添加文字水印

        参数:
            gif_bytes: GIF 二进制数据
            text: 文字内容
            pos: 文字位置
            font_size: 字体大小
            fill: 文字颜色
            font: 字体名称
            outline: 描边颜色（None 表示无描边）
            outline_width: 描边宽度

        返回:
            bytes: 处理后的 GIF 二进制数据
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            duration = gif.info.get("duration", 100)
            loop = gif.info.get("loop", 0)
            _font = BuildImage.load_font(font, font_size)
            fill_rgb = _to_rgb(fill)
            outline_rgb = _to_rgb(outline) if outline else None

            new_frames = []
            for frame in _iter_full_frames(gif):
                rgba = frame.convert("RGBA")
                draw = ImageDraw.Draw(rgba)
                if outline_rgb is not None:
                    _draw_outlined_text(
                        draw, pos, text, _font, fill_rgb, outline_rgb, outline_width
                    )
                else:
                    draw.text(pos, text, fill=fill_rgb, font=_font)
                new_frames.append(rgba)

        return _save_gif(new_frames, duration, loop)

    @staticmethod
    def add_image_watermark(
        gif_bytes: bytes,
        watermark: BuildImage | Image.Image | bytes,
        pos: tuple[int, int] = (10, 10),
        opacity: float = 1.0,
    ) -> bytes:
        """给 GIF 每帧添加图片水印

        参数:
            gif_bytes: GIF 二进制数据
            watermark: 水印图片（BuildImage/PIL Image/bytes）
            pos: 水印位置
            opacity: 不透明度 0-1

        返回:
            bytes: 处理后的 GIF 二进制数据
        """
        wm_pil = _to_pil_image(watermark).convert("RGBA")
        if opacity < 1.0:
            alpha = wm_pil.split()[-1].point(
                lambda p: int(p * max(0.0, min(1.0, opacity)))
            )
            wm_pil.putalpha(alpha)

        with Image.open(BytesIO(gif_bytes)) as gif:
            duration = gif.info.get("duration", 100)
            loop = gif.info.get("loop", 0)
            new_frames = []
            for frame in _iter_full_frames(gif):
                rgba = frame.convert("RGBA")
                rgba.alpha_composite(wm_pil, pos)
                new_frames.append(rgba)

        return _save_gif(new_frames, duration, loop)

    @staticmethod
    def resize_gif(
        gif_bytes: bytes,
        max_size: tuple[int, int] = (400, 400),
        resample: int = Image.Resampling.LANCZOS,
    ) -> bytes:
        """缩放 GIF

        参数:
            gif_bytes: GIF 二进制数据
            max_size: 最大尺寸
            resample: 重采样算法

        返回:
            bytes: 缩放后的 GIF 二进制数据
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            duration = gif.info.get("duration", 100)
            loop = gif.info.get("loop", 0)
            new_frames = []
            for frame in _iter_full_frames(gif):
                rgba = frame.convert("RGBA")
                rgba.thumbnail(max_size, resample)
                new_frames.append(rgba)

        return _save_gif(new_frames, duration, loop)

    @staticmethod
    def crop_gif(gif_bytes: bytes, box: tuple[int, int, int, int]) -> bytes:
        """裁剪 GIF

        参数:
            gif_bytes: GIF 二进制数据
            box: 裁剪区域 (left, upper, right, lower)

        返回:
            bytes: 裁剪后的 GIF 二进制数据
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            duration = gif.info.get("duration", 100)
            loop = gif.info.get("loop", 0)
            new_frames = []
            for frame in _iter_full_frames(gif):
                rgba = frame.convert("RGBA").crop(box)
                new_frames.append(rgba)

        return _save_gif(new_frames, duration, loop)

    @staticmethod
    def reverse(gif_bytes: bytes) -> bytes:
        """倒放 GIF

        参数:
            gif_bytes: GIF 二进制数据

        返回:
            bytes: 倒放后的 GIF 二进制数据
        """
        with Image.open(BytesIO(gif_bytes)) as gif:
            duration = gif.info.get("duration", 100)
            loop = gif.info.get("loop", 0)
            frames = [f.convert("RGBA") for f in _iter_full_frames(gif)]

        frames.reverse()
        return _save_gif(frames, duration, loop)


def _iter_full_frames(gif: Image.Image):
    """迭代 GIF 帧并自动合成 disposal

    处理 GIF 的 disposal 方法（2/3）以正确合成完整画面

    参数:
        gif: 打开的 GIF 图片

    Yields:
        Image.Image: 完整画面的帧（RGBA）
    """
    prev_frame: Image.Image | None = None
    prev_disposal = 0

    for frame in ImageSequence.Iterator(gif):
        # 提取当前帧
        current = frame.convert("RGBA")
        disposal = frame.info.get("disposal", 0)

        # 应用上一帧的 disposal
        if prev_frame is not None:
            if prev_disposal == 2:
                # 恢复为上一帧之前的状态（背景色）
                pass
            elif prev_disposal == 3:
                current.alpha_composite(prev_frame, (0, 0))

        yield current
        prev_frame = current.copy()
        prev_disposal = disposal


def _to_pil_image(image: BuildImage | Image.Image | bytes) -> Image.Image:
    """统一转换为 PIL Image（返回独立副本）

    参数:
        image: 输入图片

    返回:
        Image.Image: PIL Image 对象的副本（避免副作用）
    """
    match image:
        case BuildImage():
            return image.mark_img.copy()
        case bytes():
            with Image.open(BytesIO(image)) as img:
                return img.copy()
        case _:
            return image.copy()


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    pos: tuple[float, float],
    text: str,
    font,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    width: int,
) -> None:
    """绘制带描边的文字（8 方向描边）

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
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text((x + dx, y + dy), text, fill=outline, font=font)
    draw.text(pos, text, fill=fill, font=font)


def _save_gif(
    frames: list[Image.Image],
    duration: int,
    loop: int,
) -> bytes:
    """保存帧列表为 GIF

    使用 RGBA 模式保存，由 PIL 自动选择透明色索引
    不复用原始 GIF 的 transparency 索引（调色板已重新量化）

    参数:
        frames: PIL Image 帧列表
        duration: 每帧时长
        loop: 循环次数

    返回:
        bytes: GIF 二进制数据
    """
    if not frames:
        raise ValueError("帧列表不能为空")

    # 统一转换为 P 模式，PIL 自动处理透明色索引
    quantized = [f.convert("RGBA").quantize() for f in frames]

    output = BytesIO()
    quantized[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=quantized[1:],
        duration=duration,
        loop=loop,
        disposal=2,
    )
    return output.getvalue()


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
