"""日期时间查询技能入口

参考参考插件 skillpacks 的 main.py 设计。
"""

from typing import Any

from . import impl


async def run(timezone: str = "Asia/Shanghai") -> str:
    """CLI调试入口

    参数:
        timezone: 时区名

    返回:
        str: 当前时间描述
    """
    return impl.get_current_datetime_info(timezone)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_datetime_tool(runtime)]
