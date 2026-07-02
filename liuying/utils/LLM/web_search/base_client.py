"""网络搜索基础客户端"""
from abc import ABC, abstractmethod
import json
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from liuying.utils.exception import AllURIsFailedError
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from .config import get_search_config
from .exceptions import APIKeyError, NetworkError, RequestError
from .models import SearchRequest, SearchResponse

if TYPE_CHECKING:
    from .registry import SearchClientMeta


class BaseSearchClient(ABC):
    """搜索客户端基类

    子类通过 register_search_client 装饰器注册后，
    client_meta 类属性自动设置为对应的 SearchClientMeta。
    """

    client_meta: ClassVar["SearchClientMeta | None"] = None
    """客户端元数据，由 register_search_client 装饰器设置"""

    def __init__(self, provider_name: str):
        """初始化搜索客户端

        Args:
            provider_name: 提供商名称
        """
        self._provider_name = provider_name
        self._config = get_search_config()

    @property
    def provider_name(self) -> str:
        """获取提供商名称"""
        return self._provider_name

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行搜索

        Args:
            request: 搜索请求对象

        Returns:
            搜索响应对象
        """
        ...

    def _get_api_key(self) -> str:
        """获取API密钥

        Returns:
            API密钥字符串

        Raises:
            APIKeyError: API密钥未配置
        """
        api_key = self._config.get_api_key(self._provider_name)
        if not api_key:
            raise APIKeyError(self._provider_name)
        return api_key

    def _get_base_url(self) -> str:
        """获取API基础URL

        Returns:
            API基础URL
        """
        return self._config.get_base_url(self._provider_name)

    async def _request(
        self,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """发送搜索请求

        Args:
            url: 请求URL
            headers: 请求头
            data: 请求数据
            timeout: 超时时间

        Returns:
            响应数据

        Raises:
            NetworkError: 网络错误
            RequestError: 请求错误
        """
        try:
            response = await AsyncHttpx.post(
                url=url,
                json=data,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            text = response.text
            try:
                result = json.loads(text)
            except json.JSONDecodeError as e:
                logger.error(
                    f"[{self._provider_name}] 响应不是有效JSON: {e}, "
                    f"状态码={response.status_code}, "
                    f"原始响应={text[:500]}"
                )
                raise RequestError(
                    self._provider_name,
                    f"响应不是有效JSON: {e}",
                    status_code=response.status_code,
                    response_data={"raw": text[:500]},
                ) from e
            if not isinstance(result, dict):
                raise RequestError(
                    self._provider_name,
                    f"响应格式错误: {type(result)}",
                )
            return result
        except AllURIsFailedError as e:
            last_exc = e.exceptions[-1] if e.exceptions else None
            if isinstance(last_exc, httpx.HTTPStatusError):
                response = last_exc.response
                logger.error(
                    f"[{self._provider_name}] HTTP错误: "
                    f"状态码={response.status_code}, "
                    f"URL={url}, "
                    f"响应={response.text[:500]}"
                )
                raise RequestError(
                    self._provider_name,
                    f"HTTP {response.status_code} 错误: {last_exc}",
                    status_code=response.status_code,
                    response_data={"raw": response.text[:500]},
                ) from e
            logger.error(
                f"[{self._provider_name}] 所有URL请求失败: {e}, "
                f"异常类型={[type(x).__name__ for x in e.exceptions]}"
            )
            raise NetworkError(self._provider_name, e) from e
        except APIKeyError:
            raise
        except RequestError:
            raise
        except Exception as e:
            logger.error(
                f"[{self._provider_name}] 网络请求异常: {type(e).__name__}: {e}, "
                f"URL={url}"
            )
            raise NetworkError(self._provider_name, e) from e
