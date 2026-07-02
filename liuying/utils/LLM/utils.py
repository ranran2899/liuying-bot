"""LLM公共工具模块，提供响应解析、错误处理等通用功能"""
from typing import Any


class APIError(Exception):
    """API错误基类"""

    def __init__(self, message: str, code: str = "UNKNOWN", provider: str = ""):
        super().__init__(message)
        self.code = code
        self.provider = provider

    def __str__(self) -> str:
        prefix = f"[{self.provider}]" if self.provider else ""
        if self.code:
            return f"{prefix}{self.code}: {self.args[0]}"
        return str(self.args[0])


class MultiAPIError(Exception):
    """多配置调用失败异常组"""

    def __init__(self, errors: list[tuple[str, Exception]]):
        self.errors = errors
        messages = "; ".join(f"{url}: {err}" for url, err in errors)
        super().__init__(f"所有配置调用失败: {messages}")

    def __str__(self) -> str:
        return self.args[0]


class ResponseParser:
    """API响应解析器"""

    @staticmethod
    def parse_chat_response(
        response: dict[str, Any], provider: str = "openai"
    ) -> tuple[str, str]:
        """解析对话响应

        完整返回思考内容与回复内容两个字段，由调用方决定是否使用思考内容。
        协议层不做拼接决策，保持字段级隔离，避免思维链污染回复内容。

        Args:
            response: API响应数据
            provider: 提供商名称

        Returns:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容

        Raises:
            APIError: 响应解析错误
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("API返回内容为空", "EMPTY_RESPONSE", provider)

        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return "", str(message)

        content = message.get("content", "")
        content = content if isinstance(content, str) else str(content)

        reasoning = message.get("reasoning_content", "")
        reasoning = reasoning if isinstance(reasoning, str) else str(reasoning)

        return reasoning, content

    @staticmethod
    def extract_usage(response: dict[str, Any]) -> dict[str, int]:
        """从响应中提取 token 消耗

        参数:
            response: API 响应数据

        返回:
            包含 prompt_tokens/completion_tokens/total_tokens 的字典，缺失项为 0
        """
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
            "completion_tokens": usage.get("completion_tokens", 0) or 0,
            "total_tokens": usage.get("total_tokens", 0) or 0,
        }

    @staticmethod
    def parse_ernie_response(response: dict[str, Any]) -> str:
        """解析文心一言格式对话响应

        参数:
            response: API响应数据

        返回:
            回复文本内容

        异常:
            APIError: 响应错误
        """
        if response.get("error_code", 0) != 0:
            raise APIError(
                response.get("error_msg", "未知错误"),
                str(response.get("error_code", "UNKNOWN")),
                "ernie",
            )
        return response.get("result", "")

    @staticmethod
    def parse_image_response(response: dict[str, Any]) -> list[str]:
        """解析图像生成响应

        Args:
            response: API响应数据

        Returns:
            图像URL列表
        """
        data = response.get("data", [])
        return [
            item.get("url", "")
            for item in data
            if isinstance(item, dict) and item.get("url")
        ]

    @staticmethod
    def parse_transcription_response(response: dict[str, Any]) -> str:
        """解析语音转文本响应

        Args:
            response: API响应数据

        Returns:
            转录文本
        """
        return response.get("text", "")


class ResponseValidator:
    """响应验证器"""

    @staticmethod
    def check_error(
        response: dict[str, Any] | None, provider: str = "openai"
    ) -> None:
        """检查响应中的错误

        Args:
            response: API响应数据
            provider: 提供商名称

        Raises:
            APIError: API返回错误
        """
        if not response:
            raise APIError("API请求失败: 未收到响应", "NO_RESPONSE", provider)

        match provider:
            case "ernie":
                ResponseValidator._check_ernie_error(response)
            case _:
                ResponseValidator._check_standard_error(response, provider)

    @staticmethod
    def _check_standard_error(
        response: dict[str, Any], provider: str
    ) -> None:
        """检查标准格式错误（OpenAI/智谱等通用格式）

        Args:
            response: 响应数据
            provider: 提供商名称

        Raises:
            APIError: API错误
        """
        if "error" not in response:
            return

        error_info = response["error"]
        match error_info:
            case dict():
                msg = error_info.get("message", "API调用失败")
                code = error_info.get("code", "UNKNOWN")
            case _:
                msg = str(error_info)
                code = "UNKNOWN"
        raise APIError(f"{provider} API错误: {msg}", code, provider)

    @staticmethod
    def _check_ernie_error(response: dict[str, Any]) -> None:
        """检查文心一言格式错误

        Args:
            response: 响应数据

        Raises:
            APIError: API错误
        """
        if response.get("error_code", 0) != 0:
            raise APIError(
                f"ERNIE API错误: {response.get('error_msg', '未知错误')}",
                str(response.get("error_code", "UNKNOWN")),
                "ernie",
            )


def extract_content(
    response: dict[str, Any], key: str = "content", default: str = ""
) -> str:
    """从响应中提取内容

    Args:
        response: 响应字典
        key: 内容键名
        default: 默认值

    Returns:
        提取的内容
    """
    return response.get(key, default) if isinstance(response, dict) else default


def safe_get(
    data: dict[str, Any] | None, *keys: str, default: Any = None
) -> Any:
    """安全获取嵌套字典中的值

    Args:
        data: 数据字典
        *keys: 键路径
        default: 默认值

    Returns:
        获取的值或默认值
    """
    if data is None:
        return default
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result


__all__ = [
    "APIError",
    "MultiAPIError",
    "ResponseParser",
    "ResponseValidator",
    "extract_content",
    "safe_get",
]
