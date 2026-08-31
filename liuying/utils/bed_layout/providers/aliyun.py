"""阿里云OSS存储提供者"""
from typing import Any

from liuying.utils.enum import StorageType

from ..base import CloudStorageProvider, ProviderRegistry


@ProviderRegistry.register(StorageType.ALIYUN)
class AliyunOssProvider(CloudStorageProvider):
    """阿里云OSS存储提供者"""

    _config_key = "ALIYUN_OSS_CONFIG"
    _required_fields = ("endpoint", "bucket_name", "access_key_id", "access_key_secret")

    @property
    def provider_name(self) -> str:
        return "阿里云OSS"

    @classmethod
    def _create_client(cls) -> object:
        """创建OSS Bucket实例"""
        import oss2

        config = cls._get_config()
        auth = oss2.Auth(
            config.get("access_key_id", ""),
            config.get("access_key_secret", ""),
        )
        return oss2.Bucket(
            auth,
            config.get("endpoint", ""),
            config.get("bucket_name", ""),
        )

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到阿里云OSS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        headers = {"Content-Type": content_type} if content_type else None
        self._get_client().put_object(filename, file_data, headers=headers)
        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除阿里云OSS中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """
        self._get_client().delete_object(filename)
        return True

    async def get_url(self, filename: str) -> str:
        """获取阿里云OSS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        endpoint = self._strip_scheme(self._get_config().get("endpoint", ""))
        return f"https://{self._bucket}.{endpoint}/{filename}"
