from pathlib import Path

from liuying.services.log import logger


class AssetRegistry:
    """独立的资源注册表服务，存储由插件动态注册的资源。

    使用实例变量存储注册项，避免可变类变量在多实例间共享状态的反模式。
    """

    def __init__(self):
        self._markdown_styles: dict[str, Path] = {}

    def register_markdown_style(self, name: str, path: Path) -> None:
        """为 Markdown 渲染器注册一个具名样式。

        参数:
            name: 样式的唯一名称
            path: 指向该样式的CSS文件路径
        """
        if name in self._markdown_styles:
            logger.warning(f"Markdown 样式 '{name}' 已被注册，将被覆盖。")
        self._markdown_styles[name] = path
        logger.debug(f"已注册 Markdown 样式 '{name}' -> '{path}'")

    def resolve_markdown_style(self, name: str) -> Path | None:
        """解析已注册的 Markdown 样式。"""
        return self._markdown_styles.get(name)

    def unregister_markdown_style(self, name: str) -> bool:
        """注销已注册的 Markdown 样式，供插件卸载时清理资源。

        返回:
            bool: 是否成功注销
        """
        if name in self._markdown_styles:
            del self._markdown_styles[name]
            logger.debug(f"已注销 Markdown 样式 '{name}'")
            return True
        return False


asset_registry = AssetRegistry()
