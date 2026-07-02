"""
百度云BOS存储提供者
"""
from io import BytesIO
from typing import ClassVar

from ..config import get_provider_config
from .base import CloudStorageProvider

_CONFIG_KEY = "BAIDU_BOS_CONFIG"


class BaiduBosProvider(CloudStorageProvider):
    """百度云BOS存储提供者"""

    _client: ClassVar[object | None] = None

    @property
    def provider_name(self) -> str:
        return "百度云BOS"

    @classmethod
    def _get_client(cls):
        """获取BOS客户端实例

        返回:
            BosClient: BOS客户端实例
        """
        if cls._client is None:
            from baidubce.auth.bce_credentials import BceCredentials
            from baidubce.bce_client_configuration import BceClientConfiguration
            from baidubce.services.bos.bos_client import BosClient

            config = get_provider_config(_CONFIG_KEY)
            bce_config = BceClientConfiguration(
                credentials=BceCredentials(
                    config.get("access_key", ""),
                    config.get("secret_key", ""),
                ),
                endpoint=config.get("endpoint", ""),
            )
            cls._client = BosClient(bce_config)
        return cls._client

    def is_configured(self) -> bool:
        config = get_provider_config(_CONFIG_KEY)
        return all(
            (
                config.get("bucket_name"),
                config.get("endpoint"),
                config.get("access_key"),
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
        """上传文件到百度云BOS

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
            bucket_name=config.get("bucket_name", ""),
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
        client = self._get_client()
        config = get_provider_config(_CONFIG_KEY)

        client.delete_object(
            bucket_name=config.get("bucket_name", ""),
            key=filename,
        )
        return True

    async def get_url(self, filename: str) -> str:
        """获取百度云BOS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        config = get_provider_config(_CONFIG_KEY)
        return f"https://{config.get('endpoint', '')}/{filename}"
