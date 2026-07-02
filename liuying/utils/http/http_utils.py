"""异步HTTP客户端工具模块，基于httpx提供高性能网络请求能力。"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any, ClassVar

import aiofiles
import httpx
from httpx import AsyncClient, AsyncHTTPTransport, HTTPStatusError, Proxy, Response
import orjson as json
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)

from liuying.utils.exception import AllURIsFailedError
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.user_agent import get_user_agent

from .http_cache import ResponseCache, response_cache
from .http_retry import _SENTINEL, Retry

_LOG_TAG = "HTTPClient"
_FALLBACK_TAG = "AsyncHttpx:FallbackExecutor"


class HttpClientManager:
    """全局HTTP客户端管理器，封装客户端生命周期与代理工厂。"""

    _client: AsyncClient | None = None

    @classmethod
    def _build_proxy_mounts(
        cls, proxy_url: str, transport: AsyncHTTPTransport
    ) -> httpx.AsyncClient:
        """构建带代理的httpx客户端，统一处理mounts配置。

        参数:
            proxy_url: 代理URL，同时用于http和https。
            transport: HTTP传输层。

        返回:
            配置好代理的AsyncClient实例。
        """
        return httpx.AsyncClient(
            mounts={
                "http://": AsyncHTTPTransport(proxy=Proxy(proxy_url)),
                "https://": AsyncHTTPTransport(proxy=Proxy(proxy_url)),
            },
            transport=transport,
        )

    @classmethod
    def _build_proxies_mounts(
        cls, proxies: dict[str, str], transport: AsyncHTTPTransport
    ) -> httpx.AsyncClient:
        """构建带多代理的httpx客户端，分别处理http和https。

        参数:
            proxies: 代理字典，键为协议前缀。
            transport: HTTP传输层。

        返回:
            配置好代理的AsyncClient实例。
        """
        http_proxy = proxies.get("http://")
        https_proxy = proxies.get("https://")
        return httpx.AsyncClient(
            mounts={
                "http://": AsyncHTTPTransport(
                    proxy=Proxy(http_proxy) if http_proxy else None
                ),
                "https://": AsyncHTTPTransport(
                    proxy=Proxy(https_proxy) if https_proxy else None
                ),
            },
            transport=transport,
        )

    @classmethod
    async def init(cls) -> None:
        """在Bot启动时初始化全局httpx客户端。"""
        cls._client = httpx.AsyncClient(
            headers=get_user_agent(),
            follow_redirects=True,
        )
        logger.info("全局 httpx.AsyncClient 已启动。", _LOG_TAG)

    @classmethod
    async def close(cls) -> None:
        """在Bot关闭时关闭全局httpx客户端。"""
        if cls._client:
            await cls._client.aclose()
            logger.info("全局 httpx.AsyncClient 已关闭。", _LOG_TAG)

    @classmethod
    def get_client(cls) -> AsyncClient:
        """获取全局 httpx.AsyncClient 实例。

        返回:
            AsyncClient: 全局HTTP客户端实例。

        异常:
            RuntimeError: 客户端未初始化且不在测试环境中。
        """
        if not cls._client:
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                raise RuntimeError(
                    "全局 httpx.AsyncClient 未初始化，请检查启动流程。"
                )
            logger.warning("在测试环境中创建临时HTTP客户端", _LOG_TAG)
            cls._client = httpx.AsyncClient(
                headers=get_user_agent(),
                follow_redirects=True,
            )
        return cls._client

    @classmethod
    def get_async_client(
        cls,
        proxies: dict[str, str] | None = None,
        proxy: str | None = None,
        verify: bool = False,
        **kwargs,
    ) -> httpx.AsyncClient:
        """创建 httpx.AsyncClient 实例的工厂函数。

        参数:
            proxies: 多代理配置字典。
            proxy: 单代理URL，同时用于http和https。
            verify: 是否验证SSL证书。
            **kwargs: 传递给AsyncClient的额外参数。

        返回:
            AsyncClient: 新创建的HTTP客户端实例。
        """
        transport = kwargs.pop("transport", None) or AsyncHTTPTransport(
            verify=verify
        )
        match (proxies, proxy):
            case (dict(), _):
                return cls._build_proxies_mounts(proxies, transport)
            case (_, str()):
                return cls._build_proxy_mounts(proxy, transport)
            case _:
                return httpx.AsyncClient(transport=transport, **kwargs)


@PriorityLifecycle.on_startup(priority=0)
async def _init_global_client():
    """启动钩子：初始化全局HTTP客户端。"""
    await HttpClientManager.init()


@PriorityLifecycle.on_shutdown(priority=1)
async def _close_global_client():
    """关闭钩子：关闭全局HTTP客户端。"""
    await HttpClientManager.close()


class AsyncHttpx:
    """高性能异步HTTP客户端工具类。

    特性:
        - 全局共享连接池，提升性能
        - 支持临时客户端配置（代理、超时等）
        - 内置重试机制和多URL回退
        - 提供JSON解析和文件下载功能
    """

    CLIENT_KEY: ClassVar[frozenset[str]] = frozenset(
        {"use_proxy", "proxies", "proxy", "verify"}
    )

    default_proxy: ClassVar[dict[str, str] | None] = None

    @classmethod
    def _prepare_temporary_client_config(cls, client_kwargs: dict) -> dict:
        """处理旧式客户端kwargs，转换为get_async_client可用配置。

        参数:
            client_kwargs: 原始客户端配置字典。

        返回:
            dict: 处理后的客户端配置。
        """
        final_config = client_kwargs.copy()
        use_proxy = final_config.pop("use_proxy", True)
        if "proxies" not in final_config and "proxy" not in final_config:
            final_config["proxies"] = cls.default_proxy if use_proxy else None
        return final_config

    @classmethod
    def _split_kwargs(cls, kwargs: dict) -> tuple[dict, dict]:
        """分离客户端配置和请求参数。

        参数:
            kwargs: 混合参数字典。

        返回:
            tuple[dict, dict]: (客户端配置, 请求参数)。
        """
        client_kwargs = {}
        request_kwargs = {}
        for k, v in kwargs.items():
            target = client_kwargs if k in cls.CLIENT_KEY else request_kwargs
            target[k] = v
        return client_kwargs, request_kwargs

    @classmethod
    @asynccontextmanager
    async def _get_active_client_context(
        cls, client: AsyncClient | None = None, **kwargs
    ) -> AsyncGenerator[AsyncClient, None]:
        """根据kwargs决定并提供一个活动的HTTP客户端。

        参数:
            client: 可选的已有客户端实例。
            **kwargs: 客户端配置参数，非空时创建临时客户端。

        返回:
            AsyncGenerator[AsyncClient, None]: 活动的HTTP客户端。
        """
        if kwargs:
            logger.debug(f"为单次请求创建临时客户端，配置: {kwargs}")
            temp_config = cls._prepare_temporary_client_config(kwargs)
            async with HttpClientManager.get_async_client(
                **temp_config
            ) as temp_client:
                yield temp_client
        else:
            yield client or HttpClientManager.get_client()

    @Retry.simple(log_name="内部HTTP请求")
    async def _execute_request_inner(
        self, client: AsyncClient, method: str, url: str, **kwargs
    ) -> Response:
        """执行单次HTTP请求的核心方法，被重试装饰器包裹。

        参数:
            client: HTTP客户端实例。
            method: HTTP方法。
            url: 请求URL。
            **kwargs: 请求参数。

        返回:
            Response: HTTP响应对象。
        """
        return await client.request(method, url, **kwargs)

    @classmethod
    async def _single_request(
        cls, method: str, url: str, *, client: AsyncClient | None = None, **kwargs
    ) -> Response:
        """执行单次HTTP请求，内置默认重试逻辑。

        参数:
            method: HTTP方法。
            url: 请求URL。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数和客户端配置。

        返回:
            Response: HTTP响应对象。
        """
        client_kwargs, request_kwargs = cls._split_kwargs(kwargs)
        async with cls._get_active_client_context(
            client=client, **client_kwargs
        ) as active_client:
            response = await cls()._execute_request_inner(
                active_client, method, url, **request_kwargs
            )
            response.raise_for_status()
            return response

    @classmethod
    async def _execute_with_fallbacks(
        cls,
        urls: str | list[str],
        worker: Callable[..., Awaitable[Any]],
        *,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Any:
        """通用执行器，按顺序尝试多个URL直到成功。

        参数:
            urls: 单个URL或URL列表。
            worker: 接受URL和kwargs的协程函数。
            client: 可选的HTTP客户端。
            **kwargs: 传递给worker的额外参数。

        返回:
            Any: worker的返回值。

        异常:
            AllURIsFailedError: 所有URL都请求失败时抛出。
        """
        url_list = [urls] if isinstance(urls, str) else urls
        exceptions: list[Exception] = []

        for i, url in enumerate(url_list):
            try:
                result = await worker(url, client=client, **kwargs)
                if i > 0:
                    logger.info(
                        f"成功从镜像 '{url}' 获取资源 "
                        f"(在尝试了 {i} 个失败的镜像之后)。",
                        _FALLBACK_TAG,
                    )
                return result
            except Exception as e:
                exceptions.append(e)
                if url != url_list[-1]:
                    logger.warning(
                        f"Worker '{worker.__name__}' on {url} failed, "
                        f"trying next. Error: {e.__class__.__name__}",
                        _FALLBACK_TAG,
                    )

        raise AllURIsFailedError(url_list, exceptions)

    @classmethod
    async def _json_request_with_fallback(
        cls,
        method: str,
        url: str | list[str],
        *,
        log_label: str,
        default: Any = None,
        raise_on_failure: bool = False,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Any:
        """JSON请求的通用回退执行器，消除get_json/post_json的重复逻辑。

        参数:
            method: HTTP方法。
            url: 单个URL或URL列表。
            log_label: 日志标识。
            default: 失败时的默认返回值。
            raise_on_failure: 失败时是否抛出异常。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Any: 解析后的JSON数据或默认值。
        """

        async def worker(current_url: str, **worker_kwargs):
            logger.debug(
                f"开始{log_label}: {current_url}", f"AsyncHttpx:{log_label}"
            )
            return await cls._request_and_parse_json(
                method, current_url, **worker_kwargs
            )

        try:
            result = await cls._execute_with_fallbacks(
                url, worker, client=client, **kwargs
            )
            return default if result is _SENTINEL else result
        except AllURIsFailedError as e:
            logger.error(
                f"所有URL的{log_label}均失败: {e}", f"AsyncHttpx:{log_label}"
            )
            if raise_on_failure:
                raise
            return default

    @classmethod
    async def get(
        cls,
        url: str | list[str],
        *,
        follow_redirects: bool = True,
        check_status_code: int | None = None,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Response:
        """发送GET请求，返回第一个成功的响应。

        参数:
            url: 单个URL或URL列表。
            follow_redirects: 是否跟随重定向。
            check_status_code: 检查的期望状态码。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数和客户端配置。

        返回:
            Response: HTTP响应对象。

        异常:
            AllURIsFailedError: 所有URL都请求失败时抛出。
        """

        async def worker(current_url: str, **worker_kwargs) -> Response:
            logger.info(f"开始获取 {current_url}..", "AsyncHttpx:get")
            response = await cls._single_request(
                "GET",
                current_url,
                follow_redirects=follow_redirects,
                **worker_kwargs,
            )
            if check_status_code and response.status_code != check_status_code:
                raise HTTPStatusError(
                    f"状态码错误: {response.status_code}!={check_status_code}",
                    request=response.request,
                    response=response,
                )
            return response

        return await cls._execute_with_fallbacks(url, worker, client=client, **kwargs)

    @classmethod
    async def head(
        cls, url: str | list[str], *, client: AsyncClient | None = None, **kwargs
    ) -> Response:
        """发送HEAD请求，返回第一个成功的响应。

        参数:
            url: 单个URL或URL列表。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Response: HTTP响应对象。
        """

        async def worker(current_url: str, **worker_kwargs) -> Response:
            return await cls._single_request("HEAD", current_url, **worker_kwargs)

        return await cls._execute_with_fallbacks(url, worker, client=client, **kwargs)

    @classmethod
    async def post(
        cls, url: str | list[str], *, client: AsyncClient | None = None, **kwargs
    ) -> Response:
        """发送POST请求，返回第一个成功的响应。

        参数:
            url: 单个URL或URL列表。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Response: HTTP响应对象。
        """

        async def worker(current_url: str, **worker_kwargs) -> Response:
            return await cls._single_request("POST", current_url, **worker_kwargs)

        return await cls._execute_with_fallbacks(url, worker, client=client, **kwargs)

    @classmethod
    async def get_content(
        cls, url: str | list[str], *, client: AsyncClient | None = None, **kwargs
    ) -> bytes:
        """获取指定URL的二进制内容。

        参数:
            url: 单个URL或URL列表。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            bytes: 响应的二进制内容。
        """
        res = await cls.get(url, client=client, **kwargs)
        return res.content

    @classmethod
    @Retry.api(
        log_name="JSON请求",
        exception=(json.JSONDecodeError,),
        return_on_failure=_SENTINEL,
        wait_fixed_seconds=2,
    )
    async def _request_and_parse_json(
        cls, method: str, url: str, *, client: AsyncClient | None = None, **kwargs
    ) -> Any:
        """执行HTTP请求并解析JSON响应。

        参数:
            method: HTTP方法。
            url: 请求URL。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Any: 解析后的JSON数据。
        """
        client_kwargs, request_kwargs = cls._split_kwargs(kwargs)
        async with cls._get_active_client_context(
            client=client, **client_kwargs
        ) as active_client:
            response = await active_client.request(method, url, **request_kwargs)
            response.raise_for_status()
            return response.json()

    @classmethod
    async def get_json(
        cls,
        url: str | list[str],
        *,
        default: Any = None,
        raise_on_failure: bool = False,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Any:
        """发送GET请求并自动解析为JSON，支持重试和多链接尝试。

        参数:
            url: 单个URL或URL列表。
            default: 失败时的默认返回值。
            raise_on_failure: 失败时是否抛出AllURIsFailedError。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Any: 解析后的JSON数据或默认值。
        """
        return await cls._json_request_with_fallback(
            "GET",
            url,
            log_label="GET JSON",
            default=default,
            raise_on_failure=raise_on_failure,
            client=client,
            **kwargs,
        )

    @classmethod
    async def post_json(
        cls,
        url: str | list[str],
        *,
        json: Any = None,
        data: Any = None,
        default: Any = None,
        raise_on_failure: bool = False,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Any:
        """发送POST请求并自动解析为JSON，支持重试和多链接尝试。

        参数:
            url: 单个URL或URL列表。
            json: 请求体JSON数据。
            data: 请求体表单数据。
            default: 失败时的默认返回值。
            raise_on_failure: 失败时是否抛出AllURIsFailedError。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Any: 解析后的JSON数据或默认值。
        """
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            kwargs["data"] = data
        return await cls._json_request_with_fallback(
            "POST",
            url,
            log_label="POST JSON",
            default=default,
            raise_on_failure=raise_on_failure,
            client=client,
            **kwargs,
        )

    @classmethod
    @Retry.api(log_name="文件下载(流式)")
    async def _stream_download(
        cls, url: str, path: Path, *, client: AsyncClient | None = None, **kwargs
    ) -> None:
        """执行流式下载，被重试装饰器包裹。

        参数:
            url: 下载URL。
            path: 保存路径。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。
        """
        client_kwargs, request_kwargs = cls._split_kwargs(kwargs)
        show_progress = request_kwargs.pop("show_progress", False)

        async with cls._get_active_client_context(
            client=client, **client_kwargs
        ) as active_client:
            async with active_client.stream(
                "GET", url, **request_kwargs
            ) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))

                if show_progress:
                    with Progress(
                        TextColumn(path.name),
                        "[progress.percentage]{task.percentage:>3.0f}%",
                        BarColumn(bar_width=None),
                        DownloadColumn(),
                        TransferSpeedColumn(),
                    ) as progress:
                        task_id = progress.add_task("Download", total=total)
                        async with aiofiles.open(path, "wb") as f:
                            async for chunk in response.aiter_bytes():
                                await f.write(chunk)
                                progress.update(task_id, advance=len(chunk))
                else:
                    async with aiofiles.open(path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)

    @classmethod
    async def download_file(
        cls,
        url: str | list[str],
        path: str | Path,
        *,
        stream: bool = False,
        show_progress: bool = False,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> bool:
        """下载文件到指定路径，支持多链接尝试和流式下载。

        参数:
            url: 单个URL或URL列表。
            path: 文件保存路径。
            stream: 是否使用流式下载。
            show_progress: 是否显示下载进度条。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            bool: 是否下载成功。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async def worker(current_url: str, **worker_kwargs) -> bool:
            if stream:
                await cls._stream_download(
                    current_url, path,
                    show_progress=show_progress, **worker_kwargs,
                )
            else:
                content = await cls.get_content(current_url, **worker_kwargs)
                async with aiofiles.open(path, "wb") as f:
                    await f.write(content)
            logger.info(
                f"下载 {current_url} 成功 -> {path.absolute()}",
                "AsyncHttpx:download",
            )
            return True

        try:
            return await cls._execute_with_fallbacks(
                url, worker, client=client, **kwargs
            )
        except AllURIsFailedError:
            logger.error(
                f"所有URL下载均失败 -> {path.absolute()}", "AsyncHttpx:download"
            )
            return False

    @classmethod
    async def gather_download_file(
        cls,
        url_list: Sequence[list[str] | str],
        path_list: Sequence[str | Path],
        *,
        limit_async_number: int = 5,
        **kwargs,
    ) -> list[bool]:
        """并发下载多个文件，支持为每个文件提供多个URL尝试。

        参数:
            url_list: URL列表，每个元素可以是单个URL或URL列表。
            path_list: 文件路径列表，与url_list一一对应。
            limit_async_number: 并发下载数量限制。
            **kwargs: 传递给download_file的参数。

        返回:
            list[bool]: 每个文件是否下载成功。
        """
        semaphore = asyncio.Semaphore(limit_async_number)

        async def limited_download(
            url: str | list[str], path: str | Path
        ) -> bool:
            async with semaphore:
                return await cls.download_file(url, path, **kwargs)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(limited_download(url, path))
                for url, path in zip(url_list, path_list, strict=True)
            ]
        return [task.result() for task in tasks]

    @classmethod
    async def resume_download(
        cls,
        url: str,
        path: str | Path,
        *,
        chunk_size: int = 1024 * 1024,
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> bool:
        """断点续传下载，基于Range头从上次中断处继续下载。

        参数:
            url: 下载URL（单个URL，不支持多URL回退）。
            path: 文件保存路径。
            chunk_size: 每次读取的块大小(字节)。
            on_progress: 进度回调(已下载字节数, 总字节数)，总字节数
                未知时为-1。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            bool: 是否下载成功。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        existing_size = path.stat().st_size if path.exists() else 0
        headers = kwargs.pop("headers", {})
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            logger.info(
                f"断点续传: {path.name} 已有 {existing_size} 字节",
                "AsyncHttpx:resume",
            )

        client_kwargs, request_kwargs = cls._split_kwargs(kwargs)
        request_kwargs["headers"] = headers

        try:
            async with cls._get_active_client_context(
                client=client, **client_kwargs
            ) as active_client:
                async with active_client.stream(
                    "GET", url, **request_kwargs
                ) as response:
                    if response.status_code == 200 and existing_size > 0:
                        logger.warning(
                            f"服务器不支持Range请求，重新下载: {path.name}",
                            "AsyncHttpx:resume",
                        )
                        existing_size = 0
                        mode = "wb"
                    elif response.status_code == 206:
                        mode = "ab"
                        logger.info(
                            f"服务器支持Range请求，继续下载: {path.name}",
                            "AsyncHttpx:resume",
                        )
                    else:
                        response.raise_for_status()
                        mode = "wb"

                    content_length = response.headers.get("Content-Length")
                    total = (
                        int(content_length) + existing_size
                        if content_length
                        else -1
                    )
                    downloaded = existing_size

                    async with aiofiles.open(path, mode) as f:
                        async for chunk in response.aiter_bytes(chunk_size):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if on_progress:
                                await on_progress(downloaded, total)

                    logger.info(
                        f"断点续传下载完成: {url} -> "
                        f"{path.absolute()} ({downloaded} 字节)",
                        "AsyncHttpx:resume",
                    )
                    return True
        except Exception as e:
            logger.error(
                f"断点续传下载失败: {url} - {e}",
                "AsyncHttpx:resume",
                e=e,
            )
            return False

    @classmethod
    async def cached_get(
        cls,
        url: str,
        *,
        ttl: float = 300.0,
        params: dict[str, Any] | None = None,
        client: AsyncClient | None = None,
        **kwargs,
    ) -> Any:
        """带缓存的GET请求，JSON响应自动缓存。

        参数:
            url: 请求URL。
            ttl: 缓存TTL(秒)。
            params: 查询参数。
            client: 可选的HTTP客户端。
            **kwargs: 请求参数。

        返回:
            Any: 缓存或新获取的JSON数据。
        """
        key = ResponseCache.build_cache_key("GET", url, params=params)
        return await response_cache.get_or_fetch(
            key,
            cls.get_json,
            url,
            params=params,
            client=client,
            **kwargs,
            ttl=ttl,
        )


async_httpx = AsyncHttpx()
