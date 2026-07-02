"""图片工具模块

提供图片处理相关的工具类，包括文本转图片、图片分组、图片哈希、格式转换等功能
所有功能已封装为类，便于统一管理和导入
"""

from collections.abc import Awaitable, Callable
from io import BytesIO
import os
from pathlib import Path
import random
import re

import imagehash
from nonebot.utils import is_coroutine_callable
from PIL import Image

from liuying.configs.path_config import TEMP_PATH
from liuying.utils.image._build_image import BuildImage, ColorAlias
from liuying.utils.log import logger

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico"}
)
"""允许的图片扩展名"""

__all__ = [
    "ALLOWED_EXTENSIONS",
    "ImageConverter",
    "ImageGrouper",
    "ImageHasher",
    "TextRenderer",
]


class TextRenderer:
    """文本转图片渲染器

    支持解析带格式标签 <f></f> 的文本并生成图片
    """

    @staticmethod
    async def render(
        text: str,
        auto_parse: bool = True,
        font_size: int = 20,
        color: str | tuple[int, int, int] = (255, 255, 255),
        font: str = "HYWenHei-85W.ttf",
        font_color: str | tuple[int, int, int] = (0, 0, 0),
        padding: int | tuple[int, int, int, int] = 0,
        _add_height: float = 0,
    ) -> BuildImage:
        """解析文本并转为图片

        使用标签 <f> </f> 可选配置项:
            font: str -> 特殊文本字体
            fs / font_size: int -> 特殊文本大小
            fc / font_color: Union[str, Tuple[int, int, int]] -> 特殊文本颜色

        示例:
            在不在，<f font=YSHaoShenTi-2.ttf font_size=30 font_color=red>HibiKi</f>

        参数:
            text: 文本
            auto_parse: 是否自动解析，否则原样发送
            font_size: 普通字体大小
            color: 背景颜色
            font: 普通字体
            font_color: 普通字体颜色
            padding: 文本外边距，元组类型时为（上，左，下，右）
            _add_height: 手动额外添加高度

        返回:
            BuildImage: 生成的图片
        """
        if not text:
            raise ValueError("文本转图片 text 不能为空...")

        pw = ph = top_padding = left_padding = 0
        match padding:
            case int():
                pw = ph = padding * 2
                top_padding = left_padding = padding
            case (int(top), int(left), int(bottom), int(right)):
                pw = left + right
                ph = top + bottom
                top_padding = top
                left_padding = left

        _font = BuildImage.load_font(font, font_size)

        if auto_parse and re.search(r"<f(.*)>(.*)</f>", text):
            return await TextRenderer._parse_formatted(
                text, _font, font, font_size, font_color, color,
                pw, ph, top_padding, left_padding,
            )

        return await TextRenderer._create_plain(
            text, _font, font, font_size, font_color, color,
            pw, ph, top_padding, left_padding,
        )

    @staticmethod
    async def _parse_formatted(
        text: str,
        _font,
        font: str,
        font_size: int,
        font_color: str | tuple[int, int, int],
        color: str | tuple[int, int, int],
        pw: int,
        ph: int,
        top_padding: int,
        left_padding: int,
    ) -> BuildImage:
        """解析带格式标签的文本并生成图片"""
        _data: list[tuple[tuple[int, int], str, str, str]] = []
        new_text = ""
        placeholder_index = 0

        for s in text.split("</f>"):
            if r := re.search(r"<f(.*)>(.*)", s):
                start, end = r.span()
                if start != 0 and (t := s[:start]):
                    new_text += t
                _data.append(
                    ((start, end), f"[placeholder_{placeholder_index}]",
                     r.group(1).strip(), r.group(2))
                )
                new_text += f"[placeholder_{placeholder_index}]"
                placeholder_index += 1

        new_text += text.split("</f>")[-1]
        image_list = []
        current_placeholder_index = 0

        for s in new_text.split("\n"):
            _tmp_text = s
            img_width = 0
            img_height = BuildImage.get_text_size("正", _font)[1]
            _tmp_index = current_placeholder_index

            for _ in range(s.count("[placeholder_")):
                placeholder = _data[_tmp_index]
                if "font_size" in placeholder[2]:
                    if r := re.search(r"font_size=['\"]?(\d+)", placeholder[2]):
                        w, h = BuildImage.get_text_size(
                            placeholder[3], font, int(r.group(1))
                        )
                        img_height = max(img_height, h)
                        img_width += w
                else:
                    img_width += BuildImage.get_text_size(placeholder[3], _font)[0]
                _tmp_text = _tmp_text.replace(f"[placeholder_{_tmp_index}]", "")
                _tmp_index += 1

            img_width += BuildImage.get_text_size(_tmp_text, _font)[0]
            A = BuildImage(img_width, img_height, color=color,
                           font=font, font_size=font_size)
            basic_font_h = A.getsize("正")[1]
            current_width = 0

            for _ in range(s.count("[placeholder_")):
                if not s.startswith(f"[placeholder_{current_placeholder_index}]"):
                    slice_ = s.split(f"[placeholder_{current_placeholder_index}]")
                    await A.text(
                        (current_width, A.height - basic_font_h - 1),
                        slice_[0],
                        font_color,
                    )
                    current_width += A.getsize(slice_[0])[0]

                placeholder = _data[current_placeholder_index]
                _f, _fs, _fc = TextRenderer._parse_font_config(
                    placeholder[2], font, font_size, font_color
                )

                text_img = await BuildImage.build_text_image(
                    placeholder[3], font=_f, size=_fs, font_color=_fc
                )
                _img_h = (
                    int(A.height / 2 - text_img.height / 2)
                    if new_text == "[placeholder_0]"
                    else A.height - text_img.height
                )
                await A.paste(text_img, (current_width, _img_h - 1))
                current_width += text_img.width
                s = s[
                    s.index(f"[placeholder_{current_placeholder_index}]")
                    + len(f"[placeholder_{current_placeholder_index}]"):
                ]
                current_placeholder_index += 1

            if s:
                slice_ = s.split(f"[placeholder_{current_placeholder_index}]")
                await A.text((current_width, A.height - basic_font_h), slice_[0])
                current_width += A.getsize(slice_[0])[0]

            await A.crop((0, 0, current_width, A.height))
            image_list.append(A)

        width = max(img.width for img in image_list) + pw
        height = sum(img.height for img in image_list) + ph
        A = BuildImage(width + left_padding, height + top_padding, color=color)
        current_height = top_padding

        for img in image_list:
            await A.paste(img, (left_padding, current_height))
            current_height += img.height

        return A

    @staticmethod
    def _parse_font_config(
        config_str: str, default_font: str, default_size: int, default_color
    ) -> tuple[str, int, str | tuple[int, int, int]]:
        """解析字体配置字符串

        参数:
            config_str: 配置字符串
            default_font: 默认字体
            default_size: 默认大小
            default_color: 默认颜色

        返回:
            tuple: (字体, 大小, 颜色)
        """
        _font = default_font
        _font_size = default_size
        _font_color = default_color

        for e in config_str.split():
            match e.split("="):
                case ["font", value]:
                    _font = value
                case ["font_size", value] | ["fs", value]:
                    _font_size = min(max(int(value), 1), 1000)
                case ["font_color", value] | ["fc", value]:
                    _font_color = value

        return _font, _font_size, _font_color

    @staticmethod
    async def _create_plain(
        text: str,
        _font,
        font: str,
        font_size: int,
        font_color: str | tuple[int, int, int],
        color: str | tuple[int, int, int],
        pw: int,
        ph: int,
        top_padding: int,
        left_padding: int,
    ) -> BuildImage:
        """创建纯文本图片"""
        _, h = BuildImage.get_text_size("正", _font)
        line_height = font_size // 3

        lines = text.split("\n")
        image_list = [
            await BuildImage.build_text_image(
                s.strip() or "正", font, font_size, font_color
            )
            for s in lines
        ]

        width = max(
            BuildImage.get_text_size(s.strip() or "正", _font)[0] for s in lines
        ) + pw
        height = sum(img.height + 8 for img in image_list) + ph

        A = BuildImage(width + left_padding, height + top_padding + 2, color=color)
        cur_h = top_padding

        for img in image_list:
            await A.paste(img, (left_padding, cur_h))
            cur_h += img.height + line_height

        return A


class ImageGrouper:
    """图片分组与装箱工具

    根据图片尺寸进行分组排列，支持自动组装
    """

    @staticmethod
    def group(image_list: list[BuildImage]) -> tuple[list[list[BuildImage]], int]:
        """根据图片大小进行分组

        参数:
            image_list: 排序图片列表

        返回:
            tuple[list[list[BuildImage]], int]: 分组结果和最大尺寸
        """
        if not image_list:
            return [], 0

        sorted_list = sorted(image_list, key=lambda x: x.height, reverse=True)
        max_image = sorted_list[0]
        remaining = sorted_list[1:]
        max_h = max_image.height

        image_group: list[list[BuildImage]] = [[max_image]]
        used_ids: set[str] = set()
        surplus_list = remaining[:]

        for image in remaining:
            if image.uid in used_ids:
                continue

            group = [image]
            used_ids.add(image.uid)
            curr_h = image.height

            while True:
                surplus_list = [x for x in surplus_list if x.uid not in used_ids]
                found = False

                for tmp in surplus_list:
                    temp_h = curr_h + tmp.height + 10
                    if temp_h < max_h or abs(max_h - temp_h) < 100:
                        curr_h += tmp.height + 15
                        used_ids.add(tmp.uid)
                        group.append(tmp)
                        found = True
                        break

                if not found:
                    break

            image_group.append(group)

        while surplus_list:
            surplus_list = [x for x in surplus_list if x.uid not in used_ids]
            if not surplus_list:
                break

            surplus_list.sort(key=lambda x: x.height, reverse=True)

            for img in surplus_list:
                if img.uid in used_ids:
                    continue

                min_h = float("inf")
                min_index = -1

                for i, ig in enumerate(image_group):
                    if (total_h := sum(x.height for x in ig)) < min_h:
                        min_h = total_h
                        min_index = i

                if min_index != -1:
                    image_group[min_index].append(img)
                    used_ids.add(img.uid)

        max_h = max(sum(x.height + 15 for x in ig) for ig in image_group)
        max_w = sum(max(x.width for x in ig) + 30 for ig in image_group)

        used_ids.clear()

        while abs(max_h - max_w) > 200 and len(image_group) - 1 >= len(image_group[-1]):
            for img in image_group[-1]:
                min_h = float("inf")
                min_index = -1

                for i, ig in enumerate(image_group):
                    if (total_h := sum(x.height for x in ig) + img.height) < min_h:
                        min_h = total_h
                        min_index = i

                used_ids.add(min_index)
                image_group[min_index].append(img)

            max_w -= max(x.width for x in image_group[-1]) - 30
            image_group.pop()
            max_h = max(sum(x.height + 15 for x in ig) for ig in image_group)

        return image_group, max(max_h + 250, max_w + 70)

    @staticmethod
    async def build_sorted(
        image_group: list[list[BuildImage]],
        h: int | None = None,
        padding_top: int = 200,
        color: ColorAlias = (255, 255, 255),
        background_path: Path | None = None,
        background_handle: Callable[[BuildImage], Awaitable] | None = None,
    ) -> BuildImage:
        """对 group 的图片进行组装

        参数:
            image_group: 分组图片列表
            h: max(宽，高)，一般为 group 的返回值，有值时图片必定为正方形
            padding_top: 图像列表与最顶层间距
            color: 背景颜色
            background_path: 背景图片文件夹路径（随机）
            background_handle: 背景图额外操作

        返回:
            BuildImage: 组装后的图片
        """
        bk_file = None
        if background_path:
            random_bk = os.listdir(background_path)
            if random_bk:
                bk_file = random.choice(random_bk)

        if h:
            image_w = image_h = h
        else:
            image_w = sum(max(x.width + 30 for x in ig) + 30 for ig in image_group)
            image_h = max(
                sum(x.height + 10 for x in ig) for ig in image_group
            ) + padding_top

        A = BuildImage(
            image_w,
            image_h,
            font_size=24,
            font="CJGaoDeGuo.otf",
            color=color,
            background=(
                background_path / bk_file
                if background_path and bk_file
                else None
            ),
        )

        if background_handle:
            if is_coroutine_callable(background_handle):
                await background_handle(A)
            else:
                background_handle(A)

        curr_w = 50
        for ig in image_group:
            curr_h = padding_top - 20
            for img in ig:
                await A.paste(img, (curr_w, curr_h))
                curr_h += img.height + 10
            curr_w += max(x.width for x in ig) + 30

        return A


class ImageHasher:
    """图片哈希工具

    提供图片哈希计算与下载图片哈希功能
    """

    @staticmethod
    def hash(image_file: str | Path) -> str:
        """获取图片的hash值

        参数:
            image_file: 图片文件路径

        返回:
            str: 哈希值
        """
        try:
            with open(image_file, "rb") as fp:
                return str(imagehash.average_hash(Image.open(fp)))
        except (OSError, ValueError) as e:
            logger.warning("获取图片Hash出错", "禁言检测", e=e)
            return ""

    @staticmethod
    async def download_hash(
        url: str, mark: str, use_proxy: bool = False
    ) -> str:
        """下载图片获取哈希值

        参数:
            url: 图片url
            mark: 随机标志符
            use_proxy: 是否使用代理

        返回:
            str: 哈希值
        """
        try:
            file_path = TEMP_PATH / f"compare_download_{mark}_img.jpg"
            # 循环依赖:liuying.utils.http.http_utils → .browser → liuying.utils.message
            # → liuying.utils.image → 本模块,故此处延迟导入
            from liuying.utils.http.http_utils import async_httpx

            if await async_httpx.download_file(url, file_path, use_proxy=use_proxy):
                return ImageHasher.hash(file_path)
        except (OSError, ValueError) as e:
            logger.warning("下载读取图片Hash出错", e=e)
        return ""


class ImageConverter:
    """图片格式转换工具

    提供 bytes 转换、尺寸获取、格式转换、缩放等功能
    """

    @staticmethod
    def to_bytes(image: Image.Image) -> bytes:
        """获取bytes

        参数:
            image: PIL Image对象

        返回:
            bytes: 图片字节数据
        """
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def get_size(img_bytes: bytes) -> tuple[str, str]:
        """获取图片尺寸

        参数:
            img_bytes: 图片字节数据

        返回:
            tuple[str, str]: 宽度和高度
        """
        with Image.open(BytesIO(img_bytes)) as image:
            width, height = image.size
        return str(width), str(height)

    @staticmethod
    def convert_format(
        file_data: bytes, target_extension: str = ".webp"
    ) -> bytes:
        """将图片转换为指定格式

        参数:
            file_data: 原始图片二进制数据
            target_extension: 目标扩展名，默认转换为 webp

        返回:
            bytes: 转换后的图片二进制数据

        异常:
            ValueError: 目标格式不受支持时抛出
        """
        target_ext = target_extension.lower()
        if target_ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"不支持的图片格式: {target_extension}")

        image_format = (
            "JPEG" if target_ext in {".jpg", ".jpeg"} else target_ext[1:].upper()
        )
        with Image.open(BytesIO(file_data)) as img:
            if img.mode in ("RGBA", "P") and image_format == "JPEG":
                img = img.convert("RGB")
            output = BytesIO()
            img.save(output, format=image_format)
            return output.getvalue()

    @staticmethod
    def resize(
        file_data: bytes,
        max_size: tuple[int, int] = (1024, 1024),
        resample: int = Image.Resampling.LANCZOS,
        quality: int | None = None,
    ) -> bytes:
        """按比例缩放图片，使其长边不超过指定尺寸

        参数:
            file_data: 原始图片二进制数据
            max_size: 最大宽高元组，默认 1024x1024
            resample: PIL 重采样算法，默认 LANCZOS
            quality: 输出质量 1-100，None 表示使用默认

        返回:
            bytes: 缩放后的图片二进制数据
        """
        with Image.open(BytesIO(file_data)) as img:
            img.thumbnail(max_size, resample=resample)
            output = BytesIO()
            save_format = img.format or "PNG"
            save_kwargs: dict = {}
            if quality is not None and save_format in ("JPEG", "WEBP"):
                save_kwargs["quality"] = max(1, min(100, quality))
            img.save(output, format=save_format, **save_kwargs)
            return output.getvalue()
