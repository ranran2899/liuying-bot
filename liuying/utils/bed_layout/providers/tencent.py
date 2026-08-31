"""腾讯云COS存储提供者"""
from io import BytesIO
from typing import Any

from liuying.utils.enum import StorageType

from ..base import CloudStorageProvider, ProviderRegistry


@ProviderRegistry.register(StorageType.TENCENT)
class TencentCosProvider(CloudStorageProvider):
    """腾讯云COS存储提供者"""

    _config_key = "TENCENT_COS_CONFIG"
    _required_fields = ("bucket_name", "region", "secret_id", "secret_key")

    @property
    def provider_name(self) -> str:
        return "腾讯云COS"

    @classmethod
    def _create_client(cls) -> object:
        """创建COS客户端实例"""
        from qcloud_cos import CosConfig, CosS3Client

        config = cls._get_config()
        cos_config = CosConfig(
            Region=config.get("region", ""),
            SecretId=config.get("secret_id", ""),
            SecretKey=config.get("secret_key", ""),
        )
        return CosS3Client(cos_config)

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到腾讯云COS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        self._get_client().put_object(
            Bucket=self._bucket,
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
        self._get_client().delete_object(Bucket=self._bucket, Key=filename)
        return True

    async def get_url(self, filename: str) -> str:
        """获取腾讯云COS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        region = self._get_config().get("region", "")
        return f"https://{self._bucket}.cos.{region}.myqcloud.com/{filename}"
