"""图像内容分析实现

把 core/vision 的图片/GIF 摘要能力暴露成 Agent 工具：
按魔数自动分流 GIF 与静态图，多图时并发拉取并分析，
把 N 轮串行往返压成 1 轮。

本技能只做「看图说话」，视觉 provider 可用性诊断在 vision_caller，
表情包挑选在 sticker_tool，不在此处重复实现。
"""

import asyncio
from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_IMAGE,
    INTENT_TAG_NETWORK,
    LATENCY_CLASS_SLOW,
)
from liuying.liuying_plugins.AI.agent.tools import AgentTool
from liuying.liuying_plugins.AI.core.vision import (
    summarize_gif,
    summarize_image,
)
from liuying.liuying_plugins.AI.skills.media import (
    fetch_image,
    fetch_images,
    is_gif,
)

_MAX_IMAGES = 3
"""单次最多分析的图片数，超出截断以控制视觉模型开销"""

_ANALYZE_TIMEOUT = 45.0
"""单张图片分析超时（秒）"""

_QUESTION_LIMIT = 200
"""用户问题截断长度，防止提示词注入过长内容"""

_BASE_PROMPT = (
    "请用中文客观描述这张图片的内容。"
    "包含主体、场景、可见文字（如有）与整体氛围，"
    "不超过120字。只描述看到的内容，禁止推测和编造。"
)
"""无具体问题时的默认描述提示"""


def build_prompt(question: str) -> str:
    """构造视觉分析提示词

    参数:
        question: 用户的具体问题，可为空

    返回:
        str: 提示词
    """
    question = (question or "").strip()[:_QUESTION_LIMIT]
    if not question:
        return _BASE_PROMPT
    return (
        f"请看这张图片并回答问题：{question}\n"
        "只依据图片可见内容回答，看不出来就直说看不出来，"
        "禁止编造。用中文，不超过120字。"
    )


async def _analyze_bytes(
    data: bytes,
    mime: str,
    prompt: str,
    llm_helper: Any,
) -> str:
    """分析单张图片字节

    参数:
        data: 图片二进制数据
        mime: MIME类型
        prompt: 提示词
        llm_helper: LLM助手实例

    返回:
        str: 描述文本或失败原因
    """
    if is_gif(data):
        result = await summarize_gif(data, llm_helper)
        if not result.success:
            return f"动图分析失败：{result.error or '未知原因'}"
        return (
            f"{result.summary}"
            f"（动图，共{result.frame_count}帧，"
            f"采样{result.sampled_frames}帧）"
        )

    summary = await summarize_image(
        data, mime, llm_helper, prompt=prompt
    )
    if not summary.success:
        return f"图片分析失败：{summary.error or '未知原因'}"
    return summary.description


async def analyze_image(
    image_url: str,
    question: str = "",
    llm_helper: Any = None,
) -> str:
    """分析单张图片

    参数:
        image_url: 图片URL
        question: 针对图片的具体问题
        llm_helper: LLM助手实例

    返回:
        str: 分析结论或不可用原因
    """
    if llm_helper is None:
        return "图像分析不可用：未配置LLM助手"

    data, mime, error = await fetch_image(image_url)
    if error:
        return f"图像分析失败：{error}"

    prompt = build_prompt(question)
    # 视觉模型属外部不确定依赖，超时与异常统一降级为可读文本，
    # 避免异常穿透打断 Agent 回合。
    try:
        async with asyncio.timeout(_ANALYZE_TIMEOUT):
            return await _analyze_bytes(
                data, mime, prompt, llm_helper
            )
    except TimeoutError:
        return "图像分析超时，请稍后重试"
    except Exception as e:
        return f"图像分析异常：{type(e).__name__}"


async def analyze_images(
    image_urls: list[str],
    question: str = "",
    llm_helper: Any = None,
) -> str:
    """并发分析多张图片

    参数:
        image_urls: 图片URL列表
        question: 针对全部图片的共同问题
        llm_helper: LLM助手实例

    返回:
        str: 逐张分析结论汇总
    """
    if llm_helper is None:
        return "图像分析不可用：未配置LLM助手"

    fetched = await fetch_images(image_urls or [], _MAX_IMAGES)
    if not fetched:
        return "请提供至少一个有效的图片URL"

    prompt = build_prompt(question)

    async def _one(data: bytes, mime: str, error: str) -> str:
        """单张分析并吸收异常"""
        if error:
            return f"获取失败：{error}"
        try:
            async with asyncio.timeout(_ANALYZE_TIMEOUT):
                return await _analyze_bytes(
                    data, mime, prompt, llm_helper
                )
        except TimeoutError:
            return "分析超时"
        except Exception as e:
            return f"分析异常：{type(e).__name__}"

    descriptions = await asyncio.gather(
        *(
            _one(data, mime, error)
            for _, data, mime, error in fetched
        )
    )
    if len(descriptions) == 1:
        return descriptions[0]
    return "\n".join(
        f"图{index}：{text}"
        for index, text in enumerate(descriptions, start=1)
    )


def build_vision_tools(runtime: Any) -> list[AgentTool]:
    """构建图像分析工具集

    参数:
        runtime: SkillRuntime 实例

    返回:
        list[AgentTool]: 工具列表
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _analyze_one(
        image_url: str, question: str = ""
    ) -> str:
        """单图分析handler

        参数:
            image_url: 图片URL
            question: 具体问题

        返回:
            str: 分析结论
        """
        return await analyze_image(
            image_url=image_url,
            question=question,
            llm_helper=llm_helper,
        )

    async def _analyze_many(
        image_urls: list[str], question: str = ""
    ) -> str:
        """多图分析handler

        参数:
            image_urls: 图片URL列表
            question: 共同问题

        返回:
            str: 分析结论汇总
        """
        return await analyze_images(
            image_urls=image_urls,
            question=question,
            llm_helper=llm_helper,
        )

    return [
        AgentTool(
            name="analyze_image",
            description=(
                "看图并回答问题。用户发了图片、或需要识别图中"
                "文字/物体/场景时用本工具。GIF动图会自动采样关键帧。"
                "只有一张图时用本工具，多张图用 analyze_images"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "图片的完整URL",
                    },
                    "question": {
                        "type": "string",
                        "description": (
                            "针对图片的具体问题；"
                            "只想知道图里有什么时留空"
                        ),
                    },
                },
                "required": ["image_url"],
            },
            func=_analyze_one,
            intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_SLOW,
            requires_network=True,
            requires_image=True,
            evidence_kind=EVIDENCE_KIND_TOOL,
            per_session_quota=4,
        ),
        AgentTool(
            name="analyze_images",
            description=(
                f"一次并发分析多张图片，最多{_MAX_IMAGES}张。"
                "需要对比多张图、或用户连发了几张图时用本工具，"
                "不要多次调用 analyze_image"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "image_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            f"图片URL列表，最多{_MAX_IMAGES}个"
                        ),
                    },
                    "question": {
                        "type": "string",
                        "description": "针对全部图片的共同问题",
                    },
                },
                "required": ["image_urls"],
            },
            func=_analyze_many,
            intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_NETWORK],
            latency_class=LATENCY_CLASS_SLOW,
            requires_network=True,
            requires_image=True,
            evidence_kind=EVIDENCE_KIND_TOOL,
            per_session_quota=2,
        ),
    ]
