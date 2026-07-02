"""同伴感知

检测群内其他机器人，避免互相对话形成死循环。
基于消息特征检测（命令前缀、机器人标识）。
"""

import re

from liuying.utils.log import logger

from ...config import get_config

__all__ = ["PeerAwareness", "peer_awareness"]


_BOT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*[/.#!](\w+)"),
    re.compile(r"\[CQ:at,qq=\d+\].*?bot", re.IGNORECASE),
    re.compile(r"我是(?:机器人|bot|AI助手)", re.IGNORECASE),
    re.compile(
        r"(?:本人|本机|本bot|本机器人)(?:是|为)(?:机器人|bot)",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:bot|robot|机器人)[：:]", re.IGNORECASE),
)
"""机器人消息特征正则元组"""


_BOT_NAME_HINTS: tuple[str, ...] = (
    "bot",
    "机器人",
    "robot",
)
"""用户ID中可能的机器人标识"""


class PeerAwareness:
    """同伴感知

    检测群内其他机器人，避免互相对话。
    基于消息特征（命令前缀、机器人标识）检测。
    """

    def __init__(self) -> None:
        """初始化同伴感知"""
        self._known_bots: set[str] = set()
        """已知机器人用户ID集合"""

    def _load_known_bots(self) -> set[str]:
        """从配置加载已知机器人ID

        返回:
            set[str]: 已知机器人ID集合
        """
        configured = get_config("KNOWN_BOT_USER_IDS", [])
        if not configured:
            return set()
        if isinstance(configured, str):
            configured = configured.split(",")
        result: set[str] = set()
        for item in configured:
            item_str = str(item).strip()
            if item_str:
                result.add(item_str)
        return result

    def detect_bot(
        self, message: str, user_id: str
    ) -> bool:
        """检测消息是否来自机器人

        基于消息特征和已知机器人列表综合判断。

        参数:
            message: 消息文本
            user_id: 用户ID

        返回:
            bool: 是否为机器人消息
        """
        if not user_id:
            return False
        if self.is_known_bot(user_id):
            return True

        if not message:
            return False

        for pattern in _BOT_PATTERNS:
            if pattern.search(message):
                logger.debug(
                    f"用户 {user_id} 消息命中机器人特征，"
                    f"自动注册为机器人",
                    command="AI",
                )
                self.register_bot(user_id)
                return True
        return False

    def is_known_bot(self, user_id: str) -> bool:
        """检查用户是否为已知机器人

        参数:
            user_id: 用户ID

        返回:
            bool: 是否为已知机器人
        """
        if not user_id:
            return False
        if user_id in self._known_bots:
            return True
        if user_id in self._load_known_bots():
            return True
        uid_lower = user_id.lower()
        for hint in _BOT_NAME_HINTS:
            if hint in uid_lower:
                return True
        return False

    def register_bot(self, user_id: str) -> None:
        """注册用户为机器人

        参数:
            user_id: 用户ID
        """
        if not user_id:
            return
        if user_id not in self._known_bots:
            self._known_bots.add(user_id)
            logger.debug(
                f"注册用户 {user_id} 为机器人",
                command="AI",
            )


peer_awareness = PeerAwareness()
"""同伴感知单例"""
