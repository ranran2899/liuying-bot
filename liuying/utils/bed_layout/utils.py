"""
床图工具函数

提供定时删除任务管理、图片格式转换与缩放等辅助功能。
通过 ProviderManager 直接操作存储提供者，避免依赖 BedLayout 业务层，
彻底消除 utils 与 api 之间的循环依赖。
"""
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image

from liuying.utils.apscheduler import task_manager
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

from .config import get_default_storage
from .interfaces import ALLOWED_EXTENSIONS
from .provider_manager import ProviderManager

# 自动删除任务ID前缀，避免与其他任务冲突
_TASK_ID_PREFIX = "auto_delete_image_"


class BedLayoutUtils:
    """
    床图工具类

    封装定时删除任务管理相关的辅助功能。
    """

    @staticmethod
    async def delete_image_task(
        filename: str,
        storage_type: StorageType | None = None,
    ) -> None:
        """定时删除图片任务（支持数据库持久化恢复）

        直接通过 ProviderManager 操作存储提供者，避免依赖 BedLayout 业务层。

        参数:
            filename: 文件名
            storage_type: 存储类型
        """
        actual_type = get_default_storage(storage_type)
        provider = ProviderManager.get_provider(actual_type)
        if provider is None:
            logger.warning(
                f"定时任务删除图片失败: 存储类型 {actual_type} 未配置 | "
                f"文件: {filename}",
                "BedLayout",
            )
            return

        deleted = await provider.delete(filename)
        if deleted:
            logger.debug(f"定时任务自动删除图片: {filename}", "BedLayout")
        else:
            logger.warning(
                f"定时任务删除图片失败(图片可能已被删除): {filename}",
                "BedLayout",
            )

    @staticmethod
    async def schedule_delete_task(
        filename: str,
        delete_at: datetime,
        storage_type: StorageType | None = None,
        task_description: str = "",
    ) -> str | None:
        """创建定时删除图片任务

        参数:
            filename: 文件名
            delete_at: 删除时间
            storage_type: 存储类型
            task_description: 任务描述

        返回:
            str | None: 任务ID，创建失败返回None
        """
        task_id = f"{_TASK_ID_PREFIX}{filename}"

        try:
            await task_manager.add_date_task(
                task_id=task_id,
                func=BedLayoutUtils.delete_image_task,
                run_date=delete_at.isoformat(),
                name=f"自动删除图片-{filename}",
                group="bed_layout_auto_delete",
                description=task_description,
                args=(filename, storage_type),
                save_to_db=True,
            )
            return task_id
        except Exception as e:
            logger.error(f"创建定时删除任务失败: {e}", "BedLayout", e=e)
            return None

    @staticmethod
    async def cancel_auto_delete(filename: str) -> bool:
        """取消图片的自动删除任务

        参数:
            filename: 文件名

        返回:
            bool: 取消成功返回True，任务不存在返回False
        """
        task_id = f"{_TASK_ID_PREFIX}{filename}"
        return await task_manager.remove_task(task_id, delete_from_db=True)

    @staticmethod
    async def update_auto_delete_time(
        filename: str,
        new_minutes: int,
        storage_type: StorageType | None = None,
    ) -> bool:
        """更新图片的自动删除时间

        参数:
            filename: 文件名
            new_minutes: 新的删除分钟数
            storage_type: 存储类型

        返回:
            bool: 更新成功返回True
        """
        task_id = f"{_TASK_ID_PREFIX}{filename}"
        await task_manager.remove_task(task_id, delete_from_db=True)

        delete_at = datetime.now() + timedelta(minutes=new_minutes)

        new_task_id = await BedLayoutUtils.schedule_delete_task(
            filename=filename,
            delete_at=delete_at,
            storage_type=storage_type,
            task_description=(
                f"自动删除床图图片 {filename}，"
                f"更新于 {datetime.now().isoformat()}"
            ),
        )

        return new_task_id is not None


def convert_image_format(file_data: bytes, target_extension: str = ".webp") -> bytes:
    """将图片转换为指定格式

    参数:
        file_data: 原始图片二进制数据
        target_extension: 目标扩展名，默认转换为 webp

    返回:
        bytes: 转换后的图片二进制数据

    异常:
        ValueError: 目标格式不受支持时抛出
    """
    target_ext = target_extension.lower()
    if target_ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"不支持的图片格式: {target_extension}")

    image_format = "JPEG" if target_ext in {".jpg", ".jpeg"} else target_ext[1:].upper()
    with Image.open(BytesIO(file_data)) as img:
        if img.mode in ("RGBA", "P") and image_format == "JPEG":
            img = img.convert("RGB")
        output = BytesIO()
        img.save(output, format=image_format)
        return output.getvalue()


def resize_image(
    file_data: bytes,
    max_size: tuple[int, int] = (1024, 1024),
    resample: int = Image.Resampling.LANCZOS,
) -> bytes:
    """按比例缩放图片，使其长边不超过指定尺寸

    参数:
        file_data: 原始图片二进制数据
        max_size: 最大宽高元组，默认 1024x1024
        resample: PIL 重采样算法，默认 LANCZOS

    返回:
        bytes: 缩放后的图片二进制数据
    """
    with Image.open(BytesIO(file_data)) as img:
        img.thumbnail(max_size, resample=resample)
        output = BytesIO()
        save_format = img.format or "PNG"
        img.save(output, format=save_format)
        return output.getvalue()
