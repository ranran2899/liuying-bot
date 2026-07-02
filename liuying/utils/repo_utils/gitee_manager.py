"""
Gitee仓库管理工具
"""

import asyncio
from datetime import datetime
from pathlib import Path

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from .base_manager import BaseRepoManager
from .config import LOG_COMMAND, RepoConfig
from .exceptions import (
    ApiRateLimitError,
    NetworkError,
    RepoDownloadError,
    RepoNotFoundError,
    RepoUpdateError,
)
from .models import (
    FileDownloadResult,
    RepoCommitInfo,
    RepoFileInfo,
    RepoType,
    RepoUpdateResult,
)


class RepoInfo:
    """仓库信息类"""

    def __init__(self):
        self.owner: str = ""
        self.repo: str = ""
        self.branch: str = "master"
        self.url: str = ""

    @classmethod
    def parse_git_url(cls, url: str) -> "RepoInfo":
        """解析Git仓库URL"""
        repo_info = cls()

        # 处理Gitee URL格式
        if "gitee.com" in url:
            # https://gitee.com/owner/repo/tree/branch/path
            parts = url.split("/")
            if len(parts) >= 5:
                repo_info.owner = parts[3]
                repo_info.repo = parts[4].split(".git")[0]

                # 解析分支
                if "tree" in parts:
                    tree_idx = parts.index("tree")
                    if tree_idx + 1 < len(parts):
                        repo_info.branch = parts[tree_idx + 1]

            # 只保留仓库基础URL，去掉tree及后面的路径
            repo_info.url = url.split("/tree/")[0] if "/tree/" in url else url

        # 处理GitHub URL格式
        elif "github.com" in url:
            # https://github.com/owner/repo/tree/branch/path
            parts = url.split("/")
            if len(parts) >= 5:
                repo_info.owner = parts[3]
                repo_info.repo = parts[4].split(".git")[0]

                # 解析分支
                if "tree" in parts:
                    tree_idx = parts.index("tree")
                    if tree_idx + 1 < len(parts):
                        repo_info.branch = parts[tree_idx + 1]

            # 只保留仓库基础URL，去掉tree及后面的路径
            repo_info.url = url.split("/tree/")[0] if "/tree/" in url else url

        return repo_info

    async def get_raw_download_url(self, file_path: str) -> str:
        """获取文件的原始下载URL"""
        # 根据URL判断是Gitee还是GitHub
        if "gitee.com" in self.url:
            # Gitee的原始文件URL格式
            return f"https://gitee.com/{self.owner}/{self.repo}/raw/{self.branch}/{file_path}"
        else:
            # GitHub的原始文件URL格式
            return f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/{self.branch}/{file_path}"


class GiteeManager(BaseRepoManager):
    """Gitee仓库管理工具"""

    def __init__(self, config: RepoConfig | None = None):
        """
        初始化Gitee仓库管理工具

        参数:
            config: 配置，如果为None则使用默认配置
        """
        super().__init__(config)

    @classmethod
    def parse_gitee_url(cls, url: str) -> RepoInfo:
        """解析仓库URL"""
        return RepoInfo.parse_git_url(url)

    async def update_repo(
        self,
        repo_url: str,
        local_path: Path,
        branch: str = "master",
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> RepoUpdateResult:
        """
        更新Gitee仓库

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            local_path: 本地保存路径
            branch: 分支名称
            include_patterns: 包含的文件模式列表，如 ["*.py", "docs/*.md"]
            exclude_patterns: 排除的文件模式列表，如 ["__pycache__/*", "*.pyc"]

        返回:
            RepoUpdateResult: 更新结果
        """
        try:
            # 解析仓库URL
            repo_info = self.parse_gitee_url(repo_url)
            repo_info.branch = branch

            # 创建结果对象
            result = RepoUpdateResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_info.repo,
                owner=repo_info.owner,
                old_version="",  # 将在后面更新
                new_version="",  # 简化实现，不获取具体的commit ID
            )

            old_version = await self.read_version_file(local_path)
            if old_version:
                old_version = old_version.split("-")[-1]
                result.old_version = old_version

            # 确保本地目录存在
            local_path.mkdir(parents=True, exist_ok=True)

            # 获取所有文件列表
            files = await self.get_file_list(repo_url, branch=branch, recursive=True)
            file_paths = [file.path for file in files if not file.is_dir]

            # 过滤文件
            if include_patterns or exclude_patterns:
                from .utils import filter_files

                file_paths = filter_files(
                    file_paths, include_patterns, exclude_patterns
                )

            result.changed_files = file_paths

            # 下载文件
            for file_path in file_paths:
                try:
                    local_file_path = local_path / file_path
                    await self._download_file(repo_info, file_path, local_file_path)
                except Exception as e:
                    logger.error(f"下载文件 {file_path} 失败", LOG_COMMAND, e=e)

            # 更新版本文件
            await self.write_version_file(local_path, datetime.now().strftime("%Y%m%d%H%M%S"))

            result.success = True
            return result

        except RepoUpdateError as e:
            logger.error("更新仓库失败", LOG_COMMAND, e=e)
            return RepoUpdateResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_url.split("/")[-1] if "/" in repo_url else repo_url,
                owner=repo_url.split("/")[-2] if "/" in repo_url else "unknown",
                old_version="",
                new_version="",
                error_message=str(e),
            )
        except Exception as e:
            logger.error("更新仓库失败", LOG_COMMAND, e=e)
            return RepoUpdateResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_url.split("/")[-1] if "/" in repo_url else repo_url,
                owner=repo_url.split("/")[-2] if "/" in repo_url else "unknown",
                old_version="",
                new_version="",
                error_message=str(e),
            )

    async def download_file(
        self,
        repo_url: str,
        file_path: str,
        local_path: Path,
        branch: str = "master",
    ) -> FileDownloadResult:
        """
        从Gitee下载单个文件

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            file_path: 文件在仓库中的路径
            local_path: 本地保存路径
            branch: 分支名称

        返回:
            FileDownloadResult: 下载结果
        """
        repo_name = (
            repo_url.split("/tree/")[0].split("/")[-1].replace(".git", "").strip()
        )
        try:
            # 解析仓库URL
            repo_info = self.parse_gitee_url(repo_url)
            repo_info.branch = branch

            # 创建结果对象
            result = FileDownloadResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_info.repo,
                file_path=file_path,
                version=branch,
            )

            # 确保本地目录存在
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # 下载文件
            file_size = await self._download_file(repo_info, file_path, local_path)

            result.success = True
            result.file_size = file_size
            return result

        except RepoDownloadError as e:
            logger.error("下载文件失败", LOG_COMMAND, e=e)
            return FileDownloadResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_name,
                file_path=file_path,
                version=branch,
                error_message=str(e),
            )
        except Exception as e:
            logger.error("下载文件失败", LOG_COMMAND, e=e)
            return FileDownloadResult(
                repo_type=RepoType.GITEE,
                repo_name=repo_name,
                file_path=file_path,
                version=branch,
                error_message=str(e),
            )

    async def get_file_list(
        self,
        repo_url: str,
        dir_path: str = "",
        branch: str = "master",
        recursive: bool = False,
    ) -> list[RepoFileInfo]:
        """
        获取仓库文件列表

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            dir_path: 目录路径，空字符串表示仓库根目录
            branch: 分支名称
            recursive: 是否递归获取子目录

        返回:
            list[RepoFileInfo]: 文件信息列表
        """
        try:
            # 解析仓库URL
            repo_info = self.parse_gitee_url(repo_url)
            repo_info.branch = branch

            # 根据URL类型使用不同的API
            if "gitee.com" in repo_info.url:
                # 使用Gitee API获取文件列表
                api_url = f"https://gitee.com/api/v5/repos/{repo_info.owner}/{repo_info.repo}/contents/{dir_path}"
            else:
                # 使用GitHub API获取文件列表
                api_url = f"https://api.github.com/repos/{repo_info.owner}/{repo_info.repo}/contents/{dir_path}"

            params = {
                "ref": branch,
            }

            resp = await AsyncHttpx.get(api_url, params=params)
            if resp.status_code == 200:
                contents = resp.json()
                result = []

                for item in contents:
                    is_dir = item["type"] == "dir"
                    path = item["path"]
                    if is_dir and not path.endswith("/"):
                        path = path + "/"
                    file_info = RepoFileInfo(
                        path=path,
                        is_dir=is_dir
                    )
                    result.append(file_info)

                    if is_dir and recursive:
                        sub_files = await self.get_file_list(
                            repo_url,
                            item["path"],
                            branch,
                            recursive
                        )
                        result.extend(sub_files)

                return result
            else:
                logger.error(f"获取文件列表失败: HTTP {resp.status_code}", LOG_COMMAND)
                return []

        except Exception as e:
            logger.error("获取文件列表失败", LOG_COMMAND, e=e)
            return []

    async def get_commit_info(
        self, repo_url: str, commit_id: str
    ) -> RepoCommitInfo | None:
        """
        获取提交信息

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            commit_id: 提交ID

        返回:
            Optional[RepoCommitInfo]: 提交信息，如果获取失败则返回None
        """
        try:
            # 解析仓库URL
            repo_info = self.parse_gitee_url(repo_url)

            # 构建API URL
            if "gitee.com" in repo_info.url:
                api_url = f"https://gitee.com/api/v5/repos/{repo_info.owner}/{repo_info.repo}/commits/{commit_id}"
            else:
                api_url = f"https://api.github.com/repos/{repo_info.owner}/{repo_info.repo}/commits/{commit_id}"

            # 发送请求
            resp = await AsyncHttpx.get(
                api_url,
                timeout=self.config.github.api_timeout,
                proxy=self.config.github.proxy,
            )

            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                raise ApiRateLimitError("Gitee")

            if resp.status_code != 200:
                if resp.status_code == 404:
                    raise RepoNotFoundError(f"{repo_info.owner}/{repo_info.repo}")
                raise NetworkError(f"HTTP {resp.status_code}: {resp.text}")

            data = resp.json()

            return RepoCommitInfo(
                commit_id=data["sha"],
                message=data["commit"]["message"],
                author=data["commit"]["author"]["name"],
                commit_time=datetime.fromisoformat(
                    data["commit"]["author"]["date"].replace("Z", "+00:00")
                ),
                changed_files=[file["filename"] for file in data.get("files", [])],
            )
        except Exception as e:
            logger.error("获取提交信息失败", LOG_COMMAND, e=e)
            return None

    async def update_via_git(
        self,
        repo_url: str,
        local_path: Path,
        branch: str = "master",
        force: bool = False,
        *,
        repo_type: RepoType | None = None,
        owner="",
        prepare_repo_url=None,
    ) -> RepoUpdateResult:
        """
        通过Git命令直接更新仓库

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            local_path: 本地仓库路径
            branch: 分支名称
            force: 是否强制拉取
            repo_type: 仓库类型
            owner: 仓库拥有者
            prepare_repo_url: 预处理仓库URL的函数

        返回:
            RepoUpdateResult: 更新结果
        """
        # 解析仓库URL
        repo_info = self.parse_gitee_url(repo_url)

        # 调用基类的update_via_git方法
        return await super().update_via_git(
            repo_url=repo_url,
            local_path=local_path,
            branch=branch,
            force=force,
            repo_type=RepoType.GITEE,
            owner=repo_info.owner,
        )

    async def update(
        self,
        repo_url: str,
        local_path: Path,
        branch: str = "master",
        use_git: bool = True,
        force: bool = False,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> RepoUpdateResult:
        """
        更新仓库，可选择使用Git命令或API方式

        参数:
            repo_url: 仓库URL，格式为 https://gitee.com/owner/repo
            local_path: 本地保存路径
            branch: 分支名称
            use_git: 是否使用Git命令更新
            include_patterns: 包含的文件模式列表，如 ["*.py", "docs/*.md"]
            exclude_patterns: 排除的文件模式列表，如 ["__pycache__/*", "*.pyc"]

        返回:
            RepoUpdateResult: 更新结果
        """
        if use_git:
            return await self.update_via_git(repo_url, local_path, branch, force)
        else:
            return await self.update_repo(
                repo_url, local_path, branch, include_patterns, exclude_patterns
            )

    async def _download_file(
        self, repo_info: RepoInfo, file_path: str, local_path: Path
    ) -> int:
        """
        下载文件

        参数:
            repo_info: 仓库信息
            file_path: 文件在仓库中的路径
            local_path: 本地保存路径

        返回:
            int: 文件大小（字节）
        """
        # 确保目录存在
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # 获取下载URL
        download_url = await repo_info.get_raw_download_url(file_path)

        # 下载文件
        for retry in range(self.config.github.download_retry + 1):
            try:
                content = await AsyncHttpx.get_content(
                    download_url,
                    timeout=self.config.github.download_timeout,
                )

                # 保存文件
                await self.save_file_content(content, local_path)
                return len(content)

            except Exception as e:
                if retry < self.config.github.download_retry:
                    logger.warning("下载文件失败，将重试", LOG_COMMAND, e=e)
                    await asyncio.sleep(1)
                    continue
                raise RepoDownloadError(f"下载文件失败: {e}")

        raise RepoDownloadError("下载文件失败: 超过最大重试次数")
