"""视觉线索增强检索实现

针对「带图提问」这类内置 web_search 无法处理的场景：
先用视觉模型从图中抽出可检索的关键词，再拼进查询串去检索。

与既有能力的边界：
- 纯文本单路检索 → 内置 web_search 工具
- 多角度并发研究 → web_research 技能的 deep_research
- 只看图不检索 → vision_analyze 技能
本技能只负责「图 → 关键词 → 检索」这一条链路。
"""

import asyncio
from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_IMAGE,
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    LATENCY_CLASS_SLOW,
)
from liuying.liuying_plugins.AI.core.vision import summarize_image
from liuying.liuying_plugins.AI.skills.media import fetch_images
from liuying.liuying_plugins.AI.tools import AgentTool

_MAX_IMAGES = 2
"""参与线索抽取的图片数上限"""

_RESULT_COUNT = 5
"""检索结果条数"""

_SNIPPET_LIMIT = 200
"""单条摘要截断长度，控制送入LLM的token"""

_CLUE_LIMIT = 60
"""单张图抽出的线索文本截断长度"""

_TOTAL_TIMEOUT = 40.0
"""线索抽取加检索的总超时（秒）"""

_CLUE_PROMPT = (
    "请从这张图片中提取最适合用于网络搜索的关键词。"
    "只输出关键词本身，用空格分隔，不超过6个词，"
    "不要输出解释、标点和完整句子。"
    "图中有明确文字、商品名、作品名、地标时优先输出它们。"
    "认不出具体名称时输出空字符串。"
)
"""视觉线索抽取提示词"""


def clean_clue(text: str) -> str:
    """清洗视觉模型返回的线索文本

    视觉模型常忽略「只输出关键词」的约束而带上解释性句子，
    此处做长度截断与换行归一，避免污染查询串。

    参数:
        text: 视觉模型原始输出

    返回:
        str: 清洗后的线索，无有效内容时为空串
    """
    clue = " ".join((text or "").split())
    return clue[:_CLUE_LIMIT].strip()


async def extract_clues(
    image_urls: list[str], llm_helper: Any
) -> list[str]:
    """从图片中并发抽取检索线索

    参数:
        image_urls: 图片URL列表
        llm_helper: LLM助手实例

    返回:
        list[str]: 线索文本列表，失败的图片不产出线索
    """
    fetched = await fetch_images(image_urls or [], _MAX_IMAGES)
    if not fetched:
        return []

    async def _one(data: bytes, mime: str, error: str) -> str:
        """单张线索抽取并吸收异常"""
        if error:
            return ""
        # 视觉模型属外部不确定依赖，单张失败降级为无线索，
        # 检索仍可按原查询继续。
        try:
            summary = await summarize_image(
                data, mime, llm_helper, prompt=_CLUE_PROMPT
            )
        except Exception:
            return ""
        if not summary.success:
            return ""
        return clean_clue(summary.description)

    clues = await asyncio.gather(
        *(
            _one(data, mime, error)
            for _, data, mime, error in fetched
        )
    )
    return [clue for clue in clues if clue]


def build_query(query: str, clues: list[str]) -> str:
    """把原查询与视觉线索拼成增强查询

    去重后拼接，避免线索里重复出现原查询中已有的词。

    参数:
        query: 用户原查询
        clues: 视觉线索列表

    返回:
        str: 增强后的查询串
    """
    query = (query or "").strip()
    seen = set(query.lower().split())
    extra: list[str] = []
    for clue in clues:
        for word in clue.split():
            key = word.lower()
            if key in seen:
                continue
            seen.add(key)
            extra.append(word)
    if not extra:
        return query
    return f"{query} {' '.join(extra)}".strip()


def format_results(items: list[dict[str, str]]) -> str:
    """格式化检索结果

    参数:
        items: 检索结果列表

    返回:
        str: 编号结果文本
    """
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        title = (item.get("title") or "").strip()
        snippet = (
            item.get("snippet") or item.get("content") or ""
        ).strip()
        if len(snippet) > _SNIPPET_LIMIT:
            snippet = f"{snippet[:_SNIPPET_LIMIT]}..."
        lines.append(f"[{index}] {title}\n{snippet}")
    return "\n\n".join(lines)


async def visual_search(
    query: str,
    image_urls: list[str] | None = None,
    llm_helper: Any = None,
) -> str:
    """结合图片线索执行网络检索

    参数:
        query: 用户原查询
        image_urls: 相关图片URL列表
        llm_helper: LLM助手实例

    返回:
        str: 检索结果或不可用原因
    """
    if llm_helper is None:
        return "视觉检索不可用：未配置LLM助手"
    query = (query or "").strip()
    if not query and not image_urls:
        return "请提供查询词或图片"

    clues: list[str] = []
    final_query = query
    # 视觉抽取与检索均为外部调用，整体超时兜底避免挂死 Agent 循环。
    try:
        async with asyncio.timeout(_TOTAL_TIMEOUT):
            clues = await extract_clues(
                image_urls or [], llm_helper
            )
            final_query = build_query(query, clues)
            if not final_query:
                return "无法从图片中识别出可检索的内容，请补充文字描述"
            results = await llm_helper.web_search(
                final_query, count=_RESULT_COUNT
            )
    except TimeoutError:
        return "视觉检索超时，请稍后重试"
    except Exception as e:
        return f"视觉检索失败：{type(e).__name__}"

    items = [r for r in (results or ()) if isinstance(r, dict)]
    if not items:
        return f"用「{final_query}」没检索到相关结果"

    header = f"检索词：{final_query}"
    if clues:
        header += f"（含{len(clues)}张图的视觉线索）"
    return f"{header}\n\n{format_results(items)}"


def build_search_tools(runtime: Any) -> list[AgentTool]:
    """构建视觉检索工具集

    参数:
        runtime: SkillRuntime 实例

    返回:
        list[AgentTool]: 工具列表
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(
        query: str, image_urls: list[str] | None = None
    ) -> str:
        """视觉检索handler

        参数:
            query: 查询词
            image_urls: 图片URL列表

        返回:
            str: 检索结果
        """
        return await visual_search(
            query=query,
            image_urls=image_urls,
            llm_helper=llm_helper,
        )

    return [
        AgentTool(
            name="visual_web_search",
            description=(
                "带图检索：先从图片里认出是什么，再拿去网上查。"
                "用户发图并问「这个多少钱」「这是哪」「这是哪部动画」"
                "这类需要联网求证的问题时用本工具。"
                "纯文字查询用 web_search，只想知道图里有什么用 "
                "analyze_image，都不要用本工具"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "用户想查的问题，如「价格」「产地」；"
                            "图片是主要线索时可以只写问的方向"
                        ),
                    },
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            f"相关图片URL，最多{_MAX_IMAGES}个"
                        ),
                    },
                },
                "required": ["query"],
            },
            func=_handler,
            intent_tags=[
                INTENT_TAG_IMAGE,
                INTENT_TAG_NETWORK,
                INTENT_TAG_REALTIME,
            ],
            latency_class=LATENCY_CLASS_SLOW,
            requires_network=True,
            requires_image=True,
            evidence_kind=EVIDENCE_KIND_TOOL,
        )
    ]
