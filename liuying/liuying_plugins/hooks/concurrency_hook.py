"""并发限制释放钩子"""

from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor

from liuying.utils.limiters import ConcurrencyLimiter


@run_postprocessor
async def _concurrency_release_hook(matcher: Matcher):
    """释放并发限制器，与统计钩子独立"""
    if concurrency_info := matcher.state.get("_concurrency_limiter_info"):
        limiter: ConcurrencyLimiter = concurrency_info["limiter"]
        limiter.release(concurrency_info["key"])
