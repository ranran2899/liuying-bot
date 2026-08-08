"""新闻查询技能入口

参考参考插件 skillpacks 的 main.py 设计：
- build_tools(runtime) 接收 SkillRuntime 参数，返回 AgentTool 列表
- run(**kwargs) 提供 CLI 调试入口
"""

from typing import Any

from . import impl


async def run(category: str = "general") -> str:
    """CLI调试入口

    参数:
        category: 新闻分类

    返回:
        str: 新闻摘要
    """
    return await impl.query_news(category=category)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_news_tool(runtime)]
