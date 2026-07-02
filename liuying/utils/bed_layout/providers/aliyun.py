"""
阿里云OSS存储提供者
"""
from typing import ClassVar

from ..config import get_provider_config
from .base import CloudStorageProvider

_CONFIG_KEY = "ALIYUN_OSS_CONFIG"


class AliyunOssProvider(CloudStorageProvider):
    """阿里云OSS存储提供者"""

    _client: ClassVar[object | None] = None

    @property
    def provider_name(self) -> str:
        return "阿里云OSS"

    @classmethod
    def _get_client(cls):
        """获取OSS Bucket实例

        返回:
            oss2.Bucket: OSS Bucket实例
        """
        if cls._client is None:
            import oss2

            config = get_provider_config(_CONFIG_KEY)
            auth = oss2.Auth(
                config.get("access_key_id", ""),
                config.get("access_key_secret", ""),
            )
            cls._client = oss2.Bucket(
                auth,
                config.get("endpoint", ""),
                config.get("bucket_name", ""),
            )
        return cls._client

    def is_configured(self) -> bool:
        config = get_provider_config(_CONFIG_KEY)
        return all(
            (
                config.get("endpoint"),
                config.get("bucket_name"),
                config.get("access_key_id"),
                config.get("access_key_secret"),
            )
        )

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs,
    ) -> str:
        """上传文件到阿里云OSS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储当前不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        bucket = self._get_client()

        bucket.put_object(
            filename,
            file_data,
            headers={"Content-Type": content_type} if content_type else None,
        )

        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除阿里云OSS中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """
        bucket = self._get_client()
        bucket.delete_object(filename)
        return True

    async def get_url(self, filename: str) -> str:
        """获取阿里云OSS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        config = get_provider_config(_CONFIG_KEY)
        endpoint = config.get("endpoint", "").replace(
            "https://", ""
        ).replace("http://", "")
        return (
            f"https://{config.get('bucket_name', '')}.{endpoint}/{filename}"
        )
