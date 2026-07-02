"""会话存储

会话级状态持久化，包括当前话题、情绪状态、对话阶段等。
基于内存字典（CacheDict）+ 可选数据库持久化。
"""

from typing import Any, ClassVar

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

__all__ = ["SessionStore", "session_store"]


class SessionStore:
    """会话存储

    会话级状态持久化（当前话题、情绪状态、对话阶段），
    基于内存字典 CacheDict 实现，支持可选的数据库持久化。
    """

    _DEFAULT_EXPIRE: int = 3600
    """默认会话过期时间（秒）"""

    _DEFAULT_MAX_SIZE: int = 1000
    """默认最大会话数"""

    _DEFAULT_SESSION: ClassVar[dict[str, Any]] = {
        "topic": "",
        "emotion": "",
        "stage": "",
        "updated_at": "",
    }
    """默认会话结构"""

    def __init__(self) -> None:
        """初始化会话存储"""
        self._cache = CacheDict(
            "AI_SESSION_STORE",
            expire=self._DEFAULT_EXPIRE,
            max_size=self._DEFAULT_MAX_SIZE,
        )

    def get_session(self, session_id: str) -> dict[str, Any]:
        """获取会话状态

        不存在时返回默认会话结构。

        参数:
            session_id: 会话ID

        返回:
            dict: 会话状态数据
        """
        data = self._cache.get(session_id)
        if data is None:
            return dict(self._DEFAULT_SESSION)
        if not isinstance(data, dict):
            return dict(self._DEFAULT_SESSION)
        merged = dict(self._DEFAULT_SESSION)
        merged.update(data)
        return merged

    def set_session(
        self, session_id: str, data: dict[str, Any]
    ) -> None:
        """设置会话状态

        参数:
            session_id: 会话ID
            data: 会话状态数据
        """
        if not isinstance(data, dict):
            logger.warning(
                f"会话数据类型错误: {type(data).__name__}",
                command="AI",
            )
            return
        merged = dict(self._DEFAULT_SESSION)
        merged.update(data)
        self._cache[session_id] = merged

    def clear_session(self, session_id: str) -> None:
        """清除会话状态

        参数:
            session_id: 会话ID
        """
        self._cache.pop(session_id, None)

    def update_session(
        self,
        session_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """增量更新会话字段

        参数:
            session_id: 会话ID
            patch: 需要更新的字段字典

        返回:
            dict: 更新后的完整会话状态
        """
        current = self.get_session(session_id)
        current.update(patch)
        self.set_session(session_id, current)
        return current


session_store = SessionStore()
"""会话存储单例"""
