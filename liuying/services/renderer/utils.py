from pathlib import Path
import re
from typing import Any

import orjson as json

from liuying.utils.pydantic_compat import _dump_pydantic_obj

_SKIP_URL_PREFIXES: frozenset[str] = frozenset({
    "data:", "http://", "https://", "file://", "/", "#", "javascript:",
})


def deep_merge_dict(base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """递归地将 new 字典合并到 base 字典中，返回新字典。

    使用深拷贝避免对原始 base 字典的共享引用污染。
    """
    result: dict[str, Any] = {
        k: (v.copy() if isinstance(v, dict) else v) for k, v in base.items()
    }
    for key, value in new.items():
        if (
            isinstance(value, dict)
            and key in result
            and isinstance(result[key], dict)
        ):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def resolve_resource_url(url: str, base_path: Path) -> str | None:
    """解析相对路径资源为绝对URI，返回None表示无需重写。"""
    if any(url.startswith(p) for p in _SKIP_URL_PREFIXES):
        return None
    try:
        resolved = (base_path / url).resolve()
        if resolved.exists():
            return resolved.as_uri()
    except OSError:
        pass
    return None


_CSS_URL_PATTERN = re.compile(r"url\(([^)]+)\)")
_HTML_URL_PATTERN = re.compile(r"(src|href)=([\'\"])([^\'\"]+)\2")


def rewrite_urls(content: str, base_path: Path, is_css: bool = False) -> str:
    """重写CSS或HTML中的相对URL为绝对URI。"""
    if is_css:
        def replace_css(match: re.Match) -> str:
            url = match.group(1).strip("\"'")
            new_url = resolve_resource_url(url, base_path)
            return f'url("{new_url}")' if new_url else match.group(0)
        return _CSS_URL_PATTERN.sub(replace_css, content)

    def replace_html(match: re.Match) -> str:
        attr, quote, url = (
            match.group(1), match.group(2), match.group(3)
        )
        new_url = resolve_resource_url(url, base_path)
        if new_url:
            return f"{attr}={quote}{new_url}{quote}"
        return match.group(0)
    return _HTML_URL_PATTERN.sub(replace_html, content)


def pydantic_tojson_filter(obj: Any) -> str:
    """递归处理Pydantic模型及其集合的 tojson 过滤器。"""
    return json.dumps(
        _dump_pydantic_obj(obj),
        option=json.OPT_ENSURE_ASCII,
    ).decode()
