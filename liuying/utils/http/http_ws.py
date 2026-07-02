"""WebSocket工具模块，提供连接、收发、重连等能力。"""

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, TypeAlias

from nonebot.utils import is_coroutine_callable
import orjson as json
import websockets
from websockets.client import WebSocketClientProtocol

from liuying.utils.log import logger

_LOG_TAG = "WsUtils"

WsResult: TypeAlias = dict[str, Any]
WsCallback: TypeAlias = Callable[..., Any]


class WsUtils:
    """WebSocket工具类，提供连接、发送、接收、重连等功能。"""

    @staticmethod
    def _error_result(error: str, **extra) -> WsResult:
        """构造统一的错误结果字典。

        参数:
            error: 错误描述。
            **extra: 额外字段。

        返回:
            dict: 标准错误结果。
        """
        return {"success": False, "error": error, **extra}

    @staticmethod
    def _serialize_data(data: str | dict[str, Any]) -> str:
        """将数据序列化为字符串，字典自动转JSON。

        参数:
            data: 原始数据。

        返回:
            str: 序列化后的字符串。
        """
        if isinstance(data, dict):
            return json.dumps(data).decode("utf-8")
        return str(data)

    @staticmethod
    async def _invoke_callback(callback: WsCallback | None, *args, **kwargs):
        """调用回调函数，自动适配同步/异步。

        参数:
            callback: 回调函数。
            *args: 位置参数。
            **kwargs: 关键字参数。
        """
        if callback is None:
            return
        if is_coroutine_callable(callback):
            await callback(*args, **kwargs)
        else:
            callback(*args, **kwargs)

    @classmethod
    async def connect(
        cls,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> WsResult:
        """异步建立WebSocket连接。

        参数:
            url: WebSocket服务器URL。
            headers: 请求头。
            timeout: 连接超时时间(秒)。

        返回:
            dict: 包含success、websocket、url字段的连接结果。
        """
        logger.info(f"尝试连接WebSocket: {url}", _LOG_TAG)
        try:
            websocket = await asyncio.wait_for(
                websockets.connect(url, additional_headers=headers),
                timeout=timeout,
            )
            logger.info(f"WebSocket连接成功: {url}", _LOG_TAG)
            return {"success": True, "websocket": websocket, "url": url}
        except Exception as e:
            logger.error(f"WebSocket连接失败: {url} - {e}", _LOG_TAG, e=e)
            return cls._error_result(str(e), url=url)

    @classmethod
    async def send(
        cls,
        websocket: WebSocketClientProtocol,
        data: str | dict[str, Any],
        is_binary: bool = False,
    ) -> WsResult:
        """异步发送WebSocket消息。

        参数:
            websocket: WebSocket连接对象。
            data: 要发送的数据，字典自动转为JSON。
            is_binary: 是否以二进制形式发送。

        返回:
            dict: 发送结果。
        """
        try:
            data_str = cls._serialize_data(data)
            if is_binary:
                await websocket.send(data_str.encode("utf-8"))
            else:
                await websocket.send(data_str)
            logger.debug(f"WebSocket消息发送成功: {data_str}", _LOG_TAG)
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"WebSocket消息发送失败: {e}", _LOG_TAG, e=e)
            return cls._error_result(str(e), data=data)

    @classmethod
    async def receive(
        cls,
        websocket: WebSocketClientProtocol,
        timeout: int | None = None,
        parse_json: bool = True,
    ) -> WsResult:
        """异步接收WebSocket消息。

        参数:
            websocket: WebSocket连接对象。
            timeout: 超时时间(秒)，None时无限等待。
            parse_json: 是否自动解析JSON。

        返回:
            dict: 包含success、data、raw_data、is_binary的接收结果。
        """
        try:
            recv_coro = websocket.recv()
            message = (
                await asyncio.wait_for(recv_coro, timeout=timeout)
                if timeout is not None
                else await recv_coro
            )

            match message:
                case bytes():
                    message_str = message.decode("utf-8")
                    is_binary = True
                case _:
                    message_str = message
                    is_binary = False

            logger.debug(f"WebSocket消息接收成功: {message_str}", _LOG_TAG)

            if parse_json and not is_binary:
                try:
                    return {
                        "success": True,
                        "data": json.loads(message_str),
                        "raw_data": message_str,
                        "is_binary": is_binary,
                    }
                except json.JSONDecodeError:
                    logger.debug("接收到的消息不是有效的JSON格式", _LOG_TAG)

            return {
                "success": True,
                "data": message_str,
                "raw_data": message,
                "is_binary": is_binary,
            }
        except TimeoutError:
            logger.error("WebSocket消息接收超时", _LOG_TAG)
            return cls._error_result("接收超时")
        except websockets.ConnectionClosed as e:
            logger.error(
                f"WebSocket连接已关闭: {e.code} - {e.reason}", _LOG_TAG
            )
            return cls._error_result(
                f"连接已关闭: {e.code} - {e.reason}", closed=True
            )
        except Exception as e:
            logger.error(f"WebSocket消息接收失败: {e}", _LOG_TAG, e=e)
            return cls._error_result(str(e))

    @classmethod
    async def close(
        cls,
        websocket: WebSocketClientProtocol,
        code: int = 1000,
        reason: str = "Normal closure",
    ) -> WsResult:
        """异步关闭WebSocket连接。

        参数:
            websocket: WebSocket连接对象。
            code: 关闭代码。
            reason: 关闭原因。

        返回:
            dict: 关闭结果。
        """
        try:
            await websocket.close(code=code, reason=reason)
            logger.info(f"WebSocket连接已关闭: {code} - {reason}", _LOG_TAG)
        except Exception:
            pass
        return {"success": True, "code": code, "reason": reason}

    @classmethod
    @asynccontextmanager
    async def _managed_connection(
        cls, url: str, headers: dict[str, str] | None = None, timeout: int = 30
    ) -> WebSocketClientProtocol:
        """管理WebSocket连接的上下文，自动关闭。

        参数:
            url: WebSocket服务器URL。
            headers: 请求头。
            timeout: 连接超时时间(秒)。

        返回:
            AsyncGenerator: WebSocket连接对象。

        异常:
            ConnectionError: 连接失败时抛出。
        """
        result = await cls.connect(url, headers=headers, timeout=timeout)
        if not result["success"]:
            raise ConnectionError(result.get("error", "连接失败"))
        ws = result["websocket"]
        try:
            yield ws
        finally:
            await cls.close(ws)

    @classmethod
    async def send_and_receive(
        cls,
        url: str,
        data: str | dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        parse_json: bool = True,
        is_binary: bool = False,
    ) -> WsResult:
        """发送消息并等待接收响应（一次性WebSocket请求）。

        参数:
            url: WebSocket服务器URL。
            data: 要发送的数据。
            headers: 请求头。
            timeout: 总超时时间(秒)。
            parse_json: 是否自动解析JSON响应。
            is_binary: 是否以二进制形式发送。

        返回:
            dict: 包含响应数据的结果。
        """
        try:
            async with cls._managed_connection(
                url, headers=headers, timeout=timeout // 2
            ) as ws:
                send_result = await cls.send(ws, data, is_binary=is_binary)
                if not send_result["success"]:
                    return send_result
                return await cls.receive(
                    ws, timeout=timeout // 2, parse_json=parse_json
                )
        except ConnectionError as e:
            return cls._error_result(str(e))
        except Exception as e:
            logger.error(f"WebSocket请求失败: {e}", _LOG_TAG, e=e)
            return cls._error_result(str(e))

    @classmethod
    async def _send_heartbeat(
        cls, websocket: WebSocketClientProtocol, interval: int
    ) -> None:
        """周期性发送心跳包。

        参数:
            websocket: WebSocket连接对象。
            interval: 心跳间隔(秒)。
        """
        try:
            while not websocket.closed:
                try:
                    await websocket.send("ping")
                    logger.debug("WebSocket心跳包发送成功", _LOG_TAG)
                except Exception as e:
                    logger.error(
                        f"WebSocket心跳包发送失败: {e}", _LOG_TAG, e=e
                    )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.debug("WebSocket心跳任务已取消", _LOG_TAG)

    @classmethod
    async def create_websocket_client(
        cls,
        url: str,
        on_message: WsCallback | None,
        on_connect: WsCallback | None = None,
        on_disconnect: WsCallback | None = None,
        headers: dict[str, str] | None = None,
        retry_interval: int = 5,
        max_retry: int = 10,
        heartbeat_interval: int | None = 30,
    ) -> WsResult:
        """创建带重连机制的WebSocket客户端。

        参数:
            url: WebSocket服务器URL。
            on_message: 收到消息的回调函数（支持同步/异步）。
            on_connect: 连接成功的回调函数（支持同步/异步）。
            on_disconnect: 断开连接的回调函数（支持同步/异步）。
            headers: 请求头。
            retry_interval: 重连间隔(秒)。
            max_retry: 最大重连次数，0表示无限重连。
            heartbeat_interval: 心跳间隔(秒)，None时不发送心跳。

        返回:
            dict: 客户端启动结果。
        """
        retry_count = 0
        heartbeat_task: asyncio.Task | None = None

        try:
            while True:
                try:
                    ws = await websockets.connect(
                        url, additional_headers=headers
                    )
                    logger.info(f"WebSocket客户端连接成功: {url}", _LOG_TAG)
                    retry_count = 0

                    if on_connect:
                        try:
                            await cls._invoke_callback(on_connect, ws)
                        except Exception as e:
                            logger.error(
                                f"on_connect回调执行失败: {e}", _LOG_TAG, e=e
                            )

                    if heartbeat_interval:
                        heartbeat_task = asyncio.create_task(
                            cls._send_heartbeat(ws, heartbeat_interval)
                        )

                    while True:
                        try:
                            result = await cls.receive(ws)
                            if not result["success"]:
                                if result.get("closed"):
                                    logger.warning(
                                        "WebSocket连接已关闭，准备重连",
                                        _LOG_TAG,
                                    )
                                    break
                                logger.error(
                                    f"接收消息失败: {result.get('error')}",
                                    _LOG_TAG,
                                )
                                continue

                            if on_message:
                                try:
                                    await cls._invoke_callback(
                                        on_message, result
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"on_message回调执行失败: {e}",
                                        _LOG_TAG,
                                        e=e,
                                    )
                        except Exception as e:
                            logger.error(
                                f"接收消息异常: {e}", _LOG_TAG, e=e
                            )
                            break

                except websockets.ConnectionClosed as e:
                    logger.warning(
                        f"WebSocket连接关闭: {e.code} - {e.reason}", _LOG_TAG
                    )
                    if on_disconnect:
                        try:
                            await cls._invoke_callback(
                                on_disconnect, e.code, e.reason
                            )
                        except Exception as exc:
                            logger.error(
                                f"on_disconnect回调执行失败: {exc}",
                                _LOG_TAG,
                                e=exc,
                            )
                except Exception as e:
                    logger.error(
                        f"WebSocket客户端异常: {e}", _LOG_TAG, e=e
                    )

                if heartbeat_task:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                    heartbeat_task = None

                retry_count += 1
                if max_retry > 0 and retry_count > max_retry:
                    logger.error(
                        f"超过最大重连次数({max_retry})，停止重连", _LOG_TAG
                    )
                    return cls._error_result(
                        f"超过最大重连次数({max_retry})"
                    )

                logger.info(
                    f"{retry_interval}秒后尝试第{retry_count}次重连...",
                    _LOG_TAG,
                )
                await asyncio.sleep(retry_interval)

        except Exception as e:
            logger.error(f"WebSocket客户端启动失败: {e}", _LOG_TAG, e=e)
            return cls._error_result(str(e))


ws_utils = WsUtils()
