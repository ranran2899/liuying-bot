"""话题线程追踪

将群聊消息按文本相似度聚类到话题线程，支持线程生命周期管理。
新消息通过 Jaccard 相似度匹配到最接近的活跃线程，
超时未活跃的线程自动关闭。供上下文管理器查询当前话题。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

from liuying.utils.log import logger

_THREAD_TIMEOUT_MINUTES = 30
"""线程超时关闭分钟数"""

_SIMILARITY_THRESHOLD = 0.25
"""线程匹配相似度阈值"""

_MAX_ACTIVE_THREADS = 10
"""最大活跃线程数"""

_SUMMARY_KEYWORDS = 5
"""主题关键词数量"""

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
"""CJK字符匹配模式"""

_CJK_SPLIT_RE = re.compile(r"([\u4e00-\u9fff\u3400-\u4dbf]+)")
"""CJK文本分割模式"""


def _tokenize_text(text: str) -> set[str]:
    """分词: CJK按字符bigram, 非CJK按空格分词

    解决中文文本 split() 无效的问题,使用字符级bigram
    保证 Jaccard 相似度对中文有实际区分能力。

    参数:
        text: 输入文本

    返回:
        set[str]: 词元集合
    """
    tokens: set[str] = set()
    parts = _CJK_SPLIT_RE.split(text)
    for part in parts:
        if not part:
            continue
        if _CJK_RE.match(part):
            chars = [c for c in part if c.strip()]
            for i in range(len(chars) - 1):
                tokens.add(chars[i] + chars[i + 1])
            for c in chars:
                tokens.add(c)
        else:
            for word in part.split():
                if len(word) >= 2:
                    tokens.add(word.lower())
    return tokens


@dataclass(slots=True)
class ThreadMessage:
    """线程消息

    Attributes:
        user_id: 用户ID
        text: 消息文本
        timestamp: 消息时间
    """

    user_id: str
    text: str
    timestamp: datetime


@dataclass(slots=True)
class TopicThread:
    """话题线程

    Attributes:
        thread_id: 线程ID
        group_id: 群组ID
        topic: 主题摘要
        keywords: 主题关键词列表
        messages: 线程内消息列表
        participants: 参与者ID集合
        last_active: 最后活跃时间
        is_active: 是否活跃
    """

    thread_id: int
    group_id: str
    topic: str
    keywords: list[str] = field(default_factory=list)
    messages: list[ThreadMessage] = field(default_factory=list)
    participants: set[str] = field(default_factory=set)
    last_active: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    def add_message(
        self, user_id: str, text: str
    ) -> None:
        """添加消息到线程

        参数:
            user_id: 用户ID
            text: 消息文本
        """
        self.messages.append(
            ThreadMessage(
                user_id=user_id,
                text=text,
                timestamp=datetime.now(),
            )
        )
        self.participants.add(user_id)
        self.last_active = datetime.now()
        if len(self.messages) > 50:
            self.messages = self.messages[-30:]


class ThreadTracker:
    """话题线程追踪器

    按文本相似度将群聊消息聚类到话题线程，
    管理线程生命周期与查询。
    """

    def __init__(self) -> None:
        """初始化话题线程追踪器"""
        self._threads: dict[int, dict[str, TopicThread]] = {}
        """group_id -> {thread_id -> TopicThread}"""
        self._next_id: int = 1
        """线程ID自增计数器"""

    def track_message(
        self,
        group_id: str,
        user_id: str,
        text: str,
    ) -> TopicThread:
        """追踪一条群聊消息，归入或创建话题线程

        参数:
            group_id: 群组ID
            user_id: 用户ID
            text: 消息文本

        返回:
            TopicThread: 归入的线程
        """
        self._cleanup_expired(group_id)
        thread = self._find_matching_thread(group_id, text)
        if thread is None:
            thread = self._create_thread(group_id, text)
        thread.add_message(user_id, text)
        return thread

    def get_active_threads(
        self, group_id: str
    ) -> list[TopicThread]:
        """获取群组当前活跃的话题线程

        参数:
            group_id: 群组ID

        返回:
            list[TopicThread]: 活跃线程列表（按最后活跃时间降序）
        """
        threads = self._threads.get(group_id, {})
        active = [
            t
            for t in threads.values()
            if t.is_active
        ]
        active.sort(
            key=lambda t: t.last_active, reverse=True
        )
        return active[:_MAX_ACTIVE_THREADS]

    def get_thread_context(
        self,
        group_id: str,
        max_messages: int = 10,
    ) -> str:
        """获取当前话题的上下文文本（供提示词使用）

        参数:
            group_id: 群组ID
            max_messages: 最大消息数

        返回:
            str: 上下文文本
        """
        active = self.get_active_threads(group_id)
        if not active:
            return ""
        thread = active[0]
        recent = thread.messages[-max_messages:]
        if not recent:
            return ""
        lines: list[str] = [
            f"[当前话题: {thread.topic}]"
        ]
        for msg in recent:
            lines.append(f"用户{msg.user_id}: {msg.text}")
        return "\n".join(lines)

    def _find_matching_thread(
        self, group_id: str, text: str
    ) -> TopicThread | None:
        """查找与文本最匹配的活跃线程

        参数:
            group_id: 群组ID
            text: 消息文本

        返回:
            TopicThread | None: 匹配的线程或None
        """
        threads = self._threads.get(group_id, {})
        best_thread: TopicThread | None = None
        best_score = 0.0
        for thread in threads.values():
            if not thread.is_active:
                continue
            score = self._thread_similarity(thread, text)
            if (
                score >= _SIMILARITY_THRESHOLD
                and score > best_score
            ):
                best_score = score
                best_thread = thread
        return best_thread

    def _create_thread(
        self, group_id: str, text: str
    ) -> TopicThread:
        """创建新话题线程

        参数:
            group_id: 群组ID
            text: 首条消息文本

        返回:
            TopicThread: 新线程
        """
        thread_id = self._next_id
        self._next_id += 1
        keywords = self._extract_keywords(text)
        topic = self._build_topic(text, keywords)
        thread = TopicThread(
            thread_id=thread_id,
            group_id=group_id,
            topic=topic,
            keywords=keywords,
        )
        if group_id not in self._threads:
            self._threads[group_id] = {}
        self._threads[group_id][thread_id] = thread
        logger.debug(
            f"创建话题线程: group={group_id} "
            f"thread={thread_id} topic={topic}",
            command="AI",
        )
        return thread

    def _cleanup_expired(self, group_id: str) -> int:
        """清理超时的活跃线程

        参数:
            group_id: 群组ID

        返回:
            int: 清理的线程数量
        """
        threads = self._threads.get(group_id, {})
        cutoff = datetime.now() - timedelta(
            minutes=_THREAD_TIMEOUT_MINUTES
        )
        count = 0
        for thread in threads.values():
            if thread.is_active and thread.last_active < cutoff:
                thread.is_active = False
                count += 1
        return count

    @staticmethod
    def _thread_similarity(
        thread: TopicThread, text: str
    ) -> float:
        """计算文本与线程的相似度

        基于线程关键词与文本的 Jaccard 相似度。

        参数:
            thread: 话题线程
            text: 待匹配文本

        返回:
            float: 相似度（0-1）
        """
        if not thread.keywords or not text:
            return 0.0
        text_words = _tokenize_text(text)
        keyword_set = set(thread.keywords)
        if not text_words or not keyword_set:
            return 0.0
        intersection = text_words & keyword_set
        union = text_words | keyword_set
        return len(intersection) / len(union)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """提取文本关键词

        基于词频提取前N个关键词（简化方案）。

        参数:
            text: 输入文本

        返回:
            list[str]: 关键词列表
        """
        if not text:
            return []
        words = _tokenize_text(text)
        freq: dict[str, int] = {}
        for word in words:
            if len(word) >= 2:
                freq[word] = freq.get(word, 0) + 1
        sorted_words = sorted(
            freq.items(), key=lambda x: x[1], reverse=True
        )
        return [
            w for w, _ in sorted_words[:_SUMMARY_KEYWORDS]
        ]

    @staticmethod
    def _build_topic(
        text: str, keywords: list[str]
    ) -> str:
        """构建线程主题摘要

        参数:
            text: 首条消息文本
            keywords: 关键词列表

        返回:
            str: 主题摘要
        """
        if keywords:
            return "、".join(keywords[:3])
        return text[:20] if text else "未命名话题"


thread_tracker = ThreadTracker()
"""话题线程追踪器单例"""
