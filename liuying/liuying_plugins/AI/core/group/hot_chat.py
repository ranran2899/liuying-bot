"""热聊保护

热聊时降低随机发言概率，避免打断用户讨论。
基于近期消息频率检测热聊状态。
"""

from collections import defaultdict, deque
from datetime import datetime
import random

from liuying.utils.log import logger

from ...config import get_config

__all__ = ["HotChatProtector", "hot_chat_protector"]


_HOT_WINDOW_SECONDS: int = 30
"""热聊检测时间窗口（秒）"""

_HOT_MESSAGE_THRESHOLD: int = 10
"""热聊消息数阈值"""

_SUPPRESS_RATIO: float = 0.8
"""热聊时抑制随机发言的概率"""


class HotChatProtector:
    """热聊保护

    基于近期消息频率检测热聊状态。
    热聊时降低随机发言概率，避免打断用户讨论。
    """

    def __init__(self) -> None:
        """初始化热聊保护"""
        self._timestamps: dict[
            str, deque[float]
        ] = defaultdict(lambda: deque(maxlen=100))
        """群ID -> 近期消息时间戳队列"""

    def _get_window_seconds(self) -> int:
        """获取热聊检测时间窗口

        返回:
            int: 时间窗口（秒）
        """
        value = get_config(
            "HOT_CHAT_WINDOW_SECONDS",
            _HOT_WINDOW_SECONDS,
        )
        try:
            return max(5, int(value))
        except (TypeError, ValueError):
            return _HOT_WINDOW_SECONDS

    def _get_threshold(self) -> int:
        """获取热聊消息数阈值

        返回:
            int: 消息数阈值
        """
        value = get_config(
            "HOT_CHAT_MESSAGE_THRESHOLD",
            _HOT_MESSAGE_THRESHOLD,
        )
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            return _HOT_MESSAGE_THRESHOLD

    def _get_suppress_ratio(self) -> float:
        """获取抑制概率

        返回:
            float: 抑制概率（0-1）
        """
        value = get_config(
            "HOT_CHAT_SUPPRESS_RATIO", _SUPPRESS_RATIO
        )
        try:
            ratio = float(value)
            return max(0.0, min(1.0, ratio))
        except (TypeError, ValueError):
            return _SUPPRESS_RATIO

    def _count_recent(
        self, group_id: str
    ) -> int:
        """统计时间窗口内的消息数

        参数:
            group_id: 群组ID

        返回:
            int: 近期消息数
        """
        timestamps = self._timestamps.get(group_id)
        if not timestamps:
            return 0
        cutoff = datetime.now().timestamp() - (
            self._get_window_seconds()
        )
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        return len(timestamps)

    def record_message(self, group_id: str) -> None:
        """记录一条群消息

        参数:
            group_id: 群组ID
        """
        if not group_id:
            return
        self._timestamps[group_id].append(
            datetime.now().timestamp()
        )

    def is_hot_chat(self, group_id: str) -> bool:
        """检测群是否处于热聊状态

        参数:
            group_id: 群组ID

        返回:
            bool: 是否热聊
        """
        if not group_id:
            return False
        count = self._count_recent(group_id)
        threshold = self._get_threshold()
        if count >= threshold:
            logger.debug(
                f"群 {group_id} 处于热聊状态: "
                f"{count}条消息/{self._get_window_seconds()}秒",
                command="AI",
            )
            return True
        return False

    def should_suppress_random(
        self, group_id: str
    ) -> bool:
        """判断是否应抑制随机发言

        热聊时按抑制概率返回True。

        参数:
            group_id: 群组ID

        返回:
            bool: 是否抑制
        """
        if not group_id:
            return False
        if not self.is_hot_chat(group_id):
            return False
        return random.random() < self._get_suppress_ratio()


hot_chat_protector = HotChatProtector()
"""热聊保护单例"""
