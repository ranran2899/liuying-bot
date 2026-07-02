"""wife插件服务层"""

import random

from liuying.models.wife_image import WifeImageRecord
from liuying.utils.bed_layout import BedLayout
from liuying.utils.bed_layout.providers.local import LocalStorageProvider
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

WIFE_IMAGE_DIR = "二次元老婆"


class WifeService:
    """wife插件服务类，封装图片相关操作"""

    @staticmethod
    async def get_wife_list() -> list[WifeImageRecord]:
        """获取所有wife图片记录列表

        返回:
            list[WifeImageRecord]: wife图片记录列表
        """
        return await WifeImageRecord.get_all_images()

    @staticmethod
    async def get_random_wife(
        wife_list: list[WifeImageRecord],
    ) -> WifeImageRecord | None:
        """从列表中随机选择一个wife

        参数:
            wife_list: wife图片记录列表

        返回:
            WifeImageRecord | None: 随机选择的wife记录，列表为空返回None
        """
        return random.choice(wife_list) if wife_list else None

    @staticmethod
    async def download_image(
        url: str, wife_name: str
    ) -> tuple[WifeImageRecord | None, str]:
        """下载图片并保存到本地图床

        参数:
            url: 图片URL
            wife_name: wife名称

        返回:
            tuple[WifeImageRecord | None, str]: (图片记录, 错误信息)，
            成功时错误信息为空字符串
        """
        image_id = await WifeImageRecord.get_next_image_id(wife_name)
        filename = f"{WIFE_IMAGE_DIR}/{wife_name}/{image_id}.png"

        provider = LocalStorageProvider()
        _, error = await provider.download_image(
            url=url,
            filename=filename,
            extension=".png",
        )
        if error:
            logger.error(error, command="wife")
            return None, error

        image_record = await WifeImageRecord.create_image_record(
            wife_name=wife_name,
            image_id=image_id,
            file_path=filename,
        )
        logger.success(
            f"下载图片成功: {wife_name} - {image_id}", command="wife"
        )
        return image_record, ""

    @staticmethod
    async def delete_wife_image(wife_name: str, image_id: int) -> bool:
        """删除wife图片

        参数:
            wife_name: wife名称
            image_id: 图片编号

        返回:
            bool: 删除成功返回True
        """
        image_record = await WifeImageRecord.get_image_by_id(wife_name, image_id)
        if not image_record:
            return False

        filename = f"{WIFE_IMAGE_DIR}/{wife_name}/{image_id}.png"
        await BedLayout.delete(filename, storage_type=StorageType.LOCAL)
        await WifeImageRecord.soft_delete_image(wife_name, image_id)
        return True

    @staticmethod
    async def delete_wife_by_name(wife_name: str) -> int:
        """删除指定wife的所有图片

        参数:
            wife_name: wife名称

        返回:
            int: 删除的图片数量
        """
        images = await WifeImageRecord.get_all_images_by_wife(wife_name)
        for image in images:
            filename = f"{WIFE_IMAGE_DIR}/{wife_name}/{image.image_id}.png"
            await BedLayout.delete(filename, storage_type=StorageType.LOCAL)
            await WifeImageRecord.soft_delete_image(wife_name, image.image_id)
        return len(images)

    @staticmethod
    async def clear_all_wife_images() -> int:
        """清空所有wife图片

        返回:
            int: 删除的图片数量
        """
        images = await WifeImageRecord.get_all_images()
        for image in images:
            filename = (
                f"{WIFE_IMAGE_DIR}/{image.wife_name}/{image.image_id}.png"
            )
            await BedLayout.delete(filename, storage_type=StorageType.LOCAL)

        await WifeImageRecord.hard_delete_all_deleted()
        return len(images)

    @staticmethod
    async def get_wife_image_bytes(
        image_record: WifeImageRecord,
    ) -> bytes | None:
        """获取wife图片的字节数据

        参数:
            image_record: 图片记录

        返回:
            bytes | None: 图片字节数据，不存在返回None
        """
        filename = (
            f"{WIFE_IMAGE_DIR}/{image_record.wife_name}"
            f"/{image_record.image_id}.png"
        )
        return await BedLayout.get_bytes(filename, storage_type=StorageType.LOCAL)
