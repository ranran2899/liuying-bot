"""
仓库管理工具包
    提供仓库文件管理、仓库提交管理等功能。
    - BaseRepoManager: 仓库管理器基类
    - RepoFileManager: 仓库文件管理器
    - GiteeManager: Gitee仓库管理器
    - FileDownloadResult: 文件下载结果
    - RepoCommitInfo: 仓库提交信息
    - RepoFileInfo: 仓库文件信息
    - RepoType: 仓库类型
    - RepoUpdateResult: 仓库更新结果
"""

from .base_manager import BaseRepoManager
from .file_manager import RepoFileManager, repo_file_manager
from .gitee_manager import GiteeManager
from .models import (
    FileDownloadResult,
    RepoCommitInfo,
    RepoFileInfo,
    RepoType,
    RepoUpdateResult,
)

__all__ = [
    "BaseRepoManager",
    "FileDownloadResult",
    "GiteeManager",
    "RepoCommitInfo",
    "RepoFileInfo",
    "RepoFileManager",
    "RepoType",
    "RepoUpdateResult",
    "repo_file_manager",
]
