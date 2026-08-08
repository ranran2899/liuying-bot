"""天气查询技能入口

参考参考插件 skillpacks 的 main.py 设计。
"""

from typing import Any

from . import impl


async def run(city: str) -> str:
    """CLI调试入口

    参数:
        city: 城市名

    返回:
        str: 天气信息
    """
    return await impl.query_weather(city=city)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_weather_tool(runtime)]
