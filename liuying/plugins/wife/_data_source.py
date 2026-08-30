"""wife插件核心业务逻辑"""

from datetime import date

from liuying.configs.config import Config
from liuying.utils.bed_layout import BedLayout
from liuying.utils.bed_layout.providers.local import LocalStorageProvider
from liuying.utils.enum import StorageType
from liuying.utils.log import logger
from liuying.utils.user.gold import UserGold

from .models import UserWifeRecord, WifeImageRecord

MessageType = str | list[str | bytes]


class WifeManage:
    """wife业务处理，返回消息内容交由handler发送"""

    @staticmethod
    async def draw_wife(user_id: str) -> MessageType:
        """处理抽wife

        参数:
            user_id: 用户ID

        返回:
            MessageType: 消息内容
        """
        today = date.today()

        record = await UserWifeRecord.get_user_wife(user_id, today)
        if record:
            images = await WifeImageRecord.get_all_images_by_wife(record.wife_name)
            if images:
                return await WifeManage._build_wife_result(
                    user_id,
                    record.wife_name,
                    images[0],
                    await UserWifeRecord.get_today_count(today),
                    is_new=False,
                )

        wife = await WifeImageRecord.get_random_image()
        if not wife:
            return "wife库是空的，请先添加wife~"

        await UserWifeRecord.set_user_wife(user_id, wife.wife_name, today)
        return await WifeManage._build_wife_result(
            user_id,
            wife.wife_name,
            wife,
            await UserWifeRecord.get_today_count(today),
        )

    @staticmethod
    async def _build_wife_result(
        user_id: str,
        wife_name: str,
        image_record: WifeImageRecord,
        today_count: int,
        *,
        is_new: bool = True,
    ) -> MessageType:
        """构建抽wife结果消息

        参数:
            user_id: 用户ID
            wife_name: wife名称
            image_record: wife图片记录
            today_count: 今天的第几个老婆
            is_new: 是否是新抽取的老婆

        返回:
            MessageType: 消息内容
        """
        image_bytes = await BedLayout.get_bytes(
            image_record.file_path, storage_type=StorageType.LOCAL
        )
        if not image_bytes:
            return f"今天的wife是 {wife_name}，但图片加载失败了~"

        gold = Config.get_config("wife", "ENABLE_GOLD", 20)
        msg = f"#你的今日老婆是「{wife_name}」~\n今天的第{today_count}个老婆"
        if is_new:
            await UserGold.add_user_gold(
                user_id=user_id, amount=gold, source="今日老婆"
            )
            msg += f"\n金币+{gold}"
        return [msg, image_bytes]

    @staticmethod
    async def search_wife(wife_name: str) -> MessageType:
        """处理查找wife

        参数:
            wife_name: wife名称

        返回:
            MessageType: 消息内容
        """
        images = await WifeImageRecord.get_all_images_by_wife(wife_name)
        if not images:
            return f"没有找到 {wife_name} 这个wife (悲"

        image_bytes = await BedLayout.get_bytes(
            images[0].file_path, storage_type=StorageType.LOCAL
        )
        if not image_bytes:
            return f"找到了 {wife_name}，但图片加载失败了~"
        return [wife_name, "\n", image_bytes]

    @staticmethod
    async def add_wife(wife_name: str, image_urls: list[str]) -> str:
        """处理添加wife

        参数:
            wife_name: wife名称
            image_urls: 图片URL列表

        返回:
            str: 消息内容
        """
        if len(image_urls) > 1:
            return "一次只能添加一个wife哦~"

        image_id = await WifeImageRecord.get_next_image_id(wife_name)
        filename = f"二次元老婆/{wife_name}/{image_id}.png"

        provider = LocalStorageProvider()
        _, error = await provider.download_image(
            url=image_urls[0],
            filename=filename,
            extension=".png",
        )
        if error:
            logger.error(error, command="wife")
            return f"添加失败: {error}"

        await WifeImageRecord.create(
            wife_name=wife_name, image_id=image_id, file_path=filename
        )
        logger.success(f"下载图片成功: {wife_name} - {image_id}", command="wife")
        return f"添加成功! {wife_name} 已加入wife库~ (编号: {image_id})"

    @staticmethod
    async def del_wife(wife_name: str) -> str:
        """处理删除wife

        参数:
            wife_name: wife名称

        返回:
            str: 消息内容
        """
        images = await WifeImageRecord.get_all_images_by_wife(wife_name)
        if not images:
            return f"没有找到 {wife_name} 这个wife~"

        for image in images:
            await BedLayout.delete(image.file_path, storage_type=StorageType.LOCAL)
        await WifeImageRecord.soft_delete_all_by_wife(wife_name)
        return f"已删除 {wife_name}，共 {len(images)} 张图片~"

    @staticmethod
    async def _wipe_wife_images() -> int:
        """删除所有wife图片与抽取记录

        返回:
            int: 删除的图片数量
        """
        images = await WifeImageRecord.get_all_images()
        for image in images:
            await BedLayout.delete(image.file_path, storage_type=StorageType.LOCAL)

        await WifeImageRecord.delete_all()
        await UserWifeRecord.clear_all_records()
        return len(images)

    @classmethod
    async def clear_wife(cls) -> str:
        """处理清空wife库

        返回:
            str: 消息内容
        """
        count = await cls._wipe_wife_images()
        return f"已清空wife库，共删除 {count} 个wife~"

    @classmethod
    async def reset_wife(cls) -> str:
        """处理重置wife库

        返回:
            str: 消息内容
        """
        count = await cls._wipe_wife_images()
        return f"已重置wife库，共删除 {count} 个wife~"
