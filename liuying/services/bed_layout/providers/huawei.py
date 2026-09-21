"""华为云OBS存储提供者"""
from typing import Any

from liuying.utils.enum import StorageType

from ..base import CloudStorageProvider, ProviderRegistry


@ProviderRegistry.register(StorageType.HUAWEI)
class HuaweiObsProvider(CloudStorageProvider):
    """华为云OBS存储提供者"""

    _config_key = "HUAWEI_OBS_CONFIG"
    _required_fields = ("endpoint", "bucket_name", "access_key", "secret_key")

    @property
    def provider_name(self) -> str:
        return "华为云OBS"

    @classmethod
    def _create_client(cls) -> object:
        """创建OBS客户端实例"""
        from obs import ObsClient

        config = cls._get_config()
        return ObsClient(
            access_key_id=config.get("access_key", ""),
            secret_access_key=config.get("secret_key", ""),
            server=config.get("endpoint", ""),
        )

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到华为云OBS

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，云存储不做处理仅保持接口兼容

        返回:
            str: 文件访问URL
        """
        headers = {"contentType": content_type} if content_type else None
        self._get_client().putContent(
            bucketName=self._bucket,
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
        self._get_client().deleteObject(bucketName=self._bucket, objectKey=filename)
        return True

    async def get_url(self, filename: str) -> str:
        """获取华为云OBS文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        endpoint = self._strip_scheme(self._get_config().get("endpoint", ""))
        return f"https://{self._bucket}.{endpoint}/{filename}"
