"""截图引擎实现。

当前基于 nonebot-plugin-htmlrender (Playwright)，通过 ScreenshotEngine
协议与上层渲染服务解耦，未来可替换为其他后端。
"""

from pathlib import Path
from typing import Any

from nonebot_plugin_htmlrender import html_to_pic

from liuying.services.renderer.core.protocols import ScreenshotEngine

# 默认视口：宽度固定，高度由内容自动撑开
DEFAULT_VIEWPORT: dict[str, int] = {"width": 800, "height": 10}


def file_base_uri(path: Path) -> str:
    """把目录路径转换为以 / 结尾的 file URI。

    同步辅助函数，供协程调用以避免在事件循环内执行 pathlib 阻塞方法。

    参数:
        path: 基础目录路径。

    返回:
        str: 以 / 结尾的 file URI 字符串。
    """
    return path.absolute().as_uri().rstrip("/") + "/"


class PlaywrightEngine(ScreenshotEngine):
    """基于 nonebot-plugin-htmlrender 的截图引擎实现。"""

    async def render(
        self, html: str, base_url_path: Path, **render_options: Any
    ) -> bytes:
        """将 HTML 字符串截图为图片字节。

        参数:
            html: 要渲染的完整 HTML 内容。
            base_url_path: 解析相对路径资源的基础目录。
            **render_options: 传递给 html_to_pic 的额外选项
                （如 viewport、wait、type 等）。

        返回:
            bytes: 渲染后的 PNG 图片字节数据。
        """
        options: dict[str, Any] = {
            "viewport": dict(DEFAULT_VIEWPORT),
            **render_options,
            "base_url": file_base_uri(base_url_path),
        }
        return await html_to_pic(html=html, **options)


def get_screenshot_engine() -> PlaywrightEngine:
    """截图引擎工厂函数。

    返回:
        PlaywrightEngine: 新建的截图引擎实例。
    """
    return PlaywrightEngine()
