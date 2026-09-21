"""本地数据库存储提供者

将图片数据存储到本地数据库中，通过HTTP服务提供访问。
"""
from hashlib import sha256
from typing import Any

from liuying.models._bot import BedLayoutImage
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

from ..base import ProviderRegistry, StorageProvider
from ..http.config import BedLayoutHttpConfig


@ProviderRegistry.register(StorageType.LOCAL)
class LocalStorageProvider(StorageProvider):
    """本地数据库存储提供者"""

    @property
    def provider_name(self) -> str:
        return "本地数据库"

    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到本地数据库

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据，支持 source/category/tags/original_url/
                original_filename/description/enable_dedup

        返回:
            str: 文件访问URL，若启用去重且图片已存在则返回已有URL
        """
        if kwargs.pop("enable_dedup", True):
            file_hash = sha256(file_data).hexdigest()
            existing = await BedLayoutImage.get_image_by_hash(file_hash)
            if existing is not None:
                logger.debug(
                    f"检测到重复图片，复用已有记录: {existing.filename}",
                    self.provider_name,
                )
                return await self.get_url(existing.filename)

        await BedLayoutImage.save_image(
            filename=filename,
            file_data=file_data,
            content_type=content_type,
            original_filename=kwargs.get("original_filename"),
            description=kwargs.get("description"),
            source=kwargs.get("source"),
            category=kwargs.get("category"),
            tags=kwargs.get("tags"),
            original_url=kwargs.get("original_url"),
        )
        return await self.get_url(filename)

    async def delete(self, filename: str) -> bool:
        """删除本地数据库中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True，图片不存在返回False
        """
        return await BedLayoutImage.delete_image_by_filename(filename)

    async def get_url(self, filename: str) -> str:
        """获取本地存储文件的访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """
        return BedLayoutHttpConfig.get_image_url(filename)

    async def get_bytes(self, filename: str) -> bytes | None:
        """获取文件的二进制数据

        参数:
            filename: 文件名

        返回:
            bytes | None: 文件二进制数据，不存在返回None
        """
        image = await BedLayoutImage.get_image_by_filename(filename)
        return image.file_data if image else None

    def is_configured(self) -> bool:
        """本地存储始终可用"""
        return True
