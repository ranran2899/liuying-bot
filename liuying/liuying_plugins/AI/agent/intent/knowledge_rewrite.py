"""检索意图规划器

用LLM改写用户查询，识别梗/黑话/缩写并补出正式名，
提升知识库召回准确率。失败时返回原始查询，不阻塞召回。
短查询与近期重复查询直接跳过LLM调用，控制召回链路延迟。
"""

import time

from liuying.utils.log import logger

from ...core.llm import llm_helper
from ...core.llm.model_router import ROLE_INTENT, model_router
from ...core.tools.json_utils import extract_json_payload

# 改写结果缓存：同查询TTL内直接复用，避免重复LLM调用
_REWRITE_TTL_SECONDS = 600.0
_REWRITE_CACHE_MAX = 128
_rewrite_cache: dict[str, tuple[float, str]] = {}


async def rewrite_query(query: str) -> str:
    """改写查询以提升知识库召回准确率

    用LLM识别梗/黑话/缩写并补出正式名。
    超短查询改写收益低直接返回；同查询命中TTL缓存时跳过LLM。
    失败时返回原始查询，不阻塞召回流程。

    参数:
        query: 原始查询

    返回:
        str: 改写后的查询
    """
    if not query or not query.strip():
        return query
    key = query.strip()
    # 极短/超长查询改写收益低或成本高，直接跳过
    if len(key) <= 4 or len(key) > 100:
        return query

    now = time.monotonic()
    cached = _rewrite_cache.get(key)
    if cached and now - cached[0] < _REWRITE_TTL_SECONDS:
        return cached[1]

    prompt = (
        "请改写以下用户查询，使其更适合知识库检索。\n\n"
        f"原始查询: {query}\n\n"
        "任务：\n"
        "1. 识别查询中的网络梗、黑话、缩写\n"
        "2. 补出正式名称或全称\n"
        "3. 保留原意，不要扩展无关内容\n"
        "4. 如果查询已经清晰，原样返回\n\n"
        "严格输出JSON：\n"
        "{\n"
        '  "rewritten": "改写后的查询",\n'
        '  "expanded_terms": ["扩展术语1", "扩展术语2"]\n'
        "}\n"
    )
    try:
        role = model_router.resolve(ROLE_INTENT)
        text = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            model=role.model or None,
            options=role.apply_to_options({"temperature": 0.2}),
            provider_name=role.provider or None,
        )
        data = extract_json_payload(text)
        if data is None:
            return query
        rewritten = str(
            data.get("rewritten", "") or ""
        ).strip()
        if not rewritten:
            return query

        if len(_rewrite_cache) >= _REWRITE_CACHE_MAX:
            oldest = sorted(
                _rewrite_cache.items(),
                key=lambda kv: kv[1][0],
            )[: _REWRITE_CACHE_MAX // 2]
            for stale_key, _ in oldest:
                _rewrite_cache.pop(stale_key, None)
        _rewrite_cache[key] = (now, rewritten)
        return rewritten
    except Exception as e:
        logger.debug(
            f"查询改写失败，返回原始: {e}",
            command="AI",
            e=e,
        )
        return query
