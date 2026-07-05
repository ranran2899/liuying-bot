"""知识库定时清理任务

定期清理过期查询日志，避免日志表无限增长。
知识库本身现基于流萤本体 PluginInfo + 实时元信息，
无需扫描入库，故不再需要刷新任务。
"""

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from ..core.knowledge import knowledge_store

_CLEANUP_TASK_ID = "ai_knowledge_cleanup"
"""知识库清理任务ID"""


class KnowledgeRefreshHelper:
    """知识库清理辅助工具类

    封装知识库查询日志清理任务逻辑。
    """

    @staticmethod
    async def _knowledge_cleanup_task() -> None:
        """知识库清理任务

        每天凌晨4点执行，清理30天前的查询日志。
        """
        try:
            count = await knowledge_store.prune_stale(days=30)
            if count > 0:
                logger.info(
                    f"知识库查询日志清理: {count} 条",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"知识库清理失败: {e}", command="AI", e=e
            )


async def setup_knowledge_jobs() -> None:
    """注册知识库定时任务

    仅包含查询日志清理任务（每天凌晨4点）。
    """
    try:
        await task_manager.add_cron_task(
            task_id=_CLEANUP_TASK_ID,
            func=KnowledgeRefreshHelper._knowledge_cleanup_task,
            hour=4,
            minute=0,
            name="AI知识库清理",
            group="ai_plugin",
            description="每天凌晨4点清理过期查询日志",
            replace_existing=True,
        )
        logger.debug(
            "知识库定时任务已注册", command="AI"
        )
    except Exception as e:
        logger.warning(
            f"知识库定时任务注册失败: {e}",
            command="AI",
            e=e,
        )
