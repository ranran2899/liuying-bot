"""复读跟随

检测群内复读行为，决定是否跟随。
- RepeatFollow：基于TTL缓存统计相同消息出现次数，达到阈值时触发跟随。
- RepeatTracker：基于滑动窗口与字符集相似度，跟踪群内复读上下文，
  供群社交服务决策是否跟随复读。
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

from liuying.utils.log import logger

from ...config import get_config

__all__ = [
    "RepeatContext",
    "RepeatFollow",
    "RepeatTracker",
    "normalize_message",
    "repeat_follow",
]


# ===== RepeatFollow：TTL 计数模式 =====

_FOLLOW_THRESHOLD: int = 3
"""触发跟随的发送人数阈值"""

_TTL_SECONDS: int = 120
"""复读检测TTL（秒）"""

_MAX_MESSAGE_LEN: int = 50
"""参与复读检测的最大消息长度"""


def normalize_message(
    text: str, max_len: int = _MAX_MESSAGE_LEN
) -> str:
    """文本归一化（用于复读检测与相似度计算）

    参数:
        text: 原始文本
        max_len: 最大长度截断

    返回:
        str: 归一化后的文本
    """
    if not text:
        return ""
    cleaned = re.sub(r"\s+", "", text.lower())
    cleaned = re.sub(r"[^\w\u4e00-\u9fa5]+", "", cleaned)
    return cleaned[:max_len]


class _RepeatEntry:
    """复读计数条目

    Attributes:
        participants: 已发送该消息的用户集合
        first_at: 首次出现时间
    """

    __slots__ = ("first_at", "participants")

    def __init__(self, user_id: str) -> None:
        """初始化复读条目

        参数:
            user_id: 首个发送者ID
        """
        self.participants: set[str] = {user_id}
        self.first_at: datetime = datetime.now()


class RepeatFollow:
    """复读跟随

    基于TTL缓存统计相同消息出现次数。
    同一消息达到阈值人数时触发跟随决策。
    """

    def __init__(self) -> None:
        """初始化复读跟随"""
        self._cache: dict[
            str, dict[str, _RepeatEntry]
        ] = defaultdict(dict)
        """群ID -> (归一化消息 -> 复读条目)"""

    def _prune_expired(
        self, group_id: str
    ) -> dict[str, _RepeatEntry]:
        """清理过期条目

        参数:
            group_id: 群组ID

        返回:
            dict[str, _RepeatEntry]: 有效条目
        """
        entries = self._cache[group_id]
        if not entries:
            return entries
        cutoff = datetime.now() - timedelta(
            seconds=self._get_ttl_seconds()
        )
        expired_keys = [
            key
            for key, entry in entries.items()
            if entry.first_at < cutoff
        ]
        for key in expired_keys:
            entries.pop(key, None)
        return entries

    def _get_threshold(self) -> int:
        """获取跟随阈值

        返回:
            int: 触发跟随的人数阈值
        """
        threshold = get_config(
            "REPEAT_FOLLOW_THRESHOLD", _FOLLOW_THRESHOLD
        )
        try:
            value = int(threshold)
            return max(2, value)
        except (TypeError, ValueError):
            return _FOLLOW_THRESHOLD

    def _get_ttl_seconds(self) -> int:
        """获取TTL秒数

        返回:
            int: TTL秒数
        """
        ttl = get_config(
            "REPEAT_FOLLOW_TTL_SECONDS", _TTL_SECONDS
        )
        try:
            value = int(ttl)
            return max(10, value)
        except (TypeError, ValueError):
            return _TTL_SECONDS

    def check_and_follow(
        self,
        group_id: str,
        message: str,
        user_id: str,
    ) -> bool:
        """检测并决策是否跟随复读

        参数:
            group_id: 群组ID
            message: 当前消息文本
            user_id: 发送者ID

        返回:
            bool: 是否应跟随复读
        """
        if not group_id or not message or not user_id:
            return False
        if len(message) > _MAX_MESSAGE_LEN:
            return False

        key = normalize_message(message)
        if not key:
            return False

        entries = self._prune_expired(group_id)
        entry = entries.get(key)

        if entry is None:
            entries[key] = _RepeatEntry(user_id)
            return False

        if user_id in entry.participants:
            return False

        entry.participants.add(user_id)
        count = len(entry.participants)
        threshold = self._get_threshold()

        if count >= threshold:
            logger.debug(
                f"群 {group_id} 复读触发: "
                f"{count}人发送相同消息",
                command="AI",
            )
            return True
        return False


repeat_follow = RepeatFollow()
"""复读跟随单例"""


# ===== RepeatTracker：滑动窗口相似度模式 =====

_REPEAT_DETECT_THRESHOLD = 3
"""复读检测阈值（相似消息条数）"""

_REPEAT_SIMILARITY = 0.7
"""复读相似度阈值"""

_REPEAT_MAX_MESSAGE_LEN = 50
"""复读检测最大消息长度（超过此长度的消息不参与复读检测）"""

_REPEAT_BUFFER_SIZE = 20
"""复读缓冲区大小（单群最大保留的复读上下文数）"""

_REPEAT_WINDOW_SECONDS = 300
"""复读时间窗口（秒），超过此时间的复读不再跟随"""

_REPEAT_MAX_FOLLOW_OFFSET = 2
"""复读最大跟随偏移量（超过阈值+偏移量后不再跟随）"""

_SIMILARITY_NORMALIZE_LEN = 100
"""相似度计算时的归一化文本截断长度"""


@dataclass(slots=True)
class RepeatContext:
    """复读上下文

    Attributes:
        text: 被复读的文本
        count: 已复读次数
        participants: 参与者列表
        first_time: 首次出现时间
        last_time: 最后出现时间
    """

    text: str = ""
    count: int = 0
    participants: list[str] = field(default_factory=list)
    first_time: datetime | None = None
    last_time: datetime | None = None


def _text_similarity(a: str, b: str) -> float:
    """计算两段文本的相似度（基于字符集合）

    参数:
        a: 文本a
        b: 文本b

    返回:
        float: 相似度（0-1）
    """
    na = normalize_message(a, max_len=_SIMILARITY_NORMALIZE_LEN)
    nb = normalize_message(b, max_len=_SIMILARITY_NORMALIZE_LEN)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    set_a = set(na)
    set_b = set(nb)
    intersection = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.0
    return len(intersection) / len(union)


class RepeatTracker:
    """复读追踪器

    基于滑动窗口与字符集相似度，跟踪群内复读上下文，
    决策是否跟随复读。由 GroupSocialService 持有。
    """

    def __init__(self) -> None:
        """初始化复读追踪器"""
        self._buffer: dict[str, deque[RepeatContext]] = {}
        """群ID -> 最近复读上下文队列"""

    def record(
        self,
        group_id: str,
        user_id: str,
        text: str,
    ) -> None:
        """记录一条消息用于复读检测

        参数:
            group_id: 群组ID
            user_id: 用户ID
            text: 消息文本
        """
        if not text or len(text) > _REPEAT_MAX_MESSAGE_LEN:
            return
        buffer = self._buffer.setdefault(
            group_id, deque(maxlen=_REPEAT_BUFFER_SIZE)
        )
        now = datetime.now()

        for ctx in buffer:
            if (
                _text_similarity(ctx.text, text)
                >= _REPEAT_SIMILARITY
            ):
                if user_id not in ctx.participants:
                    ctx.participants.append(user_id)
                    ctx.count += 1
                ctx.last_time = now
                return

        buffer.append(
            RepeatContext(
                text=text,
                count=1,
                participants=[user_id],
                first_time=now,
                last_time=now,
            )
        )

    def should_follow(
        self,
        group_id: str,
        text: str,
        *,
        bot_user_id: str = "",
    ) -> tuple[bool, str]:
        """决策是否跟随复读

        参数:
            group_id: 群组ID
            text: 当前消息文本
            bot_user_id: 机器人用户ID

        返回:
            tuple[bool, str]: (是否跟随, 复读文本)
        """
        buffer = self._buffer.get(group_id)
        if not buffer:
            return False, ""

        for ctx in buffer:
            if (
                _text_similarity(ctx.text, text)
                >= _REPEAT_SIMILARITY
            ):
                if ctx.count < _REPEAT_DETECT_THRESHOLD:
                    return False, ""
                if (
                    bot_user_id
                    and bot_user_id in ctx.participants
                ):
                    return False, ""
                if (
                    ctx.first_time
                    and (
                        datetime.now() - ctx.first_time
                    ).total_seconds()
                    > _REPEAT_WINDOW_SECONDS
                ):
                    return False, ""
                if (
                    ctx.count
                    >= _REPEAT_DETECT_THRESHOLD
                    + _REPEAT_MAX_FOLLOW_OFFSET
                ):
                    return False, ""
                return True, ctx.text
        return False, ""

    def prune_group(self, group_id: str) -> None:
        """清理指定群的复读上下文

        参数:
            group_id: 群组ID
        """
        self._buffer.pop(group_id, None)
