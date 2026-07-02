"""网络搜索客户端注册表

提供标准化的搜索客户端注册机制，允许其他开发者将自定义搜索实现
注册到 LLM 模块。通过装饰器自动注册，支持元数据声明、自动类型推断
与免配置客户端发现。

使用方式:
    from liuying.utils.LLM.web_search.registry import (
        SearchClientMeta,
        register_search_client,
    )

    @register_search_client(SearchClientMeta(
        name="my_engine",
        display_name="我的搜索引擎",
        description="自定义搜索实现",
        requires_api_key=True,
        keywords=("my_engine", "myengine"),
    ))
    class MyClient(BaseSearchClient):
        ...
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base_client import BaseSearchClient


@dataclass(slots=True, frozen=True)
class SearchClientMeta:
    """搜索客户端元数据

    声明客户端的标识、展示信息、配置要求与识别规则。

    Attributes:
        name: 客户端类型标识符（如 baidu/bocha/bing_http）
        display_name: 展示名称
        description: 描述
        default_base_url: 默认基础URL
        requires_api_key: 是否需要API密钥
        free: 是否免配置（无需API密钥即可使用）
        keywords: 识别关键词，用于从 provider name/base_url 自动推断客户端类型
        priority: 免配置客户端优先级（数值越小优先级越高，用于降级顺序）
    """

    name: str
    display_name: str
    description: str
    default_base_url: str = ""
    requires_api_key: bool = True
    free: bool = False
    keywords: tuple[str, ...] = ()
    priority: int = 0


_SEARCH_CLIENT_REGISTRY: dict[str, type["BaseSearchClient"]] = {}
_SEARCH_CLIENT_META: dict[str, SearchClientMeta] = {}


def register_search_client(
    meta: SearchClientMeta,
) -> Callable[[type["BaseSearchClient"]], type["BaseSearchClient"]]:
    """搜索客户端注册装饰器

    将 BaseSearchClient 子类注册到全局注册表，同时设置类属性 client_meta。

    参数:
        meta: 客户端元数据

    返回:
        装饰器函数
    """

    def wrapper(
        cls: type["BaseSearchClient"],
    ) -> type["BaseSearchClient"]:
        _SEARCH_CLIENT_REGISTRY[meta.name] = cls
        _SEARCH_CLIENT_META[meta.name] = meta
        cls.client_meta = meta
        return cls

    return wrapper


def get_search_client_class(
    name: str,
) -> type["BaseSearchClient"] | None:
    """获取已注册的搜索客户端类

    参数:
        name: 客户端类型标识符

    返回:
        客户端类，未注册返回 None
    """
    return _SEARCH_CLIENT_REGISTRY.get(name)


def get_search_client_meta(name: str) -> SearchClientMeta | None:
    """获取客户端元数据

    参数:
        name: 客户端类型标识符

    返回:
        元数据对象，不存在返回 None
    """
    return _SEARCH_CLIENT_META.get(name)


def get_registered_search_clients() -> dict[str, SearchClientMeta]:
    """获取所有已注册的搜索客户端元数据

    返回:
        客户端名到元数据的映射
    """
    return dict(_SEARCH_CLIENT_META)


def get_free_search_clients() -> list[tuple[str, SearchClientMeta]]:
    """获取所有免配置搜索客户端（按优先级排序）

    返回:
        (客户端名, 元数据) 列表，按 priority 升序
    """
    items = [
        (name, meta)
        for name, meta in _SEARCH_CLIENT_META.items()
        if meta.free
    ]
    items.sort(key=lambda x: x[1].priority)
    return items


def detect_client_type(name: str, base_url: str = "") -> str | None:
    """根据 provider 名称和 base_url 自动推断客户端类型

    遍历注册表中的元数据，匹配 keywords 识别规则。

    参数:
        name: provider 名称
        base_url: API 基础地址

    返回:
        客户端类型标识符，无法识别返回 None
    """
    name_lower = name.lower()
    base_lower = base_url.lower()
    for client_name, meta in _SEARCH_CLIENT_META.items():
        for kw in meta.keywords:
            if kw in name_lower or kw in base_lower:
                return client_name
    return None


__all__ = [
    "SearchClientMeta",
    "detect_client_type",
    "get_free_search_clients",
    "get_registered_search_clients",
    "get_search_client_class",
    "get_search_client_meta",
    "register_search_client",
]
