"""
本地数据库存储提供者

将图片数据存储到本地数据库中，通过HTTP服务提供访问。
"""
from hashlib import sha256
from typing import Any, ClassVar

from liuying.models._bot import BedLayoutImage
from liuying.utils.log import logger

from ...http.http_utils import AsyncHttpx
from ..http.config import BedLayoutHttpConfig
from ..interfaces import generate_filename, validate_extension
from .base import CloudStorageProvider


class LocalStorageProvider(CloudStorageProvider):
    """本地数据库存储提供者"""

    _client: ClassVar[object | None] = None

    @property
    def provider_name(self) -> str:
        return "本地数据库"

    @classmethod
    def _get_client(cls):
        """获取数据库操作客户端

        本地存储使用ORM模型直接操作，无需额外客户端

        返回:
            type[BedLayoutImage]: 图片模型类
        """
        if cls._client is None:
            cls._client = BedLayoutImage
        return cls._client

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
        enable_dedup = kwargs.pop("enable_dedup", True)
        if enable_dedup:
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

    async def download_image(
        self,
        url: str,
        filename: str | None = None,
        extension: str = ".png",
        content_type: str | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> tuple[str | None, str]:
        """从URL下载图片并保存到本地数据库图床

        参数:
            url: 图片URL
            filename: 自定义文件名，不指定则自动生成UUID
            extension: 图片扩展名，默认.png
            content_type: MIME类型
            timeout: 请求超时时间（秒）
            **kwargs: 上传时透传的扩展元数据

        返回:
            tuple[str | None, str]: (图片访问URL, 错误信息)，
            成功时错误信息为空字符串
        """
        validate_extension(extension)
        filename = generate_filename(filename, extension)

        try:
            file_data = await AsyncHttpx.get_content(
                url,
                timeout=timeout,
                follow_redirects=True,
            )
        except Exception as e:
            error_msg = f"下载图片失败: {e}"
            logger.error(error_msg, self.provider_name, e=e)
            return None, error_msg

        try:
            url_result = await self.upload(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                original_url=url,
                **kwargs,
            )
        except Exception as e:
            error_msg = f"保存图片失败: {e}"
            logger.error(error_msg, self.provider_name, e=e)
            return None, error_msg

        logger.success(f"下载并保存图片成功: {url_result}", self.provider_name)
        return url_result, ""
