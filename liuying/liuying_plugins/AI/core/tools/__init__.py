"""工具集

提供消息提取与网页抓取工具。

联网搜索能力统一通过 liuying.utils.LLM 的 WebSearchCapability 提供，
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

# 向后兼容别名：散落函数名指向 MessageExtractor 静态方法
extract_image_segments = MessageExtractor.extract_image_segments
extract_message_text = MessageExtractor.extract_message_text
fetch_image_bytes = MessageExtractor.fetch_image_bytes

__all__ = [
    "MessageExtractor",
    "WebFetchService",
    "WebPageContent",
    "extract_image_segments",
    "extract_message_text",
    "fetch_image_bytes",
    "message_extractor",
    "web_fetch",
]
