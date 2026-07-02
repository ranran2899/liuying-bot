"""
仓库管理工具的配置模块
"""

from dataclasses import dataclass, field
from pathlib import Path

from liuying.configs.path_config import TEMP_PATH

LOG_COMMAND = "RepoUtils"


@dataclass
class GithubConfig:
    """GitHub配置"""

    # API超时时间（秒）
    api_timeout: int = 30
    # 下载超时时间（秒）
    download_timeout: int = 60
    # 下载重试次数
    download_retry: int = 3
    # 代理配置
    proxy: str | None = None

@dataclass
class GiteeConfig:
    """Gitee配置"""

    # API超时时间（秒）
    api_timeout: int = 30
    # 下载超时时间（秒）
    download_timeout: int = 60
    # 下载重试次数
    download_retry: int = 3
    # 代理配置
    proxy: str | None = None


@dataclass
class RepoConfig:
    """仓库管理工具配置"""

    # 缓存目录
    cache_dir: Path = TEMP_PATH / "repo_cache"

    # GitHub配置
    github: GithubConfig = field(default_factory=GithubConfig)

    # 单例实例
    _instance = None

    @classmethod
    def get_instance(cls) -> "RepoConfig":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_dirs(self):
        """确保目录存在"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
