"""视觉与多媒体配置项

包含图片生成与图片/视频/文件理解等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["VISION_CONFIGS"]

VISION_CONFIGS: list[RegisterConfig] = [
    # ===== 图片生成 =====
    cfg(
        "IMAGE",
        {"provider": None, "model": "dall-e-3"},
        "图片生成配置\n - provider: 供应商\n - model: 模型名",
        dict,
    ),
    # ===== 多媒体理解 =====
    cfg(
        "VISION",
        {
            "enabled": True,
            "file_send_enabled": True,
            "video_understanding_enabled": True,
            "result_cache_enabled": True,
        },
        "多媒体理解配置\n"
        " - enabled: 图片/GIF/视频理解\n"
        " - file_send_enabled: 文件发送\n"
        " - video_understanding_enabled: 视频理解\n"
        " - result_cache_enabled: 结果缓存",
        dict,
    ),
]
"""视觉与多媒体配置项列表"""
