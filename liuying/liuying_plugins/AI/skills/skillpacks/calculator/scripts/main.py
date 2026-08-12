"""数学计算技能入口"""

from typing import Any

from . import impl


async def run(expression: str) -> str:
    """CLI调试入口

    参数:
        expression: 数学表达式

    返回:
        str: 计算结果
    """
    return impl.calculate(expression)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_calculator_tool(runtime)]
