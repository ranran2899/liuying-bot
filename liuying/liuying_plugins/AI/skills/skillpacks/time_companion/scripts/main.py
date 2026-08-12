"""日期推算技能入口"""

from typing import Any

from . import impl


async def run(target: str) -> str:
    """CLI调试入口，计算距目标日期天数

    参数:
        target: 目标日期文本

    返回:
        str: 倒计时描述
    """
    return impl.days_until(target)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return impl.build_time_tools(runtime)
