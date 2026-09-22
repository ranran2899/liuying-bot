"""定时任务

包含记忆衰减与巩固任务、记忆策展、社交智能（含群空闲发话
与私聊问候等主动行为）、日记系统、知识库刷新与清理、
群风格自动学习与用户定时任务恢复。
"""

from ..config import get_config
from ..core.tasks_service import task_service
from .diary import setup_diary_job
from .group_style_autobuild import setup_group_style_autobuild_job
from .knowledge_refresh import setup_knowledge_jobs
from .memory_curation import setup_memory_curation_job
from .memory_decay import setup_memory_jobs
from .social_intelligence import setup_social_intelligence_jobs

__all__ = [
    "setup_diary_job",
    "setup_group_style_autobuild_job",
    "setup_jobs",
    "setup_knowledge_jobs",
    "setup_memory_curation_job",
    "setup_memory_jobs",
    "setup_social_intelligence_jobs",
]


async def setup_jobs() -> None:
    """注册所有AI定时任务

    在插件启动时调用，注册记忆衰减、记忆巩固、记忆策展、
    社交智能（含主动行为）、日记、知识库刷新、群风格自动学习等任务，
    并恢复用户自定义定时任务。
    各开关的注册判断由各 job 文件的 setup_xxx/注册函数自行负责，
    本层仅顺序调度；用户任务恢复无独立 setup 函数，
    在此保留 USER_TASKS_ENABLED 判断。
    """
    await setup_memory_jobs()
    await setup_memory_curation_job()
    await setup_social_intelligence_jobs()
    await setup_diary_job()
    await setup_knowledge_jobs()
    await setup_group_style_autobuild_job()

    if get_config("USER_TASKS_ENABLED", True):
        await task_service.restore_tasks_on_startup()
