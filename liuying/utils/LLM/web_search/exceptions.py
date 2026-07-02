"""网络搜索工具包异常定义"""


class SearchError(Exception):
    """搜索异常基类"""

    __slots__ = ("message", "provider")

    def __init__(self, message: str, provider: str | None = None):
        self.message = message
        self.provider = provider
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.provider}] {self.message}" if self.provider else self.message


class APIKeyError(SearchError):
    """API密钥错误"""

    def __init__(self, provider: str, message: str = "API密钥未配置或无效"):
        super().__init__(message, provider)


class RequestError(SearchError):
    """请求错误"""

    __slots__ = ("response_data", "status_code")

    def __init__(
        self,
        provider: str,
        message: str,
        status_code: int | None = None,
        response_data: dict | None = None,
    ):
        self.status_code = status_code
        self.response_data = response_data or {}
        super().__init__(message, provider)


class ValidationError(SearchError):
    """参数验证错误"""

    __slots__ = ("field",)

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)


class RateLimitError(SearchError):
    """速率限制错误"""

    __slots__ = ("retry_after",)

    def __init__(self, provider: str, retry_after: int | None = None):
        self.retry_after = retry_after
        message = "请求频率超限"
        if retry_after:
            message += f"，请 {retry_after} 秒后重试"
        super().__init__(message, provider)


class NetworkError(SearchError):
    """网络连接错误"""

    __slots__ = ("original_error",)

    def __init__(self, provider: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__("网络连接失败", provider)
