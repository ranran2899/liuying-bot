"""
存储提供者模块

统一导出本地存储与云存储提供者实现。
"""
from .base import CloudStorageProvider
from .local import LocalStorageProvider

__all__ = ["CloudStorageProvider", "LocalStorageProvider"]
