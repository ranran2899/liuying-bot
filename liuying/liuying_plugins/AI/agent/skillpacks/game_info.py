"""游戏信息查询技能

通过联网搜索提供游戏信息查询能力。
"""

from liuying.utils.log import logger

from ...core.llm import llm_helper

_MAX_GAME_RESULTS = 4
"""游戏信息查询最大结果数"""


async def get_game_info(game: str) -> str:
    """查询游戏信息

    通过 llm_helper.web_search 查询指定游戏的信息。

    参数:
        game: 游戏名

    返回:
        str: 游戏信息文本
    """
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
        logger.warning(
            f"游戏信息查询失败: {e}", command="AI", e=e
        )
        return f"游戏信息查询失败: {e}"
