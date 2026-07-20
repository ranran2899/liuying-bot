"""记忆衰减与巩固任务

定期执行记忆衰减、记忆巩固、用户画像更新。
基于 task_manager 注册定时任务。
"""

from collections import defaultdict
from datetime import datetime, timedelta

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from ..config import get_config
from ..core.memory import memory_manager
from ..core.persona import persona_manager
from ..models.conversation_record import ConversationRecord

_DECAY_TASK_ID = "ai_memory_decay"
"""记忆衰减任务ID"""

_CONSOLIDATION_TASK_ID = "ai_memory_consolidation"
"""记忆巩固任务ID"""

_PERSONA_UPDATE_TASK_ID = "ai_user_persona_update"
"""用户画像更新任务ID"""

_PERSONA_UPDATE_THRESHOLD = 20
"""用户画像更新阈值（消息数）"""


class MemoryDecayHelper:
    """记忆衰减与巩固辅助工具类

    封装记忆衰减、记忆巩固、用户画像更新等任务逻辑。
    """

    @staticmethod
    async def _memory_decay_task() -> None:
        """记忆衰减任务

        每6小时执行，处理过期记忆。
        """
        if not get_config(
            "MEMORY_ENABLED", True
        ) or not get_config("MEMORY_DECAY_ENABLED", True):
            return

        try:
            count = await memory_manager.decay_expired()
            if count > 0:
                logger.info(
                    f"记忆衰减完成，处理{count}条",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"记忆衰减失败: {e}", command="AI", e=e
            )

    @staticmethod
    async def _memory_consolidation_task() -> None:
        """记忆巩固任务

        每天凌晨3点执行，巩固过去24小时内的对话记忆。
        """
        if not get_config(
            "MEMORY_ENABLED", True
        ) or not get_config(
            "MEMORY_CONSOLIDATION_ENABLED", True
        ):
            return

        try:
            users = (
                await MemoryDecayHelper._get_active_users_in_window(
                    hours=24
                )
            )
            total = 0
            for user_id, group_id, persona_name in users:
                count = await memory_manager.consolidate(
                    user_id,
                    group_id,
                    window_hours=24,
                    persona_name=persona_name,
                )
                total += count
            if total > 0:
                logger.info(
                    f"记忆巩固完成，处理{total}条",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"记忆巩固失败: {e}", command="AI", e=e
            )

    @staticmethod
    async def _get_active_users_in_window(
        hours: int = 24,
    ) -> list[tuple[str, str | None, str | None]]:
        """获取时间窗口内的活跃用户

        按用户+群组+人格三元组去重，确保不同人格的记忆独立巩固。
        保留 persona_name 原值用于后续过滤，避免 None 被
        归一化为 "default" 后 filter 无法命中真实 None 记录。

        参数:
            hours: 时间窗口（小时）

        返回:
            list[tuple[str, str | None, str | None]]:
                (user_id, group_id, persona_name) 列表
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        records = await ConversationRecord.filter(
            create_time__gt=cutoff,
            role="user",
        ).all()
        seen: set[tuple[str, str | None, str | None]] = set()
        for r in records:
            key = (r.user_id, r.group_id, r.persona_name)
            if key not in seen:
                seen.add(key)
        return list(seen)

    @staticmethod
    async def _user_persona_update_task() -> None:
        """用户画像更新任务

        每2小时执行，检查用户消息历史达阈值则更新画像。
        按 persona_name 分组统计与拉取历史，保证人设间数据隔离。
        优化：一次查询所有近期 user 消息并在 Python 内存分组计数，
        消除循环内 count 查询的 N+1 问题。
        """
        if not get_config("MEMORY_ENABLED", True):
            return

        try:
            cutoff = datetime.now() - timedelta(hours=2)
            records = await ConversationRecord.filter(
                create_time__gt=cutoff,
                role="user",
            ).all()

            # Python 内存按 (user_id, group_id, persona_name) 分组计数，
            # 避免循环内 N 次 count 查询的 N+1 问题
            counter: dict[
                tuple[str, str | None, str | None], int
            ] = defaultdict(int)
            for r in records:
                counter[
                    (r.user_id, r.group_id, r.persona_name)
                ] += 1

            updated = 0
            for (
                user_id,
                group_id,
                persona_name,
            ), count in counter.items():
                if count < _PERSONA_UPDATE_THRESHOLD:
                    continue
                history_records = (
                    await ConversationRecord.get_history(
                        user_id,
                        group_id,
                        limit=_PERSONA_UPDATE_THRESHOLD,
                        persona_name=persona_name,
                    )
                )
                history = [
                    {"role": r.role, "content": r.content}
                    for r in reversed(history_records)
                ]
                await persona_manager.update_user_persona(
                    user_id, history
                )
                updated += 1
            if updated > 0:
                logger.info(
                    f"用户画像更新完成，更新{updated}个",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"用户画像更新失败: {e}", command="AI", e=e
            )


async def setup_memory_jobs() -> None:
    """注册记忆相关定时任务"""
    if not get_config("MEMORY_ENABLED", True):
        logger.info("记忆任务已禁用", command="AI")
        return

    if get_config("MEMORY_DECAY_ENABLED", True):
        await task_manager.add_interval(
            task_id=_DECAY_TASK_ID,
            func=MemoryDecayHelper._memory_decay_task,
            hours=6,
            name="AI记忆衰减",
            group="ai_plugin",
            description="定期处理过期记忆",
            replace_existing=True,
        )
        logger.info("记忆衰减任务已注册（每6小时）", command="AI")

    if get_config("MEMORY_CONSOLIDATION_ENABLED", True):
        await task_manager.add_cron(
            task_id=_CONSOLIDATION_TASK_ID,
            func=MemoryDecayHelper._memory_consolidation_task,
            hour=3,
            minute=0,
            name="AI记忆巩固",
            group="ai_plugin",
            description="每天凌晨3点巩固记忆",
            replace_existing=True,
        )
        logger.info("记忆巩固任务已注册（每天3:00）", command="AI")

    await task_manager.add_interval(
        task_id=_PERSONA_UPDATE_TASK_ID,
        func=MemoryDecayHelper._user_persona_update_task,
        hours=2,
        name="AI用户画像更新",
        group="ai_plugin",
        description="每2小时检查并更新用户画像",
        replace_existing=True,
    )
    logger.info("用户画像更新任务已注册（每2小时）", command="AI")
