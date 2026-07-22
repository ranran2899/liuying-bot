"""视觉与多媒体配置项

包含图片生成、图片/视频理解、文件发送与缓存等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["VISION_CONFIGS"]

VISION_CONFIGS: list[RegisterConfig] = [
    # ===== 图片生成 =====
    RegisterConfig(
        key="IMAGE",
        value={
            "provider": None,
            "model": "dall-e-3",
        },
        module=MODULE,
        help=(
            "图片生成配置\n"
            " - provider: 供应商\n"
            " - model: 模型名"
        ),
        default_value={"provider": None, "model": "dall-e-3"},
        type=dict,
    ),
    # ===== 多媒体理解 =====
    RegisterConfig(
        key="VISION",
        value={
            "enabled": True,
            "file_send_enabled": True,
            "video_understanding_enabled": True,
            "result_cache_enabled": True,
        },
        module=MODULE,
        help=(
            "多媒体理解配置\n"
            " - enabled: 图片/GIF/视频理解\n"
            " - file_send_enabled: 文件发送\n"
            " - video_understanding_enabled: 视频理解\n"
            " - result_cache_enabled: 结果缓存"
        ),
        default_value={
            "enabled": True,
            "file_send_enabled": True,
            "video_understanding_enabled": True,
            "result_cache_enabled": True,
        },
        type=dict,
    ),
]
"""视觉与多媒体配置项列表"""
