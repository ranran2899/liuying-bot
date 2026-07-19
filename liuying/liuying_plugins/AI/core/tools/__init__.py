"""工具集

提供消息提取与网页抓取工具。

联网搜索能力统一通过 liuying.services.LLM 的 WebSearchCapability 提供，
免配置客户端由 liuying/plugins/web_search 插件注册。
"""

from .message_extractor import (
    MessageExtractor,
    message_extractor,
)
from .web_fetch import (
    WebFetchService,
    WebPageContent,
    web_fetch,
)

__all__ = [
    "MessageExtractor",
    "WebFetchService",
    "WebPageContent",
    "message_extractor",
    "web_fetch",
]
