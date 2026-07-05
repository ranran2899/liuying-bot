"""视觉理解

提供图片/GIF 内容摘要、视觉能力路由与图片理解结果缓存。
"""

from .capabilities import (
    VisionCapabilityInfo,
    VisionCapabilityRouter,
    VisionRouteResult,
    vision_router,
)
from .manager import (
    GifSummary,
    ImageSummary,
    build_vision_messages,
    summarize_gif,
    summarize_image,
)
from .result_cache import ImageResultCache, image_result_cache

__all__ = [
    "GifSummary",
    "ImageResultCache",
    "ImageSummary",
    "VisionCapabilityInfo",
    "VisionCapabilityRouter",
    "VisionRouteResult",
    "build_vision_messages",
    "image_result_cache",
    "summarize_gif",
    "summarize_image",
    "vision_router",
]
