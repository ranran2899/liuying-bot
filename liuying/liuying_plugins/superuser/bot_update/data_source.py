"""
机器人本体更新管理模块

提供机器人本体版本检查、文件更新与依赖同步功能
"""

import asyncio
from dataclasses import dataclass
import re

from liuying.utils.bot.version import get_bot_version
from liuying.utils.log import logger
from liuying.utils.repo_utils import repo_file_manager
from liuying.utils.repo_utils.models import RepoType

from .config import (
    BASE_PATH,
    EXCLUDE_FILES,
    LOG_COMMAND,
    REPO_URL,
    REQUIRED_FILES,
    VERSION_FILE,
)


@dataclass
class VersionInfo:
    """机器人版本信息"""

    local_version: str
    """本地版本号"""

    remote_version: str
    """仓库最新版本号"""

    @property
    def has_update(self) -> bool:
        """是否有新版本"""
        return _parse_version(self.local_version) < _parse_version(
            self.remote_version
        )


def _parse_version(version: str) -> tuple[int, ...]:
    """解析版本号为可比较的数字元组

    参数:
        version: 版本字符串，如 v0.1.6

    返回:
        tuple[int, ...]: 数字元组，如 (0, 1, 6)
    """
    return tuple(int(n) for n in re.findall(r"\d+", version))


def _parse_version_file(content: str) -> str:
    """从版本文件内容解析版本号

    参数:
        content: 版本文件内容，格式为 __version__: v0.1.6

    返回:
        str: 版本号，如 v0.1.6
    """
    for line in content.splitlines():
        if line.startswith("__version__:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("版本文件格式错误")


class UpdateManager:
    """机器人本体更新管理器"""

    @classmethod
    async def check_update(cls) -> VersionInfo:
        """检查机器人本体版本更新

        返回:
            VersionInfo: 本地与仓库版本信息
        """
        local_version = await get_bot_version()
        content = await repo_file_manager.get_file_content(REPO_URL, VERSION_FILE)
        remote_version = _parse_version_file(content)
        return VersionInfo(local_version, remote_version)

    @classmethod
    async def update_bot(cls) -> int:
        """更新机器人本体文件到仓库最新版本

        返回:
            int: 更新的文件数量

        异常:
            ValueError: 未获取到可更新文件
            RuntimeError: 文件列表不完整或下载失败
        """
        files = await repo_file_manager.list_directory_files(REPO_URL, recursive=True)
        repo_paths = [f.path for f in files if not f.is_dir]
        missing = [f for f in REQUIRED_FILES if f not in repo_paths]
        if missing:
            raise RuntimeError(f"仓库文件列表不完整，缺少关键文件: {missing}")
        download_files = [
            (f.path, BASE_PATH / f.path)
            for f in files
            if not f.is_dir and f.path not in EXCLUDE_FILES
        ]
        if not download_files:
            raise ValueError("未获取到可更新文件")
        logger.info(f"开始更新机器人本体，共 {len(download_files)} 个文件", LOG_COMMAND)
        result = await repo_file_manager.download_files(
            REPO_URL,
            download_files,
            repo_type=RepoType.GITEE,
        )
        if not result.success:
            raise RuntimeError(f"更新文件下载失败: {result.error_message}")
        logger.info(
            f"机器人本体文件更新完成，共 {len(download_files)} 个文件", LOG_COMMAND
        )
        return len(download_files)

    @classmethod
    async def update_dependencies(cls, timeout: int = 600) -> bool:
        """同步项目依赖(uv sync)

        参数:
            timeout: 超时时间(秒)

        返回:
            bool: 是否同步成功
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "sync",
                cwd=BASE_PATH,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except OSError as e:
            logger.error(f"依赖同步命令执行失败: {e}", LOG_COMMAND)
            return False
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except TimeoutError:
            proc.kill()
            logger.error(f"依赖同步超时(>{timeout}秒)，已终止", LOG_COMMAND)
            return False
        if proc.returncode == 0:
            logger.info("依赖同步完成", LOG_COMMAND)
            return True
        logger.error(
            f"依赖同步失败: {stdout.decode(errors='ignore') if stdout else ''}",
            LOG_COMMAND,
        )
        return False
