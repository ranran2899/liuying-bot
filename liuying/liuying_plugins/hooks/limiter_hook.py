from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor

from liuying.utils.manager.limiter_manager import ConcurrencyLimiter


@run_postprocessor
async def _concurrency_release_hook(matcher: Matcher):
    if concurrency_info := matcher.state.get("_concurrency_limiter_info"):
        limiter: ConcurrencyLimiter = concurrency_info["limiter"]
        key = concurrency_info["key"]
        limiter.release(key)
