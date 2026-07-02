"""图片引用追踪

追踪图片在对话中被引用与回复的上下文，
用于后续基于引用历史的图片分析、记忆构建与上下文增强。
"""

import time

from liuying.utils.log import logger

__all__ = ["ImageRefTracker", "image_ref_tracker"]


_MAX_REFS_PER_IMAGE = 20
"""单张图片最多保留的引用记录数"""


class ImageRefTracker:
    """图片引用追踪器

    基于内存字典记录每张图片被引用的消息ID、用户ID与时间戳，
    便于后续上下文分析、记忆关联与多轮图片理解。
    """

    def __init__(self) -> None:
        """初始化图片引用追踪器"""
        self._refs: dict[str, list[dict]] = {}

    def _normalize_url(self, image_url: str) -> str:
        """规范化图片URL作为键

        参数:
            image_url: 原始图片URL

        返回:
            str: 规范化后的URL（去除首尾空白）
        """
        return (image_url or "").strip()

    def track(
        self,
        image_url: str,
        message_id: int,
        user_id: str,
    ) -> None:
        """记录图片引用

        参数:
            image_url: 图片URL
            message_id: 引用该图片的消息ID
            user_id: 发起引用的用户ID
        """
        key = self._normalize_url(image_url)
        if not key:
            return

        record = {
            "message_id": message_id,
            "user_id": user_id,
            "timestamp": time.time(),
        }

        bucket = self._refs.setdefault(key, [])
        bucket.append(record)

        if len(bucket) > _MAX_REFS_PER_IMAGE:
            dropped = bucket[:-_MAX_REFS_PER_IMAGE]
            bucket[:] = bucket[len(dropped):]
            logger.debug(
                f"图片引用记录超出上限，丢弃{len(dropped)}条: {key}",
                command="AI",
            )

    def get_refs(self, image_url: str) -> list[dict]:
        """获取图片的引用记录

        参数:
            image_url: 图片URL

        返回:
            list[dict]: 引用记录列表，每项含
                message_id/user_id/timestamp 字段
        """
        key = self._normalize_url(image_url)
        if not key:
            return []
        return list(self._refs.get(key, []))

    def clear(self, image_url: str | None = None) -> None:
        """清空引用记录

        参数:
            image_url: 指定URL时仅清除该URL的记录，
                None时清空全部
        """
        if image_url is None:
            self._refs.clear()
            return
        key = self._normalize_url(image_url)
        self._refs.pop(key, None)


image_ref_tracker = ImageRefTracker()
"""图片引用追踪器单例"""
