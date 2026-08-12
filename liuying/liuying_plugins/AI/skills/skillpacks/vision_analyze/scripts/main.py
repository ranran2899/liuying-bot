"""图像内容分析技能入口"""

from typing import Any

from . import impl


async def run(image_url: str, question: str = "") -> str:
    """CLI调试入口

    参数:
        image_url: 图片URL
        question: 针对图片的问题

    返回:
        str: 分析结论
    """
    return await impl.analyze_image(
        image_url=image_url, question=question
    )


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_vision_tools(runtime)
