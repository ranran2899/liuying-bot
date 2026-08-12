"""用户画像技能入口"""

from typing import Any

from . import impl


async def run(fact: str = "") -> str:
    """CLI调试入口

    传入 fact 时写入记忆，为空时返回当前用户画像。

    参数:
        fact: 要记住的事实

    返回:
        str: 操作结果或画像文本
    """
    if fact.strip():
        return await impl.remember_fact(fact)
    return await impl.get_profile()


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_profile_tools(runtime)
