"""网络搜索数据模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .exceptions import ValidationError


class SearchProvider(StrEnum):
    """搜索引擎提供商"""

    BOCHA = "bocha"
    BAIDU = "baidu"
    FREE = "free"
    """免配置搜索客户端通用标识"""


class BaiduSearchMode(StrEnum):
    """百度搜索模式

    - WEB_SEARCH: 百度搜索，仅返回网页搜索结果
    - CHAT: 智能搜索生成，搜索后使用大模型总结(每日免费 100 次)
    - WEB_SUMMARY: 智能搜索生成高性能版，整合搜索+大模型(每日免费 100 次)
    """

    WEB_SEARCH = "web_search"
    CHAT = "chat"
    WEB_SUMMARY = "web_summary"


class FreshnessType(StrEnum):
    """时间范围类型"""

    NO_LIMIT = "noLimit"
    ONE_DAY = "oneDay"
    ONE_WEEK = "oneWeek"
    ONE_MONTH = "oneMonth"
    ONE_YEAR = "oneYear"


class ResourceType(StrEnum):
    """资源类型"""

    WEB = "web"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(slots=True)
class SearchFilter:
    """搜索过滤条件"""

    include_sites: list[str] = field(default_factory=list)
    exclude_sites: list[str] = field(default_factory=list)
    city: str | None = None

    def to_bocha_params(self) -> dict[str, Any]:
        """转换为博查API参数"""
        params: dict[str, Any] = {}
        if self.include_sites:
            params["include"] = "|".join(self.include_sites)
        if self.exclude_sites:
            params["exclude"] = "|".join(self.exclude_sites)
        return params

    def to_baidu_params(self) -> dict[str, Any]:
        """转换为百度API参数"""
        params: dict[str, Any] = {}
        if self.include_sites:
            params["match"] = {"site": self.include_sites}
        if self.city:
            params["geo"] = {"city": [self.city]}
        return params


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

    @classmethod
    def from_bocha(cls, data: dict[str, Any]) -> "WebPageResult":
        """从博查API响应创建实例"""
        return cls(
            id=data.get("id", ""),
            title=data.get("name", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet", ""),
            summary=data.get("summary"),
            site_name=data.get("siteName"),
            site_icon=data.get("siteIcon"),
            published_date=cls._parse_iso_date(data.get("datePublished")),
            crawled_date=cls._parse_iso_date(data.get("dateLastCrawled")),
            language=data.get("language"),
            display_url=data.get("displayUrl"),
        )

    @classmethod
    def from_baidu(cls, data: dict[str, Any]) -> "WebPageResult":
        """从百度API响应创建实例"""
        return cls(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("content", ""),
            summary=None,
            site_name=None,
            site_icon=data.get("icon"),
            published_date=cls._parse_baidu_date(data.get("date")),
            language=None,
            display_url=None,
        )

    @classmethod
    def from_baidu_v2(cls, data: dict[str, Any]) -> "WebPageResult":
        """从百度千帆 v2 AI 搜索响应创建实例

        适用于 web_search/chat/web_summary 三种模式的 references 字段。

        Args:
            data: 单条 reference 数据

        Returns:
            WebPageResult 实例
        """
        return cls(
            id=str(data.get("id", "")),
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet") or data.get("content", ""),
            summary=data.get("content"),
            site_name=data.get("website") or data.get("web_anchor"),
            site_icon=data.get("icon"),
            published_date=cls._parse_iso_date(data.get("date"))
            or cls._parse_baidu_date(data.get("date")),
            language=None,
            display_url=None,
        )

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
    def _parse_baidu_date(date_str: str | None) -> datetime | None:
        """解析百度格式日期"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
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

    @classmethod
    def from_bocha(cls, data: dict[str, Any]) -> "ImageResult":
        """从博查API响应创建实例"""
        return cls(
            id=data.get("imageId", ""),
            content_url=data.get("contentUrl", ""),
            host_page_url=data.get("hostPageUrl", ""),
            name=data.get("name"),
            width=data.get("width"),
            height=data.get("height"),
            thumbnail_url=data.get("thumbnailUrl"),
        )


@dataclass(slots=True)
class SearchRequest:
    """搜索请求"""

    query: str
    count: int = 10
    summary: bool = False
    freshness: FreshnessType = FreshnessType.NO_LIMIT
    resource_types: list[ResourceType] = field(
        default_factory=lambda: [ResourceType.WEB]
    )
    search_filter: SearchFilter | None = None
    baidu_mode: BaiduSearchMode = BaiduSearchMode.WEB_SEARCH
    instruction: str | None = None
    chat_model: str | None = None

    def validate(self) -> None:
        """验证请求参数"""
        if not self.query or not self.query.strip():
            raise ValidationError("搜索关键词不能为空", "query")
        if not 1 <= self.count <= 50:
            raise ValidationError("返回结果数量必须在1-50之间", "count")


@dataclass(slots=True)
class SearchResponse:
    """搜索响应

    Attributes:
        query: 搜索关键词
        web_pages: 网页结果列表
        images: 图片结果列表
        total_matches: 总匹配数
        provider: 搜索来源标识，可为 SearchProvider 枚举或自定义字符串
        request_id: 请求ID
        raw_data: 原始响应数据
        summary_text: 大模型总结文本
        baidu_mode: 百度搜索模式
    """

    query: str
    web_pages: list[WebPageResult] = field(default_factory=list)
    images: list[ImageResult] = field(default_factory=list)
    total_matches: int = 0
    provider: str = SearchProvider.BOCHA
    request_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)
    summary_text: str | None = None
    baidu_mode: BaiduSearchMode | None = None
