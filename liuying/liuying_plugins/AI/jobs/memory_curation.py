"""记忆策展定时任务

定期执行记忆质量评估、去重合并、主题聚合、主动学习。
基于 task_manager 注册定时任务。
"""

from liuying.services.apscheduler import task_manager
from liuying.utils.log import logger

from ..config import get_config
from ..core.memory import memory_curator

_CURATION_TASK_ID = "ai_memory_curation"
"""记忆策展任务ID"""

_CURATION_INTERVAL_HOURS = 12
"""策展间隔（小时）"""


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
    if not get_config("MEMORY_ENABLED", True):
        logger.info(
            "记忆功能已禁用，跳过策展任务注册",
            command="AI",
        )
        return

    await task_manager.add_interval(
        task_id=_CURATION_TASK_ID,
        func=_memory_curation_task,
        hours=_CURATION_INTERVAL_HOURS,
        name="AI记忆策展",
        group="ai_plugin",
        description="定期对记忆进行质量评估/去重/主题聚合/主动学习",
        replace_existing=True,
    )
    logger.debug("记忆策展定时任务已注册", command="AI")
