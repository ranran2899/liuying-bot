"""
腾讯云COS存储提供者
"""
from io import BytesIO
from typing import ClassVar

from ..config import get_provider_config
from .base import CloudStorageProvider

_CONFIG_KEY = "TENCENT_COS_CONFIG"


class TencentCosProvider(CloudStorageProvider):
    """腾讯云COS存储提供者"""

    _client: ClassVar[object | None] = None

    @property
    def provider_name(self) -> str:
        return "腾讯云COS"

    @classmethod
    def _get_client(cls):
        """获取COS客户端实例

        返回:
            CosS3Client: COS客户端实例
        """
        if cls._client is None:
            from qcloud_cos import CosConfig, CosS3Client

            config = get_provider_config(_CONFIG_KEY)
            cos_config = CosConfig(
                Region=config.get("region", ""),
                SecretId=config.get("secret_id", ""),
                SecretKey=config.get("secret_key", ""),
            )
            cls._client = CosS3Client(cos_config)
        return cls._client

    def is_configured(self) -> bool:
        config = get_provider_config(_CONFIG_KEY)
        return all(
            (
                config.get("bucket_name"),
                config.get("region"),
                config.get("secret_id"),
                config.get("secret_key"),
            )
        )

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs,
    ) -> str:
        """上传文件到腾讯云COS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储当前不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        client = self._get_client()
        config = get_provider_config(_CONFIG_KEY)

        client.put_object(
            Bucket=config.get("bucket_name", ""),
            Body=BytesIO(file_data),
            Key=filename,
            ContentType=content_type,
        )

        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除腾讯云COS中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """
        client = self._get_client()
        config = get_provider_config(_CONFIG_KEY)

        client.delete_object(
            Bucket=config.get("bucket_name", ""),
            Key=filename,
        )
        return True

    async def get_url(self, filename: str) -> str:
        """获取腾讯云COS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        config = get_provider_config(_CONFIG_KEY)
        return (
            f"https://{config.get('bucket_name', '')}"
            f".cos.{config.get('region', '')}.myqcloud.com/{filename}"
        )
