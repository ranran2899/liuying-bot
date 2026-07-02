"""拍一拍回复

被拍后自动拍回或回复，基于概率决定行为：
拍回 / 回复 / 忽略。
"""

import random
from typing import ClassVar

from liuying.utils.log import logger

from ..config import get_config


class PokeHandler:
    """拍一拍处理器

    基于概率决定被拍后的行为：拍回、回复或忽略。
    由 POKE_BACK_ENABLED 开关统一控制。
    """

    _POKE_BACK_PROB = 0.5
    """拍回概率"""

    _REPLY_PROB = 0.3
    """回复概率（在拍回之后的剩余概率中占比）"""

    _REPLY_TEXTS: ClassVar[list[str]] = [
        "干嘛戳我",
        "别戳啦",
        "再戳生气了",
        "怎么了呀",
        "戳坏了你赔",
    ]
    """回复文本池"""

    async def handle_poke(
        self, user_id: str, group_id: str
    ) -> dict:
        """处理被拍事件

        基于 _POKE_BACK_PROB 与 _REPLY_PROB 决策行为：
        拍回 / 回复 / 忽略。POKE_BACK_ENABLED 关闭时直接忽略。

        参数:
            user_id: 拍人的用户ID
            group_id: 群组ID，空串表示私聊

        返回:
            dict: 含 action(poke_back/reply/ignore) 与 text
        """
        if not get_config("POKE_BACK_ENABLED", True):
            return {"action": "ignore", "text": ""}

        roll = random.random()
        if roll < self._POKE_BACK_PROB:
            action = "poke_back"
            text = ""
        elif roll < self._POKE_BACK_PROB + self._REPLY_PROB:
            action = "reply"
            text = random.choice(self._REPLY_TEXTS)
        else:
            action = "ignore"
            text = ""

        logger.debug(
            f"拍一拍处理 user={user_id} group={group_id} "
            f"-> action={action}",
            command="AI",
        )
        return {"action": action, "text": text}


poke_handler = PokeHandler()
"""拍一拍处理器单例"""
