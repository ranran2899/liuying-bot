from pathlib import Path
from typing import Any

from nonebot_plugin_htmlrender import html_to_pic

from .protocols import ScreenshotEngine


class PlaywrightEngine(ScreenshotEngine):
    """使用 nonebot-plugin-htmlrender 实现的截图引擎。"""

    async def render(
        self, html: str, base_url_path: Path, **render_options: Any
    ) -> bytes:
        """将HTML字符串截图为图片。

        参数:
            html: 要渲染的HTML内容
            base_url_path: 用于解析相对路径的基础URL路径
            **render_options: 传递给底层截图库的额外选项

        返回:
            bytes: 渲染后的图片字节数据
        """
        base_url = base_url_path.absolute().as_uri()
        if not base_url.endswith("/"):
            base_url += "/"

        final_options: dict[str, Any] = {
            "viewport": {"width": 800, "height": 10},
            **render_options,
            "base_url": base_url,
        }

        return await html_to_pic(html=html, **final_options)


def get_screenshot_engine() -> PlaywrightEngine:
    """截图引擎工厂函数，当前返回 PlaywrightEngine。"""
    return PlaywrightEngine()
