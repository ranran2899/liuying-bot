"""wife插件核心功能实现"""

from datetime import date

from liuying.configs.config import Config
from liuying.models._user.user_wife import UserWifeRecord
from liuying.models.wife_image import WifeImageRecord
from liuying.utils.message import MessageUtils
from liuying.utils.user.gold import UserGold

from .utils import WifeService


class WifeHandler:
    """wife命令处理器"""

    @classmethod
    async def draw_wife(cls, user_id: str) -> None:
        """处理抽wife命令

        参数:
            user_id: 用户ID
        """
        today = date.today()

        record = await UserWifeRecord.get_user_wife(user_id, today)

        if record:
            wife_name = record.wife_name
            today_count = await UserWifeRecord.get_today_count(today)
            images = await WifeImageRecord.get_all_images_by_wife(wife_name)
            if images:
                await cls._send_wife_result(
                    user_id, wife_name, images[0], today_count, is_new=False
                )
                return

        wife_list = await WifeService.get_wife_list()
        if not wife_list:
            await MessageUtils.build_message("wife库是空的，请先添加wife~").finish()

        wife_record = await WifeService.get_random_wife(wife_list)
        if not wife_record:
            await MessageUtils.build_message("抽取wife失败，请稍后再试~").finish()

        wife_name = wife_record.wife_name
        today_count = await UserWifeRecord.get_today_count(today) + 1
        await UserWifeRecord.set_user_wife(user_id, wife_name, today)
        await cls._send_wife_result(
            user_id, wife_name, wife_record, today_count, is_new=True
        )

    @classmethod
    async def _send_wife_result(
        cls,
        user_id: str,
        wife_name: str,
        wife_record: WifeImageRecord,
        today_count: int,
        *,
        is_new: bool = True,
    ) -> None:
        """发送wife结果消息

        参数:
            user_id: 用户ID
            wife_name: wife名称
            wife_record: wife图片记录
            today_count: 今天的第几个老婆
            is_new: 是否是新抽取的老婆
        """
        enable_gold = Config.get_config("wife", "ENABLE_GOLD", 20)
        image_bytes = await WifeService.get_wife_image_bytes(wife_record)
        if not image_bytes:
            await MessageUtils.build_message(
                f"今天的wife是 {wife_name}，但图片加载失败了~"
            ).finish()

        msg = f"你的今日老婆是「{wife_name}」~\n今天的第{today_count}个老婆"
        if is_new:
            await UserGold.add_user_gold(
                user_id=user_id, amount=enable_gold, source="今日老婆"
            )
            msg += f"\n金币+{enable_gold}"
        await MessageUtils.build_message([msg, image_bytes]).finish(reply_to=True)

    @classmethod
    async def search_wife(cls, wife_name: str) -> None:
        """处理查找wife命令

        参数:
            wife_name: wife名称
        """
        images = await WifeImageRecord.get_all_images_by_wife(wife_name)
        if not images:
            await MessageUtils.build_message(
                f"没有找到 {wife_name} 这个wife (悲"
            ).finish()

        image_bytes = await WifeService.get_wife_image_bytes(images[0])
        if not image_bytes:
            await MessageUtils.build_message(
                f"找到了 {wife_name}，但图片加载失败了~"
            ).finish()
        await MessageUtils.build_message([wife_name, "\n", image_bytes]).finish()

    @classmethod
    async def add_wife(cls, wife_name: str, image_urls: list) -> None:
        """处理添加wife命令

        参数:
            wife_name: wife名称
            image_urls: 图片URL列表
        """
        wife_name = wife_name.strip()

        if not image_urls:
            await MessageUtils.build_message("没有找到图片~").finish()

        if len(image_urls) > 1:
            await MessageUtils.build_message("一次只能添加一个wife哦~").finish()

        image_record, error = await WifeService.download_image(
            image_urls[0], wife_name
        )
        if error:
            await MessageUtils.build_message(f"添加失败: {error}").finish()

        await MessageUtils.build_message(
            f"添加成功! {wife_name} 已加入wife库~ (编号: {image_record.image_id})"
        ).finish()

    @classmethod
    async def del_wife(cls, wife_name: str) -> None:
        """处理删除wife命令

        参数:
            wife_name: wife名称
        """
        count = await WifeService.delete_wife_by_name(wife_name)
        if count == 0:
            await MessageUtils.build_message(
                f"没有找到 {wife_name} 这个wife~"
            ).finish()

        await MessageUtils.build_message(
            f"已删除 {wife_name}，共 {count} 张图片~"
        ).finish()

    @classmethod
    async def clear_wife(cls) -> None:
        """处理清空wife库命令"""
        count = await WifeService.clear_all_wife_images()
        await UserWifeRecord.clear_all_records()

        await MessageUtils.build_message(
            f"已清空wife库，共删除 {count} 个wife~"
        ).finish()

    @classmethod
    async def reset_wife(cls) -> None:
        """处理重置wife库命令"""
        count = await WifeService.clear_all_wife_images()
        await UserWifeRecord.clear_all_records()

        await MessageUtils.build_message(
            f"已重置wife库，共删除 {count} 个wife~"
        ).finish()
