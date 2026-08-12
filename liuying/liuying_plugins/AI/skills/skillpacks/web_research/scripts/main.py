"""并发深度检索技能入口"""

from typing import Any

from . import impl


async def run(
    question: str, queries: list[str] | None = None
) -> str:
    """CLI调试入口

    参数:
        question: 要研究的问题
        queries: 子查询列表

    返回:
        str: 汇总结论
    """
    return await impl.research(question=question, queries=queries)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_research_tool(runtime)]
