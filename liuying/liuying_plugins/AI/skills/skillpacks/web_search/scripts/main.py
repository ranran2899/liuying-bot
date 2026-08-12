"""视觉线索增强检索技能入口"""

from typing import Any

from . import impl


async def run(
    query: str, image_urls: list[str] | None = None
) -> str:
    """CLI调试入口

    参数:
        query: 查询词
        image_urls: 图片URL列表

    返回:
        str: 检索结果
    """
    return await impl.visual_search(
        query=query, image_urls=image_urls
    )


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_search_tools(runtime)
