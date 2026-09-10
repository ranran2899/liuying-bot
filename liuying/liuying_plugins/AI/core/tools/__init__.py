"""工具集

提供消息提取、网页抓取与JSON提取等纯函数工具。

联网搜索能力统一通过 liuying.services.LLM 的 WebSearchCapability 提供，
免配置客户端由 liuying/plugins/web_search 插件注册。
"""

from .json_utils import extract_json_payload
from .message_extractor import MessageExtractor
from .web_fetch import (
    WebFetchService,
    WebPageContent,
    web_fetch,
)

__all__ = [
    "MessageExtractor",
    "WebFetchService",
    "WebPageContent",
    "extract_json_payload",
    "web_fetch",
]
