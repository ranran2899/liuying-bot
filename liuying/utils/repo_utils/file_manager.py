"""
仓库文件管理器，用于从Gitee获取指定文件内容
"""

from pathlib import Path
from typing import cast, overload

import aiofiles

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger
from liuying.utils.utils import is_binary_file

from .config import LOG_COMMAND, RepoConfig
from .exceptions import (
    FileNotFoundError,
    GitUnavailableError,
    NetworkError,
    RepoManagerError,
)
from .gitee_manager import GiteeManager
from .models import FileDownloadResult, RepoFileInfo, RepoType
from .utils import sparse_checkout_clone


class RepoFileManager:
    """仓库文件管理器，用于获取Gitee仓库中的文件内容"""

    def __init__(self, config: RepoConfig | None = None):
        """
        初始化仓库文件管理器

        参数:
            config: 配置，如果为None则使用默认配置
        """
        self.config = config or RepoConfig.get_instance()
        self.config.ensure_dirs()
        self.gitee_manager = GiteeManager(config)

    def _parse_repo_name(self, repo_url: str) -> str:
        """
        从仓库URL中解析仓库名称
        
        参数:
            repo_url: 仓库URL
            
        返回:
            str: 仓库名称
        """
        return (
            repo_url.split("/tree/")[0].split("/")[-1].replace(".git", "").strip()
        )

    def _process_file_content(self, content: bytes, file_path: str) -> bytes | str:
        """
        处理文件内容，如果是文本文件则解码为字符串
        
        参数:
            content: 文件内容（字节）
            file_path: 文件路径
            
        返回:
            bytes | str: 处理后的文件内容
        """
        if not is_binary_file(file_path):
            try:
                return content.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning(
                    f"解码文件内容时出现错误，使用忽略错误模式:{file_path}",
                    LOG_COMMAND,
                )
                return content.decode("utf-8", errors="ignore")
        return content

    @overload
    async def get_gitee_file_content(
        self,
        url: str,
        file_path: str,
        ignore_error: bool = False
    ) -> str: ...

    @overload
    async def get_gitee_file_content(
        self,
        url: str,
        file_path: list[str],
        ignore_error: bool = False
    ) -> list[tuple[str, str]]: ...

    async def get_gitee_file_content(
        self, url: str, file_path: str | list[str], ignore_error: bool = False
    ) -> str | list[tuple[str, str]]:
        """
        获取Gitee仓库文件内容

        参数:
            url: 仓库URL
            file_path: 文件路径或文件路径列表
            ignore_error: 是否忽略错误

        返回:
            list[tuple[str, str]]: 文件路径，文件内容
        """
        results = []
        is_str_input = isinstance(file_path, str)

        if is_str_input:
            file_path = [file_path]

        # 解析仓库URL
        repo_info = GiteeManager.parse_gitee_url(url)

        for f in file_path:
            try:
                # 获取文件的原始下载URL
                file_url = await repo_info.get_raw_download_url(f)

                # 发送HTTP请求获取文件内容
                content = await AsyncHttpx.get_content(file_url)

                # 处理文件内容
                processed_content = self._process_file_content(content, f)

                results.append((f, processed_content))
                logger.info(f"获取Gitee文件内容成功: {f}", LOG_COMMAND)

            except Exception as e:
                logger.warning(f"获取Gitee文件内容失败: {f}", LOG_COMMAND, e=e)
                if not ignore_error:
                    raise

        logger.debug(f"获取Gitee文件内容: {[r[0] for r in results]}", LOG_COMMAND)
        return results[0][1] if is_str_input and results else results

    @overload
    async def get_file_content(
        self,
        repo_url: str,
        file_path: str,
        branch: str = "main",
        repo_type: RepoType | None = None,
        ignore_error: bool = False,
    ) -> str: ...

    @overload
    async def get_file_content(
        self,
        repo_url: str,
        file_path: list[str],
        branch: str = "main",
        repo_type: RepoType | None = None,
        ignore_error: bool = False,
    ) -> list[tuple[str, str]]: ...

    async def get_file_content(
        self,
        repo_url: str,
        file_path: str | list[str],
        branch: str = "main",
        repo_type: RepoType | None = None,
        ignore_error: bool = False,
    ) -> str | list[tuple[str, str]]:
        """
        获取仓库文件内容

        参数:
            repo_url: 仓库URL
            file_path: 文件路径
            branch: 分支名称
            repo_type: 仓库类型，如果为None则自动判断
            ignore_error: 是否忽略错误

        返回:
            str: 文件内容
        """
        try:
            # 目前只支持Gitee，直接调用get_gitee_file_content
            return await self.get_gitee_file_content(
                repo_url, file_path, ignore_error
            )
        except Exception as e:
            if isinstance(e, FileNotFoundError | NetworkError | RepoManagerError):
                raise
            raise RepoManagerError(f"获取文件内容失败: {e}")

    async def list_directory_files(
        self,
        repo_url: str,
        directory_path: str = "",
        branch: str = "main",
        repo_type: RepoType | None = None,
        recursive: bool = True,
    ) -> list[RepoFileInfo]:
        """
        获取仓库目录下的所有文件路径

        参数:
            repo_url: 仓库URL
            directory_path: 目录路径，默认为仓库根目录
            branch: 分支名称
            repo_type: 仓库类型，如果为None则自动判断
            recursive: 是否递归获取子目录文件

        返回:
            list[RepoFileInfo]: 文件信息列表
        """
        try:
            # 使用gitee_manager获取文件列表
            return await self.gitee_manager.get_file_list(
                repo_url, directory_path, branch, recursive
            )
        except Exception as e:
            logger.error(f"获取目录文件列表失败: {directory_path}", LOG_COMMAND, e=e)
            if isinstance(e, FileNotFoundError | NetworkError | RepoManagerError):
                raise
            raise RepoManagerError(f"获取目录文件列表失败: {e}")

    async def download_files(
        self,
        repo_url: str,
        file_path: tuple[str, Path] | list[tuple[str, Path]],
        branch: str = "main",
        repo_type: RepoType | None = None,
        ignore_error: bool = False,
        sparse_path: str | None = None,
        target_dir: Path | None = None,
    ) -> FileDownloadResult:
        """
        下载多个文件

        参数:
            repo_url: 仓库URL
            file_path: 文件在仓库中的路径，本地存储路径
            branch: 分支名称
            repo_type: 仓库类型，如果为None则自动判断
            ignore_error: 是否忽略错误
            sparse_path: 稀疏检出路径
            target_dir: 稀疏目标目录

        返回:
            FileDownloadResult: 下载结果
        """

        # 参数一致性校验：sparse_path 与 target_dir 必须同时有值或同时为 None
        if (sparse_path is None) ^ (target_dir is None):
            raise RepoManagerError(
                "参数错误: sparse_path 与 target_dir 必须同时提供或同时为 None"
            )

        # 确定仓库名称
        repo_name = self._parse_repo_name(repo_url)

        if isinstance(file_path, tuple):
            file_path = [file_path]

        file_path_mapping = {f[0]: f[1] for f in file_path}

        # 创建结果对象
        result = FileDownloadResult(
            repo_type=repo_type,
            repo_name=repo_name,
            file_path=file_path,
            version=branch,
        )

        # 检查是否包含二进制文件
        has_binary = any(is_binary_file(file_name) for file_name in file_path_mapping)

        # 按照真寻的实现，只有当不是Gitee仓库且包含二进制文件时才使用稀疏检出
        if has_binary and repo_type != RepoType.GITEE and sparse_path and target_dir:
            # 二进制文件使用稀疏检出
            return await self._handle_binary_with_sparse_checkout(
                repo_url=repo_url,
                branch=branch,
                sparse_path=sparse_path,
                target_dir=target_dir,
                result=result,
            )
        else:
            # 非二进制文件直接下载
            return await self._download_and_write_files(
                repo_url=repo_url,
                file_paths=[f[0] for f in file_path],
                file_path_mapping=file_path_mapping,
                branch=branch,
                repo_type=repo_type,
                ignore_error=ignore_error,
                result=result,
            )

    async def _download_and_write_files(
        self,
        repo_url: str,
        file_paths: list[str],
        file_path_mapping: dict[str, Path],
        branch: str,
        repo_type: RepoType | None,
        ignore_error: bool,
        result: FileDownloadResult,
    ) -> FileDownloadResult:
        """
        下载文件并写入本地
        """
        try:
            # 获取文件内容
            if len(file_paths) == 1:
                file_contents_result = await self.get_file_content(
                    repo_url, file_paths[0], branch, repo_type, ignore_error
                )
                if isinstance(file_contents_result, tuple):
                    file_contents = [file_contents_result]
                elif isinstance(file_contents_result, str):
                    file_contents = [(file_paths[0], file_contents_result)]
                else:
                    file_contents = cast(list[tuple[str, str]], file_contents_result)
            else:
                file_contents = cast(
                    list[tuple[str, str]],
                    await self.get_file_content(
                        repo_url, file_paths, branch, repo_type, ignore_error
                    ),
                )

            # 写入文件
            total_size = 0
            for repo_file_path, content in file_contents:
                local_path = file_path_mapping[repo_file_path]
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # 统一处理内容为字节
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                else:
                    content_bytes = content

                # 写入文件
                async with aiofiles.open(local_path, "wb") as f:
                    await f.write(content_bytes)

                total_size += len(content_bytes)
                logger.debug(f"写入文件: {local_path}", LOG_COMMAND)

            # 检查是否成功下载了文件
            if not file_contents:
                result.success = False
                result.error_message = "下载文件失败: 未能获取到任何文件内容"
                logger.error("下载文件失败: 未能获取到任何文件内容", LOG_COMMAND)
                return result

            result.success = True
            result.file_size = total_size
            logger.info(f"下载文件成功: {[f[0] for f in file_contents]}", LOG_COMMAND)
            return result

        except Exception as e:
            logger.error(f"下载文件失败: {e}", LOG_COMMAND, e=e)
            result.success = False
            result.error_message = str(e)
            return result

    async def _handle_binary_with_sparse_checkout(
        self,
        repo_url: str,
        branch: str,
        sparse_path: str,
        target_dir: Path,
        result: FileDownloadResult,
    ) -> FileDownloadResult:
        """
        使用稀疏检出处理二进制文件
        """
        try:
            # 使用稀疏检出克隆指定路径
            await sparse_checkout_clone(
                repo_url=repo_url,
                branch=branch,
                sparse_path=sparse_path,
                target_dir=target_dir,
            )

            # 计算下载的文件大小
            total_size = 0
            if target_dir.exists():
                for f in target_dir.rglob("*"):
                    if f.is_file():
                        total_size += f.stat().st_size

            result.success = True
            result.file_size = total_size
            logger.info(f"sparse-checkout 克隆成功: {target_dir}", LOG_COMMAND)
            return result

        except GitUnavailableError as e:
            logger.error(f"Git不可用: {e}", LOG_COMMAND)
            result.success = False
            result.error_message = (
                "当前插件包含二进制文件，需要使用git，当前Git不可用，"
                "请安装git"
            )
            return result
        except Exception as e:
            logger.error(f"sparse-checkout 克隆失败: {e}", LOG_COMMAND, e=e)
            result.success = False
            result.error_message = str(e)
            return result


# 创建全局实例供直接使用
repo_file_manager = RepoFileManager()
