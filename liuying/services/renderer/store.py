"""页面主题目录与主题商店。

负责扫描页面主题目录、发现内置功能（pages/builtin 下的 manifest.json）、
解析主题价格与中文标签，并生成主题商店条目。与 ThemeManager 解耦后，
本模块只接收主题根目录，不感知 Jinja 环境。
"""

from pathlib import Path, PurePosixPath

import orjson as json
from pydantic import BaseModel

from liuying.services.log import logger


class ThemeStoreItem(BaseModel):
    """主题商店条目。"""

    feature: str
    """所属功能键，如 sign"""
    feature_label: str
    """功能的中文标签"""
    theme_name: str
    """主题目录名"""
    theme_label: str
    """主题的中文标签"""
    display_name: str
    """主题的展示名称"""
    price: int
    """主题价格，0 表示免费"""
    page_path: str
    """主题所属的页面路径"""


class ThemeCatalog:
    """页面主题与功能目录，内置页面主题列表与商店条目的缓存。"""

    def __init__(self) -> None:
        """初始化缓存容器。"""
        self._page_themes: dict[str, list[str]] = {}
        self._store_items: list[ThemeStoreItem] | None = None

    def clear_cache(self) -> None:
        """清空全部缓存。"""
        self._page_themes.clear()
        self._store_items = None

    # ---------- 页面主题 ----------

    def list_page_themes(self, page_root: Path, page_path: str) -> list[str]:
        """列出指定页面可用的页面级主题目录名。

        参数:
            page_root: 当前主题的根目录（含 pages/）。
            page_path: 页面路径，如 "pages/builtin/signIn"。

        返回:
            list[str]: 主题目录名列表，目录缺失或为空时返回 ["default"]。
        """
        if cached := self._page_themes.get(page_path):
            return cached
        page_dir = page_root / page_path
        themes = [
            d.name
            for d in page_dir.iterdir()
            if d.is_dir() and (d / "theme.json").exists()
        ] if page_dir.is_dir() else []
        result = sorted(themes) or ["default"]
        self._page_themes[page_path] = result
        return result

    def load_page_theme_json(
        self,
        page_root: Path,
        default_page_root: Path,
        page_path: str,
        theme_name: str,
    ) -> dict | None:
        """加载页面主题的 theme.json，优先当前主题目录，回退默认主题。

        参数:
            page_root: 当前主题的根目录。
            default_page_root: 默认主题的根目录。
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            dict | None: 主题配置字典，缺失或解析失败时返回 None。
        """
        for root in (page_root, default_page_root):
            target = root / page_path / theme_name / "theme.json"
            if not target.exists():
                continue
            try:
                return json.loads(target.read_bytes())
            except (json.JSONDecodeError, OSError):
                logger.warning(f"页面主题配置解析失败: '{target}'")
                return None
        return None

    def get_theme_price(
        self,
        page_root: Path,
        default_page_root: Path,
        page_path: str,
        theme_name: str,
    ) -> int:
        """查询页面主题价格。

        参数:
            page_root: 当前主题的根目录。
            default_page_root: 默认主题的根目录。
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            int: 主题价格，默认主题或未配置时返回 0。
        """
        if theme_name == "default":
            return 0
        data = self.load_page_theme_json(
            page_root, default_page_root, page_path, theme_name
        )
        return data.get("price", 0) if data else 0

    def get_theme_label(
        self,
        page_root: Path,
        default_page_root: Path,
        page_path: str,
        theme_name: str,
    ) -> str:
        """查询页面主题的中文标签。

        参数:
            page_root: 当前主题的根目录。
            default_page_root: 默认主题的根目录。
            page_path: 页面路径。
            theme_name: 主题目录名。

        返回:
            str: 中文标签，未配置时返回主题目录名。
        """
        if theme_name == "default":
            return "默认"
        data = self.load_page_theme_json(
            page_root, default_page_root, page_path, theme_name
        )
        return data.get("label", theme_name) if data else theme_name

    def resolve_theme_name(
        self,
        page_root: Path,
        default_page_root: Path,
        page_path: str,
        label_or_name: str,
    ) -> str | None:
        """把中文标签或英文目录名解析为页面主题目录名。

        参数:
            page_root: 当前主题的根目录。
            default_page_root: 默认主题的根目录。
            page_path: 页面路径。
            label_or_name: 中文标签（如"粉色"）或英文目录名（如"pink"）。

        返回:
            str | None: 匹配的主题目录名，未匹配时返回 None。
        """
        for name in self.list_page_themes(page_root, page_path):
            if name == label_or_name:
                return name
            label = self.get_theme_label(
                page_root, default_page_root, page_path, name
            )
            if label == label_or_name:
                return name
        return None

    # ---------- 功能发现与主题商店 ----------

    def discover_features(self, page_root: Path) -> dict[str, dict[str, str]]:
        """扫描 pages/builtin 下各功能的 manifest.json，返回功能映射。

        参数:
            page_root: 当前主题的根目录。

        返回:
            dict[str, dict[str, str]]: 功能键到 {page_path, label} 的映射。
        """
        builtin_dir = page_root / "pages" / "builtin"
        if not builtin_dir.is_dir():
            return {}

        features: dict[str, dict[str, str]] = {}
        for page_dir in builtin_dir.iterdir():
            if not page_dir.is_dir():
                continue
            manifest_path = page_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_bytes())
            except (json.JSONDecodeError, OSError):
                logger.warning(f"功能清单解析失败: '{manifest_path}'")
                continue
            if feature := manifest.get("feature"):
                features[feature] = {
                    "page_path": f"pages/builtin/{page_dir.name}",
                    "label": manifest.get("feature_label", feature),
                }
        return features

    def resolve_feature_key(
        self, page_root: Path, label_or_key: str
    ) -> str | None:
        """把中文功能标签或英文功能键解析为功能键。

        参数:
            page_root: 当前主题的根目录。
            label_or_key: 中文标签（如"签到"）或英文键（如"sign"）。

        返回:
            str | None: 匹配的功能键，未匹配时返回 None。
        """
        features = self.discover_features(page_root)
        for f_key, info in features.items():
            if f_key == label_or_key or info.get("label") == label_or_key:
                return f_key
        return None

    def get_store_items(
        self, page_root: Path, default_page_root: Path
    ) -> list[ThemeStoreItem]:
        """生成全部可购买的主题商店条目（带缓存）。

        参数:
            page_root: 当前主题的根目录。
            default_page_root: 默认主题的根目录。

        返回:
            list[ThemeStoreItem]: 按功能分组排序的商店条目列表。
        """
        if self._store_items is not None:
            return self._store_items

        items: list[ThemeStoreItem] = []
        for f_key, info in sorted(self.discover_features(page_root).items()):
            page_path = info["page_path"]
            for t_name in self.list_page_themes(page_root, page_path):
                data = self.load_page_theme_json(
                    page_root, default_page_root, page_path, t_name
                )
                display = data.get("name", t_name) if data else t_name
                price = data.get("price", 0) if data else 0
                if data:
                    theme_label = data.get("label", t_name)
                else:
                    theme_label = "默认" if t_name == "default" else t_name
                items.append(ThemeStoreItem(
                    feature=f_key,
                    feature_label=info["label"],
                    theme_name=t_name,
                    theme_label=theme_label,
                    display_name=display,
                    price=price,
                    page_path=page_path,
                ))

        self._store_items = items
        return items


def has_template_suffix(template_name: str) -> bool:
    """判断组件模板名是否已经携带文件后缀。

    参数:
        template_name: 组件模板路径。

    返回:
        bool: 携带后缀时返回 True。
    """
    return bool(PurePosixPath(template_name).suffix)
