"""百度搜索专属数据模型"""
from enum import StrEnum


class BaiduSearchMode(StrEnum):
    """百度搜索模式

    - WEB_SEARCH: 百度搜索，仅返回网页搜索结果
    - CHAT: 智能搜索生成，搜索后使用大模型总结(每日免费 100 次)
    - WEB_SUMMARY: 智能搜索生成高性能版，整合搜索+大模型(每日免费 100 次)
    """

    WEB_SEARCH = "web_search"
    CHAT = "chat"
    WEB_SUMMARY = "web_summary"
