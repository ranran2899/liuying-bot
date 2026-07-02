"""工具集

提供消息提取、目标推断、网页抓取、
搜索排序、网页关联验证、插件命令调用等工具。

联网搜索能力统一通过 liuying.utils.LLM 的 WebSearchCapability 提供，
免配置客户端由 liuying/plugins/web_search 插件注册。
"""

from .message_extractor import (
    extract_image_segments,
    extract_message_text,
    fetch_image_bytes,
)
from .plugin_invoker import PluginInvoker, plugin_invoker
from .search_ranker import SearchRanker, search_ranker
from .target_inference import (
    TARGET_BOT,
    TARGET_OTHERS,
    TARGET_UNCLEAR,
    infer_message_target,
)
from .web_fetch import (
    WebFetchService,
    WebPageContent,
    web_fetch,
)
from .web_grounding import WebGrounding, web_grounding

__all__ = [
    "TARGET_BOT",
    "TARGET_OTHERS",
    "TARGET_UNCLEAR",
    "PluginInvoker",
    "SearchRanker",
    "WebFetchService",
    "WebGrounding",
    "WebPageContent",
    "extract_image_segments",
    "extract_message_text",
    "fetch_image_bytes",
    "infer_message_target",
    "plugin_invoker",
    "search_ranker",
    "web_fetch",
    "web_grounding",
]
