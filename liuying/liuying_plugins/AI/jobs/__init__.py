"""定时任务

包含主动行为任务、记忆衰减与巩固任务、记忆策展、社交智能、
日记系统、知识库刷新与清理、群风格自动学习、用户定时任务恢复。
"""

from ..config import get_config
from ..core.tasks_service import task_service
from ..skills import skill_loader
from .diary import setup_diary_job
from .group_style_autobuild import setup_group_style_autobuild_job
from .knowledge_refresh import setup_knowledge_jobs
from .memory_curation import setup_memory_curation_job
from .memory_decay import setup_memory_jobs
from .proactive import setup_proactive_jobs
from .social_intelligence import setup_social_intelligence_jobs

__all__ = [
    "setup_diary_job",
    "setup_group_style_autobuild_job",
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
    记忆策展、社交智能、日记、知识库刷新、群风格自动学习等任务，
    并恢复用户自定义定时任务。
    各开关的注册期判断由各 job 文件的 setup_xxx 自行负责，
    本层仅顺序调度；用户任务恢复无独立 setup 函数，
    在此保留 USER_TASKS_ENABLED 判断。
    """
    await setup_proactive_jobs()
    await setup_memory_jobs()
    await setup_memory_curation_job()
    await setup_social_intelligence_jobs()
    await setup_diary_job()
    await setup_knowledge_jobs()
    await setup_group_style_autobuild_job()

    if get_config("USER_TASKS_ENABLED", True):
        await task_service.restore_tasks_on_startup()

    await skill_loader.register_mcp_tools()
