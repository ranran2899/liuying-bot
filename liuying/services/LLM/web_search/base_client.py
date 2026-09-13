"""网络搜索基础客户端"""
from abc import ABC, abstractmethod
import json
from typing import TYPE_CHECKING, Any, ClassVar

import httpx

from liuying.utils.exception import AllURIsFailedError
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from .exceptions import APIKeyError, NetworkError, RequestError
from .models import SearchRequest, SearchResponse

if TYPE_CHECKING:
    from .registry import SearchClientMeta


class BaseSearchClient(ABC):
    """搜索客户端基类

    子类通过 register_search_client 装饰器注册后，
    client_meta 类属性自动设置为对应的 SearchClientMeta。

    子类需自行实现 _get_api_key() 和 _get_base_url()，
    从各自的配置系统读取密钥与地址。
    """

    client_meta: ClassVar["SearchClientMeta | None"] = None
    """客户端元数据，由 register_search_client 装饰器设置"""

    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """执行搜索"""
        ...

    def _get_api_key(self) -> str:
        """获取 API 密钥，子类应覆盖此方法从自身配置系统读取

        Raises:
            APIKeyError: API密钥未配置
        """
        raise APIKeyError(self._provider_name)

    def _get_base_url(self) -> str:
        """获取基础 URL，子类应覆盖此方法从自身配置系统读取"""
        if self.client_meta:
            return self.client_meta.default_base_url
        return ""

    async def _request(
        self,
        url: str,
        headers: dict[str, str],
        data: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """发送搜索请求"""
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
