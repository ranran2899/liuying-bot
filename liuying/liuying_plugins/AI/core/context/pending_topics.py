"""待处理话题队列

话题延续的待处理队列。
存储待跟进的话题，供后续主动消息使用。
基于内存字典+TTL过期清理。
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from liuying.utils.log import logger

__all__ = ["PendingTopicQueue", "pending_topics"]


@dataclass(slots=True)
class _TopicEntry:
    """话题条目

    Attributes:
        topic: 话题文本
        expire_at: 过期时间
    """

    topic: str
    expire_at: datetime


class PendingTopicQueue:
    """待处理话题队列

    按群存储待跟进话题，供后续主动消息使用。
    基于内存字典+TTL，过期自动清理。
    """

    _DEFAULT_TTL_HOURS: int = 24
    """默认TTL（小时）"""

    _MAX_QUEUE_SIZE: int = 20
    """单群队列最大长度"""

    def __init__(self) -> None:
        """初始化待处理话题队列"""
        self._queues: dict[str, deque[_TopicEntry]] = {}
        """群ID -> 话题队列"""

    def _get_queue(
        self, group_id: str
    ) -> deque[_TopicEntry]:
        """获取群话题队列，并清理过期项

        参数:
            group_id: 群组ID

        返回:
            deque[_TopicEntry]: 话题队列
        """
        queue = self._queues.setdefault(
            group_id, deque(maxlen=self._MAX_QUEUE_SIZE)
        )
        self._prune_expired(queue)
        return queue

    def _prune_expired(
        self, queue: deque[_TopicEntry]
    ) -> None:
        """清理队列中过期话题

        参数:
            queue: 话题队列
        """
        now = datetime.now()
        while queue and queue[0].expire_at <= now:
            expired = queue.popleft()
            logger.debug(
                f"话题过期清理: {expired.topic[:30]}",
                command="AI",
            )

    def add(
        self,
        group_id: str,
        topic: str,
        ttl_hours: int = _DEFAULT_TTL_HOURS,
    ) -> None:
        """添加待处理话题

        参数:
            group_id: 群组ID
            topic: 话题文本
            ttl_hours: 存活时间（小时）
        """
        if not group_id or not topic:
            return
        queue = self._get_queue(group_id)
        expire_at = datetime.now() + timedelta(
            hours=max(1, ttl_hours)
        )
        queue.append(_TopicEntry(topic=topic, expire_at=expire_at))
        logger.debug(
            f"群 {group_id} 添加待处理话题: "
            f"{topic[:30]}，TTL {ttl_hours}小时",
            command="AI",
        )

    def pop(self, group_id: str) -> str | None:
        """弹出最早的有效话题

        参数:
            group_id: 群组ID

        返回:
            str | None: 话题文本，无则None
        """
        if not group_id:
            return None
        queue = self._get_queue(group_id)
        if not queue:
            return None
        entry = queue.popleft()
        logger.debug(
            f"群 {group_id} 弹出话题: {entry.topic[:30]}",
            command="AI",
        )
        return entry.topic

    def peek(self, group_id: str) -> str | None:
        """查看最早的有效话题（不弹出）

        参数:
            group_id: 群组ID

        返回:
            str | None: 话题文本，无则None
        """
        if not group_id:
            return None
        queue = self._get_queue(group_id)
        if not queue:
            return None
        return queue[0].topic


pending_topics = PendingTopicQueue()
"""待处理话题队列单例"""
