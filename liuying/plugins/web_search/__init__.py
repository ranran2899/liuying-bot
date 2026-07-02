"""网络搜索免配置客户端插件

提供 Bing HTTP / Wikipedia / SearXNG / DuckDuckGo 四个免配置搜索客户端，
通过 LLM 模块的注册接口自动注册到 WebSearchProvider，作为正式搜索 provider
的降级兜底方案。

本插件为服务型插件，不提供主动触发命令，仅在后台注册搜索客户端。
"""
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType

# 导入客户端模块，触发 @register_search_client 装饰器注册
from . import bing_http, duckduckgo, searxng, wikipedia  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="网络搜索免配置客户端",
    description=(
        "提供 Bing HTTP / Wikipedia / SearXNG / DuckDuckGo 免配置搜索客户端，"
        "作为正式搜索 provider 的降级兜底方案"
    ),
    usage="服务型插件，无需手动调用，自动注册到 LLM 网络搜索模块",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.DEPENDANT,
        menu_type="服务",
        is_show=False,
        configs=[],
    ).to_dict(),
)
