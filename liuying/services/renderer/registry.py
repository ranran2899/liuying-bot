"""资源注册表，存储由插件运行期动态注册的资源。"""

from pathlib import Path

from liuying.services.log import logger


class AssetRegistry:
    """以实例状态存储注册项的资源注册表，当前仅管理 Markdown 具名样式。"""

    def __init__(self) -> None:
        """初始化空的样式注册表。"""
        self._markdown_styles: dict[str, Path] = {}

    def register_markdown_style(self, name: str, path: Path) -> None:
        """注册一个具名 Markdown 样式，重复注册时覆盖并告警。

        参数:
            name: 样式的唯一名称。
            path: 指向该样式 CSS 文件的路径。
        """
        if name in self._markdown_styles:
            logger.warning(f"Markdown 样式 '{name}' 已被注册，将被覆盖。")
        self._markdown_styles[name] = path
        logger.debug(f"已注册 Markdown 样式 '{name}' -> '{path}'")

    def resolve_markdown_style(self, name: str) -> Path | None:
        """按名称解析已注册的 Markdown 样式路径。

        参数:
            name: 注册时使用的样式名称。

        返回:
            Path | None: 样式文件路径，未注册时返回 None。
        """
        return self._markdown_styles.get(name)

    def unregister_markdown_style(self, name: str) -> bool:
        """注销指定样式，供插件卸载时清理。

        参数:
            name: 注册时使用的样式名称。

        返回:
            bool: 是否成功注销（名称不存在时返回 False）。
        """
        if name not in self._markdown_styles:
            return False
        del self._markdown_styles[name]
        logger.debug(f"已注销 Markdown 样式 '{name}'")
        return True


asset_registry = AssetRegistry()
