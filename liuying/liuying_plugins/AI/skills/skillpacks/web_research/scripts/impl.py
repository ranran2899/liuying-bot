"""并发深度检索实现

面向需要多角度求证的问题：一次调用并发跑多个子查询，
按 URL 与标题去重后归并，再由 LLM 汇总成结论。

相比模型串行调用多次 web_search，本技能把 N 轮
「模型决策 + 网络往返」压缩为 1 轮，显著降低 token 与延迟。
"""

import asyncio
from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    LATENCY_CLASS_SLOW,
)
from liuying.liuying_plugins.AI.agent.tools import AgentTool

_MAX_QUERIES = 4
"""单次最多并发的子查询数，超出截断"""

_PER_QUERY_RESULTS = 4
"""每个子查询取回的结果数"""

_MAX_MERGED = 10
"""归并后进入摘要的最大条目数"""

_SNIPPET_LIMIT = 220
"""单条摘要截断长度，控制送入LLM的token"""

_QUERY_TIMEOUT = 25.0
"""全部子查询的总超时秒数"""

_SUMMARY_PROMPT = (
    "你是资料整理助手。下面是针对同一问题的多路检索结果。"
    "请只依据这些材料，用中文写出简洁结论：\n"
    "1. 先给出直接回答，不要铺垫\n"
    "2. 材料互相矛盾时明确指出分歧\n"
    "3. 材料不足以回答时直说不确定，禁止编造\n"
    "4. 控制在 200 字以内，不要用 Markdown 标题和表格"
)
"""归并摘要的系统提示"""


def _normalize_url(url: str) -> str:
    """归一化URL用于去重

    去掉协议、www 前缀、尾部斜杠与查询串，
    使同一页面的不同写法能被判为重复。

    参数:
        url: 原始URL

    返回:
        str: 归一化后的URL
    """
    text = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        text = text.removeprefix(prefix)
    text = text.removeprefix("www.")
    text = text.split("?", 1)[0].split("#", 1)[0]
    return text.rstrip("/")


async def _search_one(
    llm_helper: Any, query: str
) -> list[dict[str, str]]:
    """执行单个子查询

    参数:
        llm_helper: LLM助手实例
        query: 子查询文本

    返回:
        list[dict[str, str]]: 检索结果，失败返回空列表
    """
    # 单路检索失败不应拖垮整次研究，降级为空结果由其余路补足。
    try:
        results = await llm_helper.web_search(
            query, count=_PER_QUERY_RESULTS
        )
    except Exception:
        return []
    return [r for r in (results or ()) if isinstance(r, dict)]


def _dedup_key(item: dict[str, str]) -> str:
    """计算结果条目的去重键

    优先用归一化URL，URL 缺失时退化为小写标题。

    参数:
        item: 检索结果条目

    返回:
        str: 去重键，无法计算时为空串
    """
    url = item.get("url") or item.get("link") or ""
    if key := _normalize_url(url):
        return key
    return (item.get("title") or "").strip().lower()


def _interleave(
    batches: list[list[dict[str, str]]],
) -> list[dict[str, str]]:
    """按轮次交错展平多路结果

    交错而非顺序拼接，避免单一子查询垄断名额。

    参数:
        batches: 各子查询的结果列表

    返回:
        list[dict[str, str]]: 交错展平后的条目
    """
    if not batches:
        return []
    depth = max(len(batch) for batch in batches)
    return [
        batch[index]
        for index in range(depth)
        for batch in batches
        if index < len(batch)
    ]


def merge_results(
    batches: list[list[dict[str, str]]],
) -> list[dict[str, str]]:
    """归并多路检索结果并去重

    参数:
        batches: 各子查询的结果列表

    返回:
        list[dict[str, str]]: 去重后的结果，最多 _MAX_MERGED 条
    """
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for item in _interleave(batches):
        key = _dedup_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= _MAX_MERGED:
            break
    return merged


def format_material(items: list[dict[str, str]]) -> str:
    """把检索结果格式化为送入LLM的材料

    参数:
        items: 去重后的结果

    返回:
        str: 编号材料文本
    """
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or item.get("content") or "").strip()
        if len(snippet) > _SNIPPET_LIMIT:
            snippet = f"{snippet[:_SNIPPET_LIMIT]}..."
        lines.append(f"[{index}] {title}\n{snippet}")
    return "\n\n".join(lines)


async def research(
    question: str,
    queries: list[str] | None = None,
    llm_helper: Any = None,
) -> str:
    """并发检索并汇总结论

    参数:
        question: 要回答的原始问题
        queries: 子查询列表，为空时用 question 单路检索
        llm_helper: LLM助手实例

    返回:
        str: 汇总结论，或不可用原因说明
    """
    if llm_helper is None:
        return "深度检索不可用：未配置LLM助手"
    question = (question or "").strip()
    if not question:
        return "请提供要研究的问题"

    sub_queries = [
        q.strip() for q in (queries or []) if q and q.strip()
    ][:_MAX_QUERIES] or [question]

    # 并发检索属外部网络调用，整体超时需兜底避免挂死 Agent 循环。
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT):
            batches = await asyncio.gather(
                *(_search_one(llm_helper, q) for q in sub_queries)
            )
    except TimeoutError:
        return "深度检索超时，请缩小问题范围后重试"

    merged = merge_results(list(batches))
    if not merged:
        return f"未检索到与「{question}」相关的资料"

    material = format_material(merged)
    # 汇总失败时退化为直接返回材料，保证工具始终产出可用信息。
    try:
        summary = await llm_helper.chat_text(
            [
                {"role": "system", "content": _SUMMARY_PROMPT},
                {
                    "role": "user",
                    "content": f"问题：{question}\n\n材料：\n{material}",
                },
            ]
        )
    except Exception:
        return f"检索到{len(merged)}条资料：\n{material}"

    summary = (summary or "").strip()
    if not summary:
        return f"检索到{len(merged)}条资料：\n{material}"
    return (
        f"{summary}\n\n"
        f"（基于{len(sub_queries)}路检索、{len(merged)}条资料）"
    )


def build_research_tool(runtime: Any) -> AgentTool:
    """构建深度检索工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: 深度检索工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(
        question: str, queries: list[str] | None = None
    ) -> str:
        """深度检索handler

        参数:
            question: 原始问题
            queries: 子查询列表

        返回:
            str: 汇总结论
        """
        return await research(
            question=question,
            queries=queries,
            llm_helper=llm_helper,
        )

    return AgentTool(
        name="deep_research",
        description=(
            "复杂问题的多角度并发检索并汇总结论。需要交叉验证、"
            "对比多个来源、或一次搞清多个子问题时用本工具，"
            "不要连续多次调用 web_search"
        ),
        parameters={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要回答的原始问题",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        f"拆解出的子查询，最多{_MAX_QUERIES}条，"
                        "彼此角度应不同；省略时按原问题单路检索"
                    ),
                },
            },
            "required": ["question"],
        },
        func=_handler,
        intent_tags=[INTENT_TAG_NETWORK, INTENT_TAG_REALTIME],
        latency_class=LATENCY_CLASS_SLOW,
        requires_network=True,
        evidence_kind=EVIDENCE_KIND_TOOL,
        per_session_quota=2,
    )
