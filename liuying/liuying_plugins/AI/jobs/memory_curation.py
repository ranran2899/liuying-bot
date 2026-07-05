"""记忆策展定时任务

定期执行记忆质量评估、去重合并、主题聚合、主动学习。
基于 task_manager 注册定时任务。
"""

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from ..core.memory import memory_curator

_CURATION_TASK_ID = "ai_memory_curation"
"""记忆策展任务ID"""

_CURATION_INTERVAL_HOURS = 12
"""策展间隔（小时）"""


class MemoryCurationHelper:
    """记忆策展辅助工具类

    封装记忆质量评估、去重合并、主题聚合、主动学习任务逻辑。
    """

    @staticmethod
    async def _memory_curation_task() -> None:
        """记忆策展任务

        每12小时执行，对记忆进行质量评估、去重、主题聚合、主动学习。
        """
        try:
            report = await memory_curator.curate_all()
            if report.evaluated > 0:
                logger.info(
                    f"记忆策展完成: {report.to_dict()}",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"记忆策展任务失败: {e}", command="AI", e=e
            )


async def setup_memory_curation_job() -> None:
    """注册记忆策展定时任务

    每12小时执行一次。
    """
    try:
        await task_manager.add_interval_task(
            task_id=_CURATION_TASK_ID,
            func=MemoryCurationHelper._memory_curation_task,
            hours=_CURATION_INTERVAL_HOURS,
            name="AI记忆策展",
            group="ai_plugin",
            description="定期对记忆进行质量评估/去重/主题聚合/主动学习",
            replace_existing=True,
        )
        logger.debug(
            "记忆策展定时任务已注册", command="AI"
        )
    except Exception as e:
        logger.warning(
            f"记忆策展任务注册失败: {e}",
            command="AI",
            e=e,
        )
