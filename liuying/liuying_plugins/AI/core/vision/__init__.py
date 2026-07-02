"""视觉理解

提供图片/GIF/视频内容摘要、视觉能力路由、图片生成、
图片引用追踪与图片理解结果缓存。
"""

from .capabilities import (
    VisionCapabilityInfo,
    VisionCapabilityRouter,
    VisionRouteResult,
    vision_router,
)
from .generation import ImageGenerator, image_generator
from .image_refs import ImageRefTracker, image_ref_tracker
from .manager import (
    GifSummary,
    ImageSummary,
    build_vision_messages,
    summarize_gif,
    summarize_image,
)
from .result_cache import ImageResultCache, image_result_cache
from .video import VideoUnderstanding, video_understanding

__all__ = [
    "GifSummary",
    "ImageGenerator",
    "ImageRefTracker",
    "ImageResultCache",
    "ImageSummary",
    "VideoUnderstanding",
    "VisionCapabilityInfo",
    "VisionCapabilityRouter",
    "VisionRouteResult",
    "build_vision_messages",
    "image_generator",
    "image_ref_tracker",
    "image_result_cache",
    "summarize_gif",
    "summarize_image",
    "video_understanding",
    "vision_router",
]
