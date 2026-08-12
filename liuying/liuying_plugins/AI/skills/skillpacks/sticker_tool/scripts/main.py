"""表情包技能入口"""

from typing import Any

from . import impl


async def run(mood: str = "", context: str = "") -> str:
    """CLI调试入口

    参数:
        mood: 期望的心情标签
        context: 当前语境

    返回:
        str: 选中结果描述
    """
    return await impl.select_sticker(mood=mood, context=context)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_sticker_tools(runtime)
