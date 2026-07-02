"""
华为云OBS存储提供者
"""
from typing import ClassVar

from ..config import get_provider_config
from .base import CloudStorageProvider

_CONFIG_KEY = "HUAWEI_OBS_CONFIG"


class HuaweiObsProvider(CloudStorageProvider):
    """华为云OBS存储提供者"""

    _client: ClassVar[object | None] = None

    @property
    def provider_name(self) -> str:
        return "华为云OBS"

    @classmethod
    def _get_client(cls):
        """获取OBS客户端实例

        返回:
            ObsClient: OBS客户端实例
        """
        if cls._client is None:
            from obs import ObsClient

            config = get_provider_config(_CONFIG_KEY)
            cls._client = ObsClient(
                access_key_id=config.get("access_key", ""),
                secret_access_key=config.get("secret_key", ""),
                server=config.get("endpoint", ""),
            )
        return cls._client

    def is_configured(self) -> bool:
        config = get_provider_config(_CONFIG_KEY)
        return all(
            (
                config.get("endpoint"),
                config.get("bucket_name"),
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
        """上传文件到华为云OBS

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

        headers = {"contentType": content_type} if content_type else None
        client.putContent(
            bucketName=config.get("bucket_name", ""),
            objectKey=filename,
            content=file_data,
            headers=headers,
        )

        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除华为云OBS中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """
        client = self._get_client()
        config = get_provider_config(_CONFIG_KEY)

        client.deleteObject(
            bucketName=config.get("bucket_name", ""),
            objectKey=filename,
        )
        return True

    async def get_url(self, filename: str) -> str:
        """获取华为云OBS文件访问URL

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
