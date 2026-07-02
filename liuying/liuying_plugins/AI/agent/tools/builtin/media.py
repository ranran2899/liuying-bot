"""媒体类内置工具

图片生成。
"""

from ....core.llm import llm_helper
from ...runtime.constants import (
    INTENT_TAG_IMAGE,
    INTENT_TAG_NETWORK,
    LATENCY_CLASS_SLOW,
)
from ..decorators import register_tool


@register_tool(
    name="image_generate",
    description="根据文本提示生成图片，适用于需要绘图或视觉创作的场景",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片生成提示词",
            },
            "size": {
                "type": "string",
                "description": "图片尺寸，默认1024x1024",
                "default": "1024x1024",
            },
        },
        "required": ["prompt"],
    },
    intent_tags=[INTENT_TAG_IMAGE, INTENT_TAG_NETWORK],
    latency_class=LATENCY_CLASS_SLOW,
    requires_network=True,
    metadata={"output_kind": "image_url"},
)
async def image_generate(
    prompt: str, size: str = "1024x1024"
) -> str:
    """生成图片

    参数:
        prompt: 生成提示
        size: 尺寸

    返回:
        str: 图片URL或失败提示
    """
    try:
        urls = await llm_helper.image_generate(prompt, size=size, n=1)
        if urls:
            return urls[0]
        return "图片生成失败，未返回URL"
    except Exception as e:
        return f"图片生成失败: {e}"
