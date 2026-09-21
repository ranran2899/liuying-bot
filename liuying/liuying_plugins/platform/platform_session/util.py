"""适配器工具集"""

from collections.abc import Coroutine
from datetime import datetime, timedelta
import json
from typing import Any

from nonebot.exception import ActionFailed


class DatetimeJsonEncoder(json.JSONEncoder):
    """支持 datetime 与 timedelta 的 JSON 编码器"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return int(obj.timestamp())
        if isinstance(obj, timedelta):
            return obj.total_seconds()
        return super().default(obj)


async def safe_call[T](coro: Coroutine[Any, Any, T], default: Any = None) -> Any:
    """执行适配器 API 调用，失败时降级返回默认值

    参数:
        coro: 适配器 API 协程
        default: 调用失败时的降级返回值

    返回:
        Any: API 结果或降级默认值
    """
    try:
        return await coro
    except ActionFailed:
        return default
