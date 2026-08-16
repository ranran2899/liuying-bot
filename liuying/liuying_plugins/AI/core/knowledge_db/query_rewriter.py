"""检索意图规划器

用LLM改写用户查询，识别梗/黑话/缩写并补出正式名，
提升知识库召回准确率。失败时返回原始查询，不阻塞召回。
"""

from liuying.utils.log import logger

from ..llm import llm_helper
from ..tools.json_utils import extract_json_payload

__all__ = ["rewrite_query"]


async def rewrite_query(query: str) -> str:
    """改写查询以提升知识库召回准确率

    用LLM识别梗/黑话/缩写并补出正式名。
    失败时返回原始查询，不阻塞召回流程。

    参数:
        query: 原始查询

    返回:
        str: 改写后的查询
    """
    if not query or not query.strip():
        return query
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
        text = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            options={"temperature": 0.2},
        )
        data = extract_json_payload(text)
        if data is None:
            return query
        rewritten = str(
            data.get("rewritten", "") or ""
        ).strip()
        if not rewritten:
            return query
        return rewritten
    except Exception as e:
        logger.debug(
            f"查询改写失败，返回原始: {e}",
            command="AI",
            e=e,
        )
        return query
