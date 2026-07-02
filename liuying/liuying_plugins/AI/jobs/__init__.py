"""定时任务

包含主动行为任务、记忆衰减与巩固任务、记忆策展、社交智能、
日记系统、知识库刷新与清理。
"""

from liuying.utils.log import logger

from ..config import get_config
from .diary import setup_diary_job
from .knowledge_refresh import setup_knowledge_jobs
from .memory_curation import setup_memory_curation_job
from .memory_decay import setup_memory_jobs
from .proactive import setup_proactive_jobs
from .social_intelligence import setup_social_intelligence_jobs

__all__ = [
    "setup_diary_job",
    "setup_jobs",
    "setup_knowledge_jobs",
    "setup_memory_curation_job",
    "setup_memory_jobs",
    "setup_proactive_jobs",
    "setup_social_intelligence_jobs",
]


async def setup_jobs() -> None:
    """注册所有AI定时任务

    在插件启动时调用，注册主动行为、记忆衰减、记忆巩固、
    记忆策展、社交智能、日记、知识库刷新等任务。
    """
    await setup_proactive_jobs()
    await setup_memory_jobs()

    if get_config("MEMORY_ENABLED", True):
        try:
            await setup_memory_curation_job()
        except Exception as e:
            logger.warning(
                f"记忆策展任务注册失败: {e}", command="AI", e=e
            )

    if get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
        try:
            await setup_social_intelligence_jobs()
        except Exception as e:
            logger.warning(
                f"社交智能任务注册失败: {e}", command="AI", e=e
            )

    if get_config("DIARY_ENABLED", True):
        try:
            await setup_diary_job()
        except Exception as e:
            logger.warning(
                f"日记任务注册失败: {e}", command="AI", e=e
            )

    try:
        await setup_knowledge_jobs()
    except Exception as e:
        logger.warning(
            f"知识库任务注册失败: {e}", command="AI", e=e
        )
