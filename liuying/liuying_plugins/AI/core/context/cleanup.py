"""上下文清理

清理过期的对话记录与轮次统计，支持按时间窗口和数量限制清理。
"""

from datetime import datetime, timedelta

from liuying.utils.log import logger

from ...models.conversation_record import ConversationRecord
from ...models.conversation_turn import ConversationTurn

__all__ = ["ContextCleaner", "context_cleaner"]


class ContextCleaner:
    """上下文清理器

    清理过期上下文数据，按时间窗口和数量限制清理对话记录与轮次统计。
    """

    _DEFAULT_MAX_AGE_DAYS: int = 30
    """默认最大保留天数"""

    _DEFAULT_MAX_COUNT: int = 200
    """默认最大保留条数"""

    _TURN_EXPIRE_DAYS: int = 60
    """轮次统计过期天数"""

    async def cleanup_expired(
        self,
        user_id: str,
        group_id: str | None = None,
        max_age_days: int | None = None,
        max_count: int | None = None,
    ) -> int:
        """清理过期上下文数据

        按时间窗口和数量限制清理对话记录，并清理长期未活跃的轮次统计。

        参数:
            user_id: 用户ID
            group_id: 群组ID，None为私聊
            max_age_days: 最大保留天数，None用默认值
            max_count: 最大保留条数，None用默认值

        返回:
            int: 清理的记录总数
        """
        max_age = (
            int(max_age_days)
            if max_age_days is not None
            else self._DEFAULT_MAX_AGE_DAYS
        )
        max_keep = (
            int(max_count)
            if max_count is not None
            else self._DEFAULT_MAX_COUNT
        )

        total = 0
        try:
            total += await self._cleanup_by_time(
                user_id, group_id, max_age
            )
            total += await self._cleanup_by_count(
                user_id, group_id, max_keep
            )
            total += await self._cleanup_old_turns(user_id, group_id)
        except Exception as e:
            logger.warning(
                f"清理上下文失败: {e}",
                command="AI",
                e=e,
            )
            return total

        if total > 0:
            logger.info(
                f"清理上下文完成 user={user_id} "
                f"group={group_id} 删除{total}条",
                command="AI",
            )
        return total

    async def _cleanup_by_time(
        self,
        user_id: str,
        group_id: str | None,
        max_age_days: int,
    ) -> int:
        """按时间窗口清理过期对话记录

        参数:
            user_id: 用户ID
            group_id: 群组ID
            max_age_days: 最大保留天数

        返回:
            int: 删除的记录数
        """
        if max_age_days <= 0:
            return 0
        cutoff = datetime.now() - timedelta(days=max_age_days)
        query = ConversationRecord.filter(
            user_id=user_id, create_time__lt=cutoff
        )
        if group_id:
            query = query.filter(group_id=group_id)
        return await query.delete()

    async def _cleanup_by_count(
        self,
        user_id: str,
        group_id: str | None,
        max_count: int,
    ) -> int:
        """按数量限制清理超出阈值的旧对话记录

        保留最近 max_count 条，删除更早的记录。

        参数:
            user_id: 用户ID
            group_id: 群组ID
            max_count: 最大保留条数

        返回:
            int: 删除的记录数
        """
        if max_count <= 0:
            return 0
        query = ConversationRecord.filter(user_id=user_id)
        if group_id:
            query = query.filter(group_id=group_id)
        kept = await query.order_by("-create_time").limit(max_count).all()
        if len(kept) < max_count:
            return 0
        cutoff_time = kept[-1].create_time
        del_query = ConversationRecord.filter(
            user_id=user_id, create_time__lt=cutoff_time
        )
        if group_id:
            del_query = del_query.filter(group_id=group_id)
        return await del_query.delete()

    async def _cleanup_old_turns(
        self,
        user_id: str,
        group_id: str | None,
    ) -> int:
        """清理长期未活跃的轮次统计

        超过 _TURN_EXPIRE_DAYS 未更新的轮次记录视为过期。

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            int: 删除的轮次记录数
        """
        cutoff = datetime.now() - timedelta(days=self._TURN_EXPIRE_DAYS)
        query = ConversationTurn.filter(
            user_id=user_id, last_turn_time__lt=cutoff
        )
        if group_id:
            query = query.filter(group_id=group_id)
        return await query.delete()


context_cleaner = ContextCleaner()
"""上下文清理器单例"""
