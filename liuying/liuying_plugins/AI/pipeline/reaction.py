"""表情表态

沉默场景（NO_REPLY）时贴表情代替沉默，
支持QQ表情ID和emoji，基于情绪和概率决定是否表态。
"""

import random
from typing import ClassVar

from liuying.utils.log import logger

from ..config import get_config


class ReactionHandler:
    """表情表态处理器

    沉默场景以表情代替沉默，基于情绪和概率决策。
    表情映射同时支持QQ表情ID（用于emoji_react API）
    与emoji ID（备用）。
    """

    _REACTION_MAP: ClassVar[dict[str, tuple[int, int]]] = {
        "happy": (178, 21),
        "thinking": (0, 13),
        "approve": (76, 32),
        "surprise": (86, 27),
    }
    """情绪到表情ID映射：情绪 -> (QQ表情ID, emoji ID)"""

    _DEFAULT_EMOTION = "thinking"
    """未匹配情绪时的默认表情"""

    async def should_react(self, emotion: str) -> bool:
        """决策是否进行表情表态

        基于 REACTION_ENABLED 开关与 REACTION_PROBABILITY
        概率共同决定。沉默场景下由调用方传入情绪标签。

        参数:
            emotion: 情绪标签（happy/thinking/approve/surprise）

        返回:
            bool: 是否进行表情表态
        """
        if not get_config("REACTION_ENABLED", True):
            return False
        probability = get_config("REACTION_PROBABILITY", 0.15)
        if probability <= 0:
            return False
        decision = random.random() < probability
        logger.debug(
            f"表情表态决策 emotion={emotion} "
            f"prob={probability} -> {decision}",
            command="AI",
        )
        return decision

    def get_reaction_id(self, emotion: str) -> int:
        """获取情绪对应的QQ表情ID

        未匹配情绪时回退到默认表情ID。

        参数:
            emotion: 情绪标签（happy/thinking/approve/surprise）

        返回:
            int: QQ表情ID
        """
        mapping = self._REACTION_MAP.get(emotion)
        if mapping is None:
            mapping = self._REACTION_MAP[self._DEFAULT_EMOTION]
        return mapping[0]

    def get_emoji_id(self, emotion: str) -> int:
        """获取情绪对应的emoji ID

        未匹配情绪时回退到默认emoji ID。

        参数:
            emotion: 情绪标签（happy/thinking/approve/surprise）

        返回:
            int: emoji ID
        """
        mapping = self._REACTION_MAP.get(emotion)
        if mapping is None:
            mapping = self._REACTION_MAP[self._DEFAULT_EMOTION]
        return mapping[1]


reaction_handler = ReactionHandler()
"""表情表态处理器单例"""
