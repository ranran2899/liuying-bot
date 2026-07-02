"""视觉与多媒体配置项

包含图片生成、图片/视频理解、文件发送与缓存等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["VISION_CONFIGS"]

VISION_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="IMAGE_PROVIDER",
        value=None,
        module=MODULE,
        help="图片生成供应商",
        default_value=None,
        type=str,
    ),
    RegisterConfig(
        key="IMAGE_MODEL",
        value="dall-e-3",
        module=MODULE,
        help="图片生成模型名",
        default_value="dall-e-3",
        type=str,
    ),
    RegisterConfig(
        key="VISION_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用图片/GIF/视频理解",
        default_value=True,
        type=bool,
    ),
    # ===== Phase12: 其他 =====
    RegisterConfig(
        key="FILE_SEND_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用文件发送",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="VIDEO_UNDERSTANDING_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用视频理解",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="IMAGE_RESULT_CACHE_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用图片结果缓存",
        default_value=True,
        type=bool,
    ),
]
"""视觉与多媒体配置项列表"""
