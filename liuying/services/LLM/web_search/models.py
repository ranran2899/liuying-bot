"""网络搜索数据模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class FreshnessType(StrEnum):
    """时间范围类型"""

    NO_LIMIT = "noLimit"
    """无时间限制"""
    ONE_DAY = "oneDay"
    """最近一天"""
    ONE_WEEK = "oneWeek"
    """最近一周"""
    ONE_MONTH = "oneMonth"
    """最近一个月"""
    ONE_YEAR = "oneYear"
    """最近一年"""


class ResourceType(StrEnum):
    """资源类型"""

    WEB = "web"
    """网页"""
    IMAGE = "image"
    """图片"""
    VIDEO = "video"
    """视频"""
    AUDIO = "audio"
    """音频"""



@dataclass(slots=True)
class SearchFilter:
    """搜索过滤条件"""

    include_sites: list[str] = field(default_factory=list)
    exclude_sites: list[str] = field(default_factory=list)
    city: str | None = None


@dataclass(slots=True)
class WebPageResult:
    """网页搜索结果"""

    id: str
    title: str
    url: str
    snippet: str
    summary: str | None = None
    site_name: str | None = None
    site_icon: str | None = None
    published_date: datetime | None = None
    crawled_date: datetime | None = None
    language: str | None = None
    display_url: str | None = None

    @staticmethod
    def _parse_iso_date(date_str: str | None) -> datetime | None:
        """解析ISO格式日期"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_date(
        date_str: str | None, fmt: str = "%Y-%m-%d %H:%M:%S"
    ) -> datetime | None:
        """解析自定义格式日期"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            return None


@dataclass(slots=True)
class ImageResult:
    """图片搜索结果"""

    id: str
    content_url: str
    host_page_url: str
    name: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_url: str | None = None


@dataclass(slots=True)
class SearchRequest:
    """搜索请求

    属性:
        query: 搜索关键词
        count: 返回结果数量
        summary: 是否返回摘要
        freshness: 时间范围
        resource_types: 资源类型列表
        search_filter: 搜索过滤条件
        instruction: 搜索指令（支持指令的引擎可使用）
        chat_model: 聊天模型名称（支持总结的引擎可使用）
        extra: 引擎特定选项字典，各引擎从中读取自身专属参数
    """

    query: str
    count: int = 10
    summary: bool = False
    freshness: FreshnessType = FreshnessType.NO_LIMIT
    resource_types: list[ResourceType] = field(
        default_factory=lambda: [ResourceType.WEB]
    )
    search_filter: SearchFilter | None = None
    instruction: str | None = None
    chat_model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """验证请求参数"""
        if not self.query or not self.query.strip():
            from .exceptions import ValidationError
            raise ValidationError("搜索关键词不能为空", "query")
        if not 1 <= self.count <= 50:
            from .exceptions import ValidationError
            raise ValidationError("返回结果数量必须在1-50之间", "count")


@dataclass(slots=True)
class SearchResponse:
    """搜索响应

    属性:
        query: 搜索关键词
        web_pages: 网页结果列表
        images: 图片结果列表
        total_matches: 总匹配数
        provider: 搜索来源标识
        request_id: 请求ID
        raw_data: 原始响应数据
        summary_text: 大模型总结文本
    """

    query: str
    web_pages: list[WebPageResult] = field(default_factory=list)
    images: list[ImageResult] = field(default_factory=list)
    total_matches: int = 0
    provider: str = ""
    request_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    summary_text: str | None = None
