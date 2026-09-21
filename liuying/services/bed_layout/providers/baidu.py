"""百度云BOS存储提供者"""
from io import BytesIO
from typing import Any

from liuying.utils.enum import StorageType

from ..base import CloudStorageProvider, ProviderRegistry


@ProviderRegistry.register(StorageType.BAIDU)
class BaiduBosProvider(CloudStorageProvider):
    """百度云BOS存储提供者"""

    _config_key = "BAIDU_BOS_CONFIG"
    _required_fields = ("bucket_name", "endpoint", "access_key", "secret_key")

    @property
    def provider_name(self) -> str:
        return "百度云BOS"

    @classmethod
    def _create_client(cls) -> object:
        """创建BOS客户端实例"""
        from baidubce.auth.bce_credentials import BceCredentials
        from baidubce.bce_client_configuration import BceClientConfiguration
        from baidubce.services.bos.bos_client import BosClient

        config = cls._get_config()
        bce_config = BceClientConfiguration(
            credentials=BceCredentials(
                config.get("access_key", ""),
                config.get("secret_key", ""),
            ),
            endpoint=config.get("endpoint", ""),
        )
        return BosClient(bce_config)

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到百度云BOS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        self._get_client().put_object(
            bucket_name=self._bucket,
            key=filename,
            data=BytesIO(file_data),
            content_length=len(file_data),
            content_type=content_type,
        )
        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除百度云BOS中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """
        self._get_client().delete_object(bucket_name=self._bucket, key=filename)
        return True

    async def get_url(self, filename: str) -> str:
        """获取百度云BOS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        endpoint = self._get_config().get("endpoint", "")
        return f"https://{endpoint}/{filename}"
