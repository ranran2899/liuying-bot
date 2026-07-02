"""
床图统一API接口

提供图片上传、删除、获取URL等核心业务功能。
所有调用方应通过本模块的 BedLayout 类访问存储功能，
禁止直接调用具体 Provider 实现。
"""
from datetime import datetime, timedelta
import mimetypes
from pathlib import Path
from typing import Any

import aiofiles

from liuying.utils.enum import StorageType
from liuying.utils.log import logger
from liuying.utils.utils import get_image_size

from .config import get_default_storage
from .http.config import BedLayoutHttpConfig
from .interfaces import generate_filename, validate_extension
from .provider_manager import ProviderManager
from .providers.local import LocalStorageProvider
from .utils import BedLayoutUtils


class BedLayout:
    """
    床图操作类

    封装图片上传、删除、获取URL等核心业务，
    通过统一的存储提供者接口支持本地存储和云存储。
    """

    @classmethod
    def _get_provider(cls, storage_type: StorageType):
        """获取存储提供者，未配置时回退到本地存储

        参数:
            storage_type: 存储类型

        返回:
            CloudStorageProvider: 存储提供者实例
        """
        provider = ProviderManager.get_provider(storage_type)
        if provider is not None:
            return provider
        logger.warning(
            f"存储类型 {storage_type} 未配置，将使用本地数据库存储",
            "BedLayout",
        )
        return ProviderManager.get_provider(StorageType.LOCAL)

    @classmethod
    async def upload(
        cls,
        file_data: bytes,
        filename: str | None = None,
        extension: str = ".png",
        content_type: str | None = None,
        original_filename: str | None = None,
        storage_type: StorageType | None = None,
        **kwargs: Any,
    ) -> tuple[str, StorageType, str]:
        """上传图片到存储

        参数:
            file_data: 图片二进制数据
            filename: 自定义文件名，不指定则自动生成
            extension: 图片扩展名，默认.png
            content_type: MIME类型
            original_filename: 原始文件名
            storage_type: 存储类型，不指定则使用默认配置
            **kwargs: 扩展元数据，支持 source/category/tags/original_url/
                description/enable_dedup

        返回:
            tuple[str, StorageType, str]: 图片访问URL、实际存储类型、最终文件名
        """
        validate_extension(extension)
        storage_type = get_default_storage(storage_type)
        filename = generate_filename(filename, extension)

        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)

        provider = cls._get_provider(storage_type)
        actual_type = (
            storage_type
            if provider is not ProviderManager.get_provider(StorageType.LOCAL)
            else StorageType.LOCAL
        )

        url = await provider.upload(
            file_data,
            filename,
            content_type,
            original_filename=original_filename,
            **kwargs,
        )
        logger.info(
            f"上传图片成功: {filename} | 存储: {provider.provider_name}",
            "BedLayout",
        )
        return url, actual_type, filename

    @classmethod
    async def upload_from_file(
        cls,
        file_path: Path | str,
        filename: str | None = None,
        storage_type: StorageType | None = None,
        **kwargs: Any,
    ) -> tuple[str, StorageType, str]:
        """从文件上传图片到存储

        参数:
            file_path: 源图片路径
            filename: 自定义文件名，不指定则自动生成
            storage_type: 存储类型，不指定则使用默认配置
            **kwargs: 上传时透传的扩展元数据

        返回:
            tuple[str, StorageType, str]: 图片访问URL、实际存储类型、最终文件名
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {file_path}")

        extension = file_path.suffix.lower()
        validate_extension(extension)

        async with aiofiles.open(file_path, "rb") as f:
            file_data = await f.read()

        content_type, _ = mimetypes.guess_type(str(file_path))

        return await cls.upload(
            file_data=file_data,
            filename=filename,
            extension=extension,
            content_type=content_type,
            original_filename=file_path.name,
            storage_type=storage_type,
            **kwargs,
        )

    @classmethod
    async def delete(
        cls,
        filename: str,
        storage_type: StorageType | None = None,
    ) -> bool:
        """删除图片

        参数:
            filename: 文件名
            storage_type: 存储类型，不指定则使用默认配置

        返回:
            bool: 删除成功返回True，图片不存在返回False
        """
        storage_type = get_default_storage(storage_type)
        provider = ProviderManager.get_provider(storage_type)
        if provider is None:
            logger.warning(f"存储类型 {storage_type} 未配置", "BedLayout")
            return False

        result = await provider.delete(filename)
        if result:
            logger.info(
                f"删除图片成功: {filename} | 存储: {provider.provider_name}",
                "BedLayout",
            )
        return result

    @classmethod
    async def get_url(
        cls,
        filename: str,
        storage_type: StorageType | None = None,
    ) -> str:
        """获取图片访问URL

        参数:
            filename: 文件名
            storage_type: 存储类型，不指定则使用默认配置

        返回:
            str: 图片访问URL
        """
        storage_type = get_default_storage(storage_type)
        provider = ProviderManager.get_provider(storage_type)
        if provider is None:
            return BedLayoutHttpConfig.get_image_url(filename)

        return await provider.get_url(filename)

    @classmethod
    async def get_bytes(
        cls,
        filename: str,
        storage_type: StorageType | None = None,
    ) -> bytes | None:
        """获取图片的字节数据（仅支持本地数据库存储）

        参数:
            filename: 文件名
            storage_type: 存储类型，不指定则使用默认配置

        返回:
            bytes | None: 图片字节数据，不存在返回None
        """
        storage_type = get_default_storage(storage_type)
        provider = ProviderManager.get_provider(storage_type)

        if isinstance(provider, LocalStorageProvider):
            return await provider.get_bytes(filename)

        logger.warning("get_bytes 仅支持本地数据库存储", "BedLayout")
        return None

    @classmethod
    async def save_image_bytes(
        cls,
        file_data: bytes,
        filename: str | None = None,
        extension: str = ".png",
        content_type: str | None = None,
        original_filename: str | None = None,
        delete_after_minutes: int = 1440,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """保存图片字节数据并返回访问URL，同时设置定时删除任务

        参数:
            file_data: 图片字节数据
            filename: 自定义文件名
            extension: 图片扩展名
            content_type: MIME类型
            original_filename: 原始文件名
            delete_after_minutes: 自动删除分钟数，默认1440分钟（1天）
            **kwargs: 上传时透传的扩展元数据

        返回:
            dict[str, Any]: 包含 url, filename, delete_at, task_id,
            storage_type, width, height 的字典
        """
        url, storage_type, filename_result = await cls.upload(
            file_data=file_data,
            filename=filename,
            extension=extension,
            content_type=content_type,
            original_filename=original_filename,
            **kwargs,
        )

        width, height = get_image_size(file_data)
        delete_at = datetime.now() + timedelta(minutes=delete_after_minutes)

        task_id = await BedLayoutUtils.schedule_delete_task(
            filename=filename_result,
            delete_at=delete_at,
            storage_type=storage_type,
            task_description=(
                f"自动删除床图图片 {filename_result}，"
                f"创建于 {datetime.now().isoformat()}"
            ),
        )

        return {
            "url": url,
            "filename": filename_result,
            "delete_at": delete_at,
            "task_id": task_id,
            "storage_type": storage_type,
            "width": width,
            "height": height,
        }
