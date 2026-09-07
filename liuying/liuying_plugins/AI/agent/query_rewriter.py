"""检索意图改写器

在调用联网/资源/Wiki/视觉类工具前，基于最近对话、引用内容、
最新一句和图片生成高质量检索计划。避免直接拿用户口语当查询词，
提升工具调用成功率，降低无效调用消耗。

参考 nonebot_plugin_personification 的 query_rewriter 设计：
- LLM 改写 + 规则兜底双轨，LLM 失败仍有可用查询
- 口语化梗/黑话/外号识别，补出正式实体名/出处
- 多候选词生成，首轮失败可依次重试
"""

from dataclasses import dataclass
import json
import re
from typing import Any

from liuying.utils.log import logger

from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_INTENT, model_router

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
"""JSON 块提取正则"""

# 口语化前缀包装词（"我问的是"、"请问"等）
_QUERY_WRAPPER_LEADING_RE = re.compile(
    r"^(?:我问的是|我想问的是|我想问下|我想问一下|我想知道|我问下|我问一下|"
    r"请问|想问下|想问一下|帮我查下|帮我查一下|帮我搜下|帮我搜一下|"
    r"查一下|搜一下|问下|问一下)\s*"
)

# 口语化后缀包装词（"是什么意思"、"啥梗"等）
_QUERY_WRAPPER_TRAILING_RE = re.compile(
    r"(?:到底)?(?:算|指)?(?:是)?(?:什么(?:东西|意思|玩意儿?|来着)?|啥(?:意思|东西)?|"
    r"指什么|是谁(?:啊|来着)?|谁来着|哪来的|什么梗|什么黑话|出处(?:是)?(?:哪里)?|"
    r"来源(?:是)?(?:哪里)?|怎么回事)\s*[?？!！.。]*$"
)

# 中文互联网梗/黑话线索词
_CHINESE_WEB_SLANG_HINT_RE = re.compile(
    r"(梗|黑话|外号|别称|绰号|简称|缩写|谐音|空耳|打错|错字|玩梗|出处|来源|什么意思|"
    r"什么东西|是什么|是谁|谁啊|谁来着|哪来的|怎么回事)"
)

_MAX_QUERY_CANDIDATES = 6
"""最多保留的候选查询数"""


@dataclass(slots=True)
class ContextualQueryRewrite:
    """查询改写结果

    Attributes:
        primary_query: 最适合首轮检索的查询
        query_candidates: 首轮失败后可依次尝试的候选查询
    """

    primary_query: str
    query_candidates: list[str]


def _normalize_text(text: Any) -> str:
    """标准化文本：合并空白、去回车"""
    return re.sub(r"\s+", " ", str(text or "").replace("\r", " ")).strip()


def _compact_query_text(text: Any) -> str:
    """压缩查询文本：去除口语包装词与尾部标点"""
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    normalized = _QUERY_WRAPPER_LEADING_RE.sub("", normalized).strip()
    normalized = _QUERY_WRAPPER_TRAILING_RE.sub("", normalized).strip()
    normalized = re.sub(r"[?？!！。]+$", "", normalized).strip()
    return normalized or _normalize_text(text)


def _normalized_anchor_text(text: Any) -> str:
    """提取归一化锚点文本：去标签、去标点、小写、截断"""
    normalized = _normalize_text(text)
    normalized = re.sub(r"^\[我\]:\s*", "", normalized)
    normalized = re.sub(r"\[[^\]]+\]", " ", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized).strip().lower()
    return normalized[:48]


def _has_anchor_overlap(left: str, right: str) -> bool:
    """判断两个锚点是否有子串重叠"""
    if len(left) < 2 or len(right) < 2:
        return False
    if left in right or right in left:
        return True
    max_span = min(6, len(left), len(right))
    for span in range(max_span, 1, -1):
        for index in range(0, len(left) - span + 1):
            if left[index : index + span] in right:
                return True
    return False


def _pick_recent_entity_anchor(
    *,
    history_new: str,
    history_last: str,
    quoted_message: str = "",
) -> str:
    """从最近对话中提取与最新一句相关的实体锚点

    参数:
        history_new: 最近对话文本
        history_last: 当前最新一句
        quoted_message: 引用消息

    返回:
        str: 实体锚点文本（无则空串）
    """
    latest = _normalized_anchor_text(history_last)
    if not latest:
        return ""

    candidates: list[str] = []
    if _normalize_text(quoted_message):
        candidates.append(_normalize_text(quoted_message))
    for line in reversed(str(history_new or "").splitlines()):
        cleaned = _normalize_text(line)
        if not cleaned or cleaned in candidates:
            continue
        candidates.append(cleaned)
        if len(candidates) >= 8:
            break

    for candidate in candidates:
        normalized_candidate = _normalized_anchor_text(candidate)
        if not normalized_candidate or normalized_candidate == latest:
            continue
        if _has_anchor_overlap(normalized_candidate, latest):
            return candidate
    return ""


def _dedupe_candidates(values: list[str], *, limit: int) -> list[str]:
    """去重候选词列表"""
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize_text(value)
        if not cleaned:
            continue
        key = _normalized_anchor_text(cleaned) or cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _looks_like_colloquial_query(text: Any) -> bool:
    """判断是否像口语化查询（梗/黑话/外号等）"""
    normalized = _normalize_text(text)
    compacted = _compact_query_text(normalized)
    if not compacted:
        return False
    if _CHINESE_WEB_SLANG_HINT_RE.search(normalized):
        return True
    if compacted != normalized:
        return True
    anchor_text = _normalized_anchor_text(compacted)
    if (
        2 <= len(anchor_text) <= 10
        and " " not in compacted
        and not any(
            token in normalized
            for token in (
                "最新", "今天", "现在", "多少", "怎么",
                "为什么", "教程", "攻略", "配置",
            )
        )
    ):
        return True
    return False


def _build_contextual_query_candidates(
    *,
    primary_query: str,
    recent_anchor: str = "",
    quoted_message: str = "",
    topic_hint: str = "",
) -> list[str]:
    """构建多候选查询词

    结合主查询、实体锚点、引用内容、话题提示生成候选词，
    口语化查询额外补出"梗/出处/来源/正式名称"变体。
    """
    base = _compact_query_text(primary_query) or _normalize_text(primary_query)
    anchor = _compact_query_text(recent_anchor) or _normalize_text(recent_anchor)
    quoted = _compact_query_text(quoted_message) or _normalize_text(quoted_message)
    topic = _compact_query_text(topic_hint) or _normalize_text(topic_hint)
    colloquial = _looks_like_colloquial_query(primary_query)

    candidates: list[str] = []
    if base:
        candidates.append(base)
    if anchor and base and not _has_anchor_overlap(
        _normalized_anchor_text(anchor), _normalized_anchor_text(base)
    ):
        candidates.append(f"{anchor} {base}")
    if quoted and base and not _has_anchor_overlap(
        _normalized_anchor_text(quoted), _normalized_anchor_text(base)
    ):
        candidates.append(f"{quoted} {base}")
    if topic and base and not _has_anchor_overlap(
        _normalized_anchor_text(topic), _normalized_anchor_text(base)
    ):
        candidates.append(f"{topic} {base}")
    if colloquial and base:
        candidates.extend([
            f"{base} 梗",
            f"{base} 出处",
            f"{base} 来源",
            f"{base} 正式名称",
        ])
    return _dedupe_candidates(candidates, limit=_MAX_QUERY_CANDIDATES)


def _choose_primary_query(
    *,
    history_last: str,
    recent_anchor: str = "",
    quoted_message: str = "",
    topic_hint: str = "",
) -> str:
    """选择主查询：口语化时补锚点前缀"""
    base = _compact_query_text(history_last) or _normalize_text(history_last)
    if not base:
        return ""
    if not _looks_like_colloquial_query(history_last):
        return base
    anchor = _compact_query_text(recent_anchor) or _normalize_text(recent_anchor)
    topic = _compact_query_text(topic_hint) or _normalize_text(topic_hint)
    quoted = _compact_query_text(quoted_message) or _normalize_text(quoted_message)
    for candidate in (anchor, quoted, topic):
        if candidate and not _has_anchor_overlap(
            _normalized_anchor_text(candidate), _normalized_anchor_text(base)
        ):
            return f"{candidate} {base}".strip()
    return base


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """从文本中解析JSON对象"""
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return None


def _normalize_str_list(value: Any, limit: int) -> list[str]:
    """将值归一化为去重字符串列表"""
    items: list[str] = []
    if isinstance(value, list):
        source = value
    elif isinstance(value, str):
        source = re.split(r"[；;\n]+", value)
    else:
        source = []
    for item in source:
        normalized = _normalize_text(item)
        if normalized and normalized not in items:
            items.append(normalized)
        if len(items) >= limit:
            break
    return items


def _fallback_rewrite(
    *,
    history_new: str,
    history_last: str,
    trigger_reason: str,
    quoted_message: str = "",
    topic_hint: str = "",
) -> ContextualQueryRewrite:
    """规则兜底改写：LLM不可用时仍能生成可用查询

    提取实体锚点、构建候选词、识别口语化梗。
    """
    colloquial_hint = _looks_like_colloquial_query(history_last)
    anchor = _pick_recent_entity_anchor(
        history_new=history_new,
        history_last=history_last,
        quoted_message=quoted_message,
    )
    clues = _normalize_str_list(
        [
            clue
            for clue in [
                anchor,
                quoted_message,
                *str(history_new or "").splitlines(),
            ]
            if _normalize_text(clue)
            and not str(clue).strip().startswith("[我]:")
        ],
        limit=4,
    )
    if _normalize_text(topic_hint):
        clues = _normalize_str_list([topic_hint, *clues], limit=4)
    primary_query = _choose_primary_query(
        history_last=history_last,
        recent_anchor=anchor,
        quoted_message=quoted_message,
        topic_hint=topic_hint,
    ) or (clues[0] if clues else "")
    query_candidates = _build_contextual_query_candidates(
        primary_query=primary_query,
        recent_anchor=anchor,
        quoted_message=quoted_message,
        topic_hint=topic_hint,
    )
    if colloquial_hint and primary_query:
        query_candidates = _dedupe_candidates(
            [
                *query_candidates,
                f"{primary_query} 梗",
                f"{primary_query} 出处",
                f"{primary_query} 来源",
            ],
            limit=_MAX_QUERY_CANDIDATES,
        )
    if not query_candidates:
        query_candidates = _normalize_str_list(
            [primary_query, *clues], limit=_MAX_QUERY_CANDIDATES
        )
    return ContextualQueryRewrite(
        primary_query=primary_query,
        query_candidates=query_candidates or (
            [primary_query] if primary_query else []
        ),
    )


def _coerce_rewrite_payload(
    payload: dict[str, Any] | None,
    *,
    history_new: str,
    history_last: str,
    trigger_reason: str,
    quoted_message: str = "",
    topic_hint: str = "",
) -> ContextualQueryRewrite:
    """将LLM返回的payload与规则兜底融合

    LLM返回的字段优先，缺失或无效时回退到规则结果。
    """
    fallback = _fallback_rewrite(
        history_new=history_new,
        history_last=history_last,
        trigger_reason=trigger_reason,
        quoted_message=quoted_message,
        topic_hint=topic_hint,
    )
    if not isinstance(payload, dict):
        return fallback

    primary_query = (
        _normalize_text(payload.get("primary_query", ""))
        or fallback.primary_query
    )
    query_candidates = _normalize_str_list(
        payload.get("query_candidates", []), _MAX_QUERY_CANDIDATES
    )
    if primary_query and primary_query not in query_candidates:
        query_candidates.insert(0, primary_query)
    if not query_candidates and fallback.query_candidates:
        query_candidates = list(fallback.query_candidates)

    return ContextualQueryRewrite(
        primary_query=primary_query,
        query_candidates=query_candidates,
    )


async def contextual_query_rewriter(
    *,
    llm=None,
    history_new: str,
    history_last: str,
    trigger_reason: str = "",
    images: list[str] | None = None,
    quoted_message: str = "",
    topic_hint: str = "",
) -> ContextualQueryRewrite:
    """检索意图改写主入口

    先用规则兜底生成基础查询，再用LLM规划高质量检索计划，
    LLM输出经 _coerce_rewrite_payload 与规则结果融合，
    保证LLM失败时仍有可用查询。

    参数:
        llm: LLM助手，None时用模块单例
        history_new: 最近对话文本
        history_last: 当前最新一句
        trigger_reason: 触发原因
        images: 图片URL列表
        quoted_message: 引用消息文本
        topic_hint: 群聊话题提示

    返回:
        ContextualQueryRewrite: 改写结果
    """
    recent_anchor = _pick_recent_entity_anchor(
        history_new=history_new,
        history_last=history_last,
        quoted_message=quoted_message,
    )
    system_prompt = (
        "你是检索意图规划器。"
        "你的任务是在调用任何联网、资源、Wiki、攻略、视觉识别类工具之前，"
        "先基于最近对话、引用内容、最新一句和图片生成一个高质量检索计划。"
        "不要直接复读最后一句口语补充，不要把无信息尾句当搜索词。"
        "如果最新一句里的称呼、别名或实体，和最近几轮刚提过的对象高度相似，"
        "优先把它当成会话内同一对象，"
        "不要擅自跳到更常见但无上下文依据的百科实体。"
        "遇到中文互联网梗、黑话、缩写、别称、外号、谐音梗、空耳、错别字时，"
        "要主动补出更正式的实体名、出处、原句或作品线索，"
        "并把它们放进 query_candidates。"
        "只输出 JSON，不要输出解释、markdown 或代码块。\n\n"
        "JSON 字段：\n"
        "{\n"
        '  "primary_query": "最适合作为首轮检索的查询",\n'
        '  "query_candidates": ["首轮失败后可依次尝试的候选查询"]\n'
        "}"
    )
    user_text = (
        f"最近对话：\n{str(history_new or '').strip() or '(无最近消息)'}\n\n"
        f"当前最新一句：\n{str(history_last or '').strip() or '(空)'}\n\n"
        f"最近会话锚点：\n{recent_anchor or '(无)'}\n\n"
        f"群聊近期话题：\n{str(topic_hint or '').strip() or '(无)'}\n\n"
        f"引用内容：\n{str(quoted_message or '').strip() or '(无)'}\n\n"
        f"触发原因：\n{str(trigger_reason or '').strip() or '(无)'}\n\n"
        f"当前是否带图：{'是' if images else '否'}"
    )
    try:
        use_llm = llm or llm_helper
        role = model_router.resolve(ROLE_INTENT)
        options = role.apply_to_options(
            {"max_tokens": 600, "reasoning_enabled": False}
        )
        _, response = await use_llm.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            model=role.model or None,
            options=options,
            provider_name=role.provider or None,
        )
    except Exception as e:
        logger.debug(f"查询改写LLM调用失败，用规则兜底: {e}", command="AI")
        response = ""

    payload = _parse_json_object(response)
    return _coerce_rewrite_payload(
        payload,
        history_new=history_new,
        history_last=history_last,
        trigger_reason=trigger_reason,
        quoted_message=quoted_message,
        topic_hint=topic_hint,
    )


__all__ = [
    "ContextualQueryRewrite",
    "contextual_query_rewriter",
]
