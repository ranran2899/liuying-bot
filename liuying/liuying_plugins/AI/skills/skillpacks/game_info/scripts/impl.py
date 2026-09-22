"""游戏信息查询实现

通过 runtime.llm_helper.web_search 实现免配置游戏信息查询。
"""

from typing import Any

from liuying.liuying_plugins.AI.tools import AgentTool

_MAX_GAME_RESULTS = 4
"""游戏信息查询最大结果数"""


async def get_game_info(
    game: str,
    llm_helper: Any = None,
) -> str:
    """查询游戏信息

    通过 llm_helper.web_search 查询指定游戏的信息。

    参数:
        game: 游戏名
        llm_helper: LLM助手实例

    返回:
        str: 游戏信息文本
    """
    if llm_helper is None:
        return "游戏信息查询不可用：未配置LLM助手"
    if not game or not game.strip():
        return "请提供游戏名"
    game = game.strip()
    keyword = f"{game} 游戏 攻略 介绍"
    try:
        results = await llm_helper.web_search(
            keyword, count=_MAX_GAME_RESULTS
        )
        if not results:
            return f"未查询到 {game} 的游戏信息"
        lines: list[str] = [f"{game} 游戏信息:"]
        for item in results:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            url = item.get("url", "")
            if title:
                lines.append(f"- {title}")
            if snippet:
                lines.append(f"  {snippet}")
            if url:
                lines.append(f"  URL: {url}")
        return "\n".join(lines)
    except Exception as e:
        return f"游戏信息查询失败: {e}"


def build_game_info_tool(runtime: Any) -> AgentTool:
    """构建游戏信息查询工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: 游戏信息查询工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(game: str) -> str:
        """游戏信息查询handler

        参数:
            game: 游戏名

        返回:
            str: 游戏信息
        """
        return await get_game_info(
            game=game, llm_helper=llm_helper
        )

    return AgentTool(
        name="get_game_info",
        description="查询游戏信息（攻略/介绍）",
        parameters={
            "type": "object",
            "properties": {
                "game": {
                    "type": "string",
                    "description": "游戏名",
                },
            },
            "required": ["game"],
        },
        func=_handler,
    )
