"""
缓存核心管理模块

提供缓存管理器、后端管理、批量操作、降级管理、分布式锁、类型注册和后台任务。
"""

from .backend import BackendManager
from .batch import BatchExecutor, BatchResult
from .degrade import DegradeManager
from .lock import LockManager
from .manager import CacheManager, CacheRoot
from .operations import CacheOperations
from .pipeline import PipelineExecutor
from .registry import TypeRegistry
from .tasks import BackgroundTaskManager
from .warmup import WarmupExecutor, WarmupResult

__all__ = [
    "BackendManager",
    "BackgroundTaskManager",
    "BatchExecutor",
    "BatchResult",
    "CacheManager",
    "CacheOperations",
    "CacheRoot",
    "DegradeManager",
    "LockManager",
    "PipelineExecutor",
    "TypeRegistry",
    "WarmupExecutor",
    "WarmupResult",
]
