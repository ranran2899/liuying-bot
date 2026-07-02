"""图片工具包

统一的图片工具入口，通过 re-export 暴露公共 API：
- 基础构建：``BuildImage``、``ColorAlias``
- 图片模式：``ModeType``、``CenterType``、``FilterType``
- 排行榜：``BuildRankMat``、``BuildMat``
- 模板渲染：``ImageTemplate``、``Markdown``、``MarkdownTable``、
  ``Notebook``、``RowStyle``
- 工具集合：``TextRenderer``、``ImageGrouper``、``ImageHasher``、``ImageConverter``
- 图片合成：``ImageComposer``
- 图片特效：``ImageEffects``、``GradientDirection``、``ArtFilter``
- GIF 处理：``GifHandler``
- 二维码生成：``QrGenerator``、``QrConfig``、``ErrorCorrectionLevel``
- 图片元数据：``ImageMetaProcessor``、``ImageInfo``
- 配置常量：``ALLOWED_EXTENSIONS``

业务逻辑分布在子模块中：
- ``_build_image``: 基础构建类 ``BuildImage``，提供贴图、文字、形状、滤镜等原子能力
- ``_build_mat``: 排行榜生成 ``BuildRankMat``
- ``_image_template``: 图片模板 ``ImageTemplate``、``Markdown``、``Notebook``
- ``image_utils``: 文本渲染、图片分组、哈希、转换工具类
- ``_image_composer``: 多图合成 ``ImageComposer``
- ``_image_effects``: 图片特效 ``ImageEffects``
- ``_gif_handler``: GIF 帧级处理 ``GifHandler``
- ``_qr_generator``: 二维码生成 ``QrGenerator``
- ``_image_meta``: 图片元数据处理 ``ImageMetaProcessor``

枚举类型统一从 ``liuying.utils.enum`` 导入：
- ``ModeType``、``CenterType``、``FilterType``
- ``GradientDirection``、``ArtFilter``
- ``ModuleStyle``
"""
from liuying.utils.enum import (
    ArtFilter,
    CenterType,
    FilterType,
    GradientDirection,
    ModeType,
    ModuleStyle,
)

from ._build_image import BuildImage, ColorAlias
from ._build_mat import BuildMat, BuildRankMat, ColorValue, DataValue
from ._gif_handler import GifHandler
from ._image_composer import ImageComposer
from ._image_effects import ImageEffects
from ._image_meta import ImageInfo, ImageMetaProcessor
from ._image_template import (
    ColorType,
    ImageTemplate,
    Markdown,
    MarkdownTable,
    Notebook,
    RowStyle,
    TableDataItem,
)
from ._qr_generator import ErrorCorrectionLevel, QrConfig, QrGenerator
from .image_utils import (
    ALLOWED_EXTENSIONS,
    ImageConverter,
    ImageGrouper,
    ImageHasher,
    TextRenderer,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "ArtFilter",
    "BuildImage",
    "BuildMat",
    "BuildRankMat",
    "CenterType",
    "ColorAlias",
    "ColorType",
    "ColorValue",
    "DataValue",
    "ErrorCorrectionLevel",
    "FilterType",
    "GifHandler",
    "GradientDirection",
    "ImageComposer",
    "ImageConverter",
    "ImageEffects",
    "ImageGrouper",
    "ImageHasher",
    "ImageInfo",
    "ImageMetaProcessor",
    "ImageTemplate",
    "Markdown",
    "MarkdownTable",
    "ModeType",
    "ModuleStyle",
    "Notebook",
    "QrConfig",
    "QrGenerator",
    "RowStyle",
    "TableDataItem",
    "TextRenderer",
]
