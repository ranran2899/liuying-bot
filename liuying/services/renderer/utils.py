"""渲染器通用工具函数。"""

from pathlib import Path
import re
from typing import Any

import orjson as json

from liuying.utils.pydantic_compat import _dump_pydantic_obj

# 无需重写的 URL 前缀
_SKIP_URL_PREFIXES = frozenset({
    "data:",
    "file://",
    "http://",
    "https://",
    "javascript:",
    "#",
    "/",
})

_CSS_URL_PATTERN = re.compile(r"url\(([^)]+)\)")
_HTML_URL_PATTERN = re.compile(r"(src|href)=(['\"])([^'\"]+)\2")


def deep_merge_dict(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """将 extra 深度合并进 base，返回全新字典，不修改入参。

    参数:
        base: 基础字典，其顶层值为 dict 的项会被浅拷贝。
        extra: 覆盖字典，其中的 dict 值会与 base 同名项递归合并。

    返回:
        dict[str, Any]: 合并后的新字典。
    """
    merged: dict[str, Any] = {
        key: value.copy() if isinstance(value, dict) else value
        for key, value in base.items()
    }
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_resource_url(url: str, base_path: Path) -> str | None:
    """把相对路径资源解析为绝对文件 URI。

    参数:
        url: 资源引用字符串，如 './style.css'。
        base_path: 解析相对路径的基础目录。

    返回:
        str | None: 资源存在时返回绝对文件 URI；
            无需重写（绝对 URL 等）或资源不存在时返回 None。
    """
    if url.startswith(tuple(_SKIP_URL_PREFIXES)):
        return None
    try:
        target = (base_path / url).resolve()
    except OSError:
        return None
    return target.as_uri() if target.exists() else None


def rewrite_urls(content: str, base_path: Path, *, is_css: bool = False) -> str:
    """重写 CSS 或 HTML 内容中的相对资源引用为绝对 URI。

    参数:
        content: 原始 CSS 或 HTML 文本。
        base_path: 解析相对引用的基础目录。
        is_css: 是否按 CSS 的 url(...) 语法解析，否则按 src/href 属性解析。

    返回:
        str: 完成重写后的文本，无法解析的引用保持原样。
    """

    def replace_css(match: re.Match) -> str:
        url = match.group(1).strip("\"'")
        if resolved := resolve_resource_url(url, base_path):
            return f'url("{resolved}")'
        return match.group(0)

    def replace_html(match: re.Match) -> str:
        attr, quote, url = match.group(1), match.group(2), match.group(3)
        if resolved := resolve_resource_url(url, base_path):
            return f"{attr}={quote}{resolved}{quote}"
        return match.group(0)

    pattern = _CSS_URL_PATTERN if is_css else _HTML_URL_PATTERN
    replacer = replace_css if is_css else replace_html
    return pattern.sub(replacer, content)


def pydantic_tojson_filter(obj: Any) -> str:
    """Jinja2 的 tojson 过滤器，递归展开 Pydantic 模型后序列化。

    参数:
        obj: 任意可序列化对象，内部的 Pydantic 模型会被递归展开为字典。

    返回:
        str: JSON 字符串。
    """
    return json.dumps(_dump_pydantic_obj(obj)).decode()
