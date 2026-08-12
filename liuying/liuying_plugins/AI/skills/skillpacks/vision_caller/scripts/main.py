"""视觉能力诊断技能入口"""

from typing import Any

from . import impl


async def run(prefer_model: str = "") -> str:
    """CLI调试入口

    参数:
        prefer_model: 优先探测的模型名

    返回:
        str: 能力描述
    """
    return await impl.check_capability(prefer_model=prefer_model)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_caller_tools(runtime)
