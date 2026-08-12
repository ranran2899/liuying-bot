"""ACG检索技能入口"""

from typing import Any

from . import impl


async def run(name: str, kind: str = "auto") -> str:
    """CLI调试入口

    参数:
        name: 作品名或角色名
        kind: 查询类型

    返回:
        str: 检索结果
    """
    return await impl.resolve(name=name, kind=kind)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_acg_tool(runtime)]
