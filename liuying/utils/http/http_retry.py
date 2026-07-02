"""HTTP重试装饰器模块，基于tenacity提供固定等待与指数退避策略。"""

from collections.abc import Callable
from functools import partial, wraps
from typing import Any

from anyio import EndOfStream
from httpx import (
    ConnectError,
    HTTPStatusError,
    RemoteProtocolError,
    StreamError,
    TimeoutException,
)
from nonebot.utils import is_coroutine_callable
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from liuying.utils.enum import WaitStrategy
from liuying.utils.log import logger

LOG_COMMAND = "RetryDecorator"
_SENTINEL = object()

NETWORK_EXCEPTIONS = (
    TimeoutException,
    ConnectError,
    HTTPStatusError,
    StreamError,
    RemoteProtocolError,
    EndOfStream,
)


class Retry:
    """重试装饰器工具类，提供固定等待与指数退避两种预设策略。"""

    @staticmethod
    def _log_before_sleep(log_name: str | None, retry_state: RetryCallState):
        """tenacity 重试前的日志记录回调函数。

        参数:
            log_name: 操作名称，用于日志标识。
            retry_state: tenacity 重试状态对象。
        """
        func_name = (
            retry_state.fn.__name__ if retry_state.fn else "unknown_function"
        )
        log_context = (
            f"操作 '{log_name}' (函数 '{func_name}')"
            if log_name
            else f"函数 '{func_name}'"
        )

        reason = ""
        if retry_state.outcome:
            if exc := retry_state.outcome.exception():
                reason = f"触发异常: {exc.__class__.__name__}({exc})"
            else:
                reason = (
                    f"不满足结果条件: result={retry_state.outcome.result()}"
                )

        wait_time = (
            getattr(retry_state.next_action, "sleep", 0)
            if retry_state.next_action
            else 0
        )
        logger.warning(
            f"{log_context} 第 {retry_state.attempt_number} 次重试... "
            f"等待 {wait_time:.2f} 秒. {reason}",
            LOG_COMMAND,
        )

    @staticmethod
    def _build_wait_strategy(
        strategy: WaitStrategy,
        wait_fixed_seconds: int,
        wait_exp_multiplier: int,
        wait_exp_max: int,
    ):
        """根据策略类型构建等待策略对象。

        参数:
            strategy: 等待策略类型。
            wait_fixed_seconds: 固定等待秒数。
            wait_exp_multiplier: 指数退避乘数。
            wait_exp_max: 指数退避最大等待时间。

        返回:
            tenacity 等待策略对象。
        """
        match strategy:
            case WaitStrategy.EXPONENTIAL:
                return wait_exponential(
                    multiplier=wait_exp_multiplier, max=wait_exp_max
                )
            case _:
                return wait_fixed(wait_fixed_seconds)

    @staticmethod
    async def _invoke_failure_callback(
        on_failure: Callable[[Exception], Any] | None, exc: Exception
    ):
        """调用失败回调，自动适配同步/异步回调。

        参数:
            on_failure: 失败回调函数。
            exc: 捕获到的异常。
        """
        if on_failure is None:
            return
        if is_coroutine_callable(on_failure):
            await on_failure(exc)
        else:
            on_failure(exc)

    @staticmethod
    def simple(
        stop_max_attempt: int = 3,
        wait_fixed_seconds: int = 2,
        exception: tuple[type[Exception], ...] = (),
        *,
        log_name: str | None = None,
        on_failure: Callable[[Exception], Any] | None = None,
        return_on_failure: Any = _SENTINEL,
    ):
        """用于通用网络请求的重试装饰器预设，使用固定等待策略。

        参数:
            stop_max_attempt: 最大重试次数。
            wait_fixed_seconds: 固定等待秒数。
            exception: 额外需要重试的异常类型元组。
            log_name: 日志记录的操作名称。
            on_failure: 所有重试失败后的回调。
            return_on_failure: 所有重试失败后的返回值。
        """
        return Retry.api(
            stop_max_attempt=stop_max_attempt,
            wait_fixed_seconds=wait_fixed_seconds,
            exception=exception,
            strategy=WaitStrategy.FIXED,
            log_name=log_name,
            on_failure=on_failure,
            return_on_failure=return_on_failure,
        )

    @staticmethod
    def download(
        stop_max_attempt: int = 3,
        exception: tuple[type[Exception], ...] = (),
        *,
        wait_exp_multiplier: int = 2,
        wait_exp_max: int = 15,
        log_name: str | None = None,
        on_failure: Callable[[Exception], Any] | None = None,
        return_on_failure: Any = _SENTINEL,
    ):
        """适用于文件下载的重试装饰器预设，使用指数退避策略。

        参数:
            stop_max_attempt: 最大重试次数。
            exception: 额外需要重试的异常类型元组。
            wait_exp_multiplier: 指数退避乘数。
            wait_exp_max: 指数退避最大等待时间。
            log_name: 日志记录的操作名称。
            on_failure: 所有重试失败后的回调。
            return_on_failure: 所有重试失败后的返回值。
        """
        return Retry.api(
            stop_max_attempt=stop_max_attempt,
            exception=exception,
            strategy=WaitStrategy.EXPONENTIAL,
            wait_exp_multiplier=wait_exp_multiplier,
            wait_exp_max=wait_exp_max,
            log_name=log_name,
            on_failure=on_failure,
            return_on_failure=return_on_failure,
        )

    @staticmethod
    def api(
        stop_max_attempt: int = 3,
        wait_fixed_seconds: int = 1,
        exception: tuple[type[Exception], ...] = (),
        *,
        strategy: WaitStrategy = WaitStrategy.FIXED,
        retry_on_result: Callable[[Any], bool] | None = None,
        wait_exp_multiplier: int = 1,
        wait_exp_max: int = 10,
        log_name: str | None = None,
        on_failure: Callable[[Exception], Any] | None = None,
        return_on_failure: Any = _SENTINEL,
    ):
        """通用、可配置的API调用重试装饰器。

        参数:
            stop_max_attempt: 最大重试次数。
            wait_fixed_seconds: 固定等待秒数。
            exception: 额外需要重试的异常类型元组。
            strategy: 等待策略，'fixed' 或 'exponential'。
            retry_on_result: 结果判断回调，返回True时触发重试。
            wait_exp_multiplier: 指数退避乘数。
            wait_exp_max: 指数退避最大等待时间。
            log_name: 日志记录的操作名称。
            on_failure: 所有重试失败后的回调。
            return_on_failure: 所有重试失败后的返回值，设置后不抛异常。
        """
        base_exceptions = (*NETWORK_EXCEPTIONS, *exception)
        wait_strategy = Retry._build_wait_strategy(
            strategy, wait_fixed_seconds, wait_exp_multiplier, wait_exp_max
        )

        def decorator(func: Callable) -> Callable:
            retry_conditions = retry_if_exception_type(base_exceptions)
            if retry_on_result:
                retry_conditions |= retry_if_result(retry_on_result)

            decorated_func = retry(
                stop=stop_after_attempt(stop_max_attempt),
                wait=wait_strategy,
                retry=retry_conditions,
                before_sleep=partial(Retry._log_before_sleep, log_name),
                reraise=True,
            )(func)

            if return_on_failure is _SENTINEL:
                return decorated_func

            if is_coroutine_callable(func):

                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    try:
                        return await decorated_func(*args, **kwargs)
                    except Exception as e:
                        await Retry._invoke_failure_callback(on_failure, e)
                        return return_on_failure

                return async_wrapper

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                try:
                    return decorated_func(*args, **kwargs)
                except Exception as e:
                    if on_failure:
                        if is_coroutine_callable(on_failure):
                            logger.error(
                                f"不能在同步函数 '{func.__name__}' 中"
                                f"调用异步的 on_failure 回调。",
                                LOG_COMMAND,
                            )
                        else:
                            on_failure(e)
                    return return_on_failure

            return sync_wrapper

        return decorator
