"""游戏信息查询技能入口

参考参考插件 skillpacks 的 main.py 设计。
"""

from typing import Any

from . import impl


async def run(game: str) -> str:
    """CLI调试入口

    参数:
        game: 游戏名

    返回:
        str: 游戏信息
    """
    return await impl.get_game_info(game=game)


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_game_info_tool(runtime)]
