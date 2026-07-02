"""图片元数据处理模块

提供图片信息查询、EXIF 读取/清除、方向自动校正等能力
基于 PIL Image 的 _getexif/getexif/ImageOps.exif_transpose 实现
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps


@dataclass(slots=True)
class ImageInfo:
    """图片元信息

    属性:
        width: 宽度
        height: 高度
        format: 格式（如 PNG/JPEG）
        mode: 颜色模式（RGB/RGBA/L 等）
        file_size: 文件大小（字节）
        is_animated: 是否动图
        n_frames: 帧数（非动图为 1）
        exif: EXIF 字典（无则空字典）
    """

    width: int
    height: int
    format: str
    mode: str
    file_size: int
    is_animated: bool
    n_frames: int
    exif: dict[int, Any]


_EXIF_TAG_NAMES: dict[int, str] = {
    271: "Make",
    272: "Model",
    274: "Orientation",
    282: "XResolution",
    283: "YResolution",
    296: "ResolutionUnit",
    306: "DateTime",
    33432: "Copyright",
    33434: "ExposureTime",
    33437: "FNumber",
    37510: "UserComment",
    36867: "DateTimeOriginal",
    36868: "DateTimeDigitized",
    37377: "ISOSpeedRatings",
    37378: "ExposureBiasValue",
    37379: "MaxApertureValue",
    37380: "SubjectDistance",
    37381: "MeteringMode",
    37382: "LightSource",
    37383: "Flash",
    37384: "FocalLength",
    37386: "ExposureMode",
    37396: "SubjectArea",
    40961: "FlashpixVersion",
    40962: "PixelXDimension",
    40963: "PixelYDimension",
    41985: "ExposureProgram",
    41986: "WhiteBalance",
    41987: "DigitalZoomRatio",
    41990: "SceneCaptureType",
    41993: "GPSInfo",
}
"""EXIF 标签名映射（常用标签）"""


class ImageMetaProcessor:
    """图片元数据处理工具类

    提供图片信息查询、EXIF 读取/清除、方向自动校正等能力
    所有方法均为静态方法
    """

    @staticmethod
    def get_info(image_bytes: bytes) -> ImageInfo:
        """获取图片综合信息

        参数:
            image_bytes: 图片二进制数据

        返回:
            ImageInfo: 图片信息
        """
        with Image.open(BytesIO(image_bytes)) as img:
            exif_data = _extract_exif(img)
            return ImageInfo(
                width=img.width,
                height=img.height,
                format=img.format or "UNKNOWN",
                mode=img.mode,
                file_size=len(image_bytes),
                is_animated=getattr(img, "is_animated", False),
                n_frames=getattr(img, "n_frames", 1),
                exif=exif_data,
            )

    @staticmethod
    def read_exif(image_bytes: bytes) -> dict[int, Any]:
        """读取 EXIF 元数据

        参数:
            image_bytes: 图片二进制数据

        返回:
            dict[int, Any]: EXIF 字典（标签号 -> 值）
        """
        with Image.open(BytesIO(image_bytes)) as img:
            return _extract_exif(img)

    @staticmethod
    def read_exif_named(image_bytes: bytes) -> dict[str, Any]:
        """读取 EXIF 元数据（带名称）

        参数:
            image_bytes: 图片二进制数据

        返回:
            dict[str, Any]: EXIF 字典（标签名 -> 值）
        """
        raw = ImageMetaProcessor.read_exif(image_bytes)
        named: dict[str, Any] = {}
        for tag, value in raw.items():
            name = _EXIF_TAG_NAMES.get(tag, f"Tag_{tag}")
            named[name] = value
        return named

    @staticmethod
    def clear_exif(image_bytes: bytes) -> bytes:
        """清除 EXIF 元数据（隐私保护）

        直接调用 ``getexif().clear()`` 后重新保存，保留原始模式与调色板

        参数:
            image_bytes: 原始图片二进制数据

        返回:
            bytes: 清除 EXIF 后的图片二进制数据
        """
        with Image.open(BytesIO(image_bytes)) as img:
            exif = img.getexif() if hasattr(img, "getexif") else None
            if exif is not None:
                exif.clear()

            # 直接保存原图（保留模式、调色板、动画）
            output = BytesIO()
            img_format = img.format or "PNG"
            save_kwargs: dict[str, Any] = {}
            if img_format == "JPEG":
                save_kwargs["quality"] = 95
            elif img_format == "GIF":
                save_kwargs["save_all"] = True
            img.save(output, format=img_format, **save_kwargs)
            return output.getvalue()

    @staticmethod
    def auto_orient(image_bytes: bytes) -> bytes:
        """根据 EXIF Orientation 自动校正方向

        参数:
            image_bytes: 原始图片二进制数据

        返回:
            bytes: 校正方向后的图片二进制数据
        """
        with Image.open(BytesIO(image_bytes)) as img:
            oriented = ImageOps.exif_transpose(img)
            output = BytesIO()
            img_format = img.format or "PNG"
            save_kwargs: dict[str, Any] = {}
            if img_format == "JPEG":
                # JPEG 不支持透明通道，强制 RGB
                if oriented.mode in ("RGBA", "P", "LA"):
                    oriented = oriented.convert("RGB")
                save_kwargs["quality"] = 95
            oriented.save(output, format=img_format, **save_kwargs)
            return output.getvalue()

    @staticmethod
    def get_format(image_bytes: bytes) -> str:
        """获取图片格式

        参数:
            image_bytes: 图片二进制数据

        返回:
            str: 图片格式（如 PNG/JPEG）
        """
        with Image.open(BytesIO(image_bytes)) as img:
            return img.format or "UNKNOWN"

    @staticmethod
    def is_animated(image_bytes: bytes) -> bool:
        """判断是否动图

        参数:
            image_bytes: 图片二进制数据

        返回:
            bool: True 表示是动图
        """
        with Image.open(BytesIO(image_bytes)) as img:
            return bool(getattr(img, "is_animated", False))

    @staticmethod
    def get_dimensions(image_bytes: bytes) -> tuple[int, int]:
        """获取图片尺寸

        参数:
            image_bytes: 图片二进制数据

        返回:
            tuple[int, int]: (宽, 高)
        """
        with Image.open(BytesIO(image_bytes)) as img:
            return img.size

    @staticmethod
    def needs_orientation(image_bytes: bytes) -> bool:
        """判断图片是否需要方向校正

        参数:
            image_bytes: 图片二进制数据

        返回:
            bool: True 表示存在 Orientation 标签且非 1（正常方向）
        """
        exif = ImageMetaProcessor.read_exif(image_bytes)
        orientation = exif.get(274)
        return orientation is not None and orientation != 1


def _extract_exif(img: Image.Image) -> dict[int, Any]:
    """提取图片 EXIF 数据

    参数:
        img: PIL Image 对象

    返回:
        dict[int, Any]: EXIF 字典
    """
    try:
        exif = img.getexif()
        if exif is None:
            return {}
        return dict(exif)
    except (AttributeError, OSError, ValueError):
        return {}
