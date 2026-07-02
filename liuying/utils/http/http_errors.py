"""HTTP请求错误处理模块，提供统一异常层次和错误分类能力。"""

from typing import ClassVar

import httpx

_HTTP_ERROR_KEYWORDS = ("url", "status_code")


class HttpError(Exception):
    """HTTP请求错误基类。

    参数:
        message: 错误信息。
        url: 请求URL。
        status_code: HTTP状态码（非HTTP异常为None）。
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status_code: int | None = None,
    ):
        self.url = url
        self.status_code = status_code
        super().__init__(message)


class HttpConnectionError(HttpError):
    """连接错误（DNS解析失败、连接拒绝、网络不可达等）。"""


class HttpTimeoutError(HttpError):
    """请求超时错误。"""


class HttpClientError(HttpError):
    """客户端错误（4xx）。"""


class HttpServerError(HttpError):
    """服务端错误（5xx）。"""


class HttpRateLimitError(HttpError):
    """限流错误（429）。

    参数:
        message: 错误信息。
        url: 请求URL。
        retry_after: 建议重试等待时间(秒)。
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        retry_after: float | None = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, url, 429)


class ErrorClassifier:
    """错误分类器，根据异常或状态码判断错误类型和可重试性。"""

    _RETRYABLE_STATUS: ClassVar[set[int]] = {
        408, 425, 429, 500, 502, 503, 504,
    }

    _RETRYABLE_EXCEPTIONS: ClassVar[tuple[type[Exception], ...]] = (
        HttpTimeoutError,
        HttpConnectionError,
        HttpServerError,
        HttpRateLimitError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.StreamError,
    )

    _NON_RETRYABLE_EXCEPTIONS: ClassVar[tuple[type[Exception], ...]] = (
        HttpClientError,
    )

    @classmethod
    def classify_exception(cls, exc: Exception) -> type[HttpError]:
        """将任意异常分类为HttpError子类。

        参数:
            exc: 原始异常。

        返回:
            type[HttpError]: 对应的HttpError子类。
        """
        if isinstance(exc, HttpError):
            return exc.__class__
        if isinstance(exc, httpx.TimeoutException):
            return HttpTimeoutError
        if isinstance(exc, httpx.ConnectError | httpx.NetworkError):
            return HttpConnectionError
        if isinstance(exc, httpx.HTTPStatusError):
            return cls.classify_status(exc.response.status_code)
        return HttpError

    @classmethod
    def classify_status(cls, status_code: int) -> type[HttpError]:
        """根据HTTP状态码分类错误类型。

        参数:
            status_code: HTTP状态码。

        返回:
            type[HttpError]: 对应的HttpError子类。
        """
        if status_code == 429:
            return HttpRateLimitError
        if 400 <= status_code < 500:
            return HttpClientError
        if 500 <= status_code < 600:
            return HttpServerError
        return HttpError

    @classmethod
    def is_retryable(cls, exc: Exception) -> bool:
        """判断异常是否可重试。

        参数:
            exc: 异常对象。

        返回:
            bool: 可重试返回True。
        """
        if isinstance(exc, cls._NON_RETRYABLE_EXCEPTIONS):
            return False
        if isinstance(exc, cls._RETRYABLE_EXCEPTIONS):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in cls._RETRYABLE_STATUS
        if isinstance(exc, HttpError) and exc.status_code is not None:
            return exc.status_code in cls._RETRYABLE_STATUS
        return False

    @classmethod
    def to_http_error(
        cls, exc: Exception, url: str | None = None
    ) -> HttpError:
        """将任意异常转换为HttpError实例。

        参数:
            exc: 原始异常。
            url: 请求URL。

        返回:
            HttpError: 转换后的HttpError实例。
        """
        if isinstance(exc, HttpError):
            if url and exc.url is None:
                exc.url = url
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return HttpTimeoutError(str(exc), url)
        if isinstance(exc, httpx.ConnectError):
            return HttpConnectionError(str(exc), url)
        if isinstance(exc, httpx.HTTPStatusError):
            error_cls = cls.classify_status(exc.response.status_code)
            return error_cls(str(exc), url, exc.response.status_code)
        return HttpError(str(exc), url)
