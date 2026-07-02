"""
存储提供者抽象基类

定义所有存储提供者（本地与云存储）必须遵循的统一接口契约。
"""
from abc import ABC, abstractmethod
from typing import ClassVar

from liuying.utils.log import logger


class CloudStorageProvider(ABC):
    """存储提供者抽象基类

    所有具体存储实现（本地数据库、腾讯云、百度云、阿里云、华为云）
    都必须继承本类并实现其抽象方法，确保对外接口一致。
    """

    _client: ClassVar[object | None] = None

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称，用于日志记录"""

    @classmethod
    @abstractmethod
    def _get_client(cls):
        """获取存储客户端实例（由子类实现具体初始化逻辑）"""

    @abstractmethod
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs,
    ) -> str:
        """上传文件到存储

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据（如 source/category/tags/original_url）

        返回:
            str: 文件访问URL
        """

    @abstractmethod
    async def delete(self, filename: str) -> bool:
        """删除存储中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """

    @abstractmethod
    async def get_url(self, filename: str) -> str:
        """获取文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """检查当前提供者是否已正确配置"""

    def _log_error(self, action: str, filename: str, error: Exception) -> None:
        """记录操作错误日志

        参数:
            action: 操作类型描述
            filename: 文件名
            error: 异常对象
        """
        logger.error(f"{action}图片失败: {filename}", self.provider_name, e=error)
