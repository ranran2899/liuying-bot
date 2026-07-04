"""
签到插件工具函数
"""
from datetime import datetime
import random

from nonebot import get_driver

from liuying.configs.config import Config
from liuying.configs.path_config import TEMP_PATH
from liuying.liuying_plugins.economy.shop import register_items
from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.utils.apscheduler import task_manager
from liuying.utils.bed_layout import BedLayout
from liuying.utils.log import logger
from liuying.utils.user import UserSign

SIGN_IN_IMAGE_PATH = TEMP_PATH / "signIn"
driver = get_driver()

SIGNIN_ITEMS = [
    {
        "name": "好感度值双倍卡",
        "id": "double_favor_card",
        "description": "使用后当天签到获得的好感度值翻倍",
        "type": "增益道具",
        "rarity": 3,
        "image_url": "https://gitee.com/shiranranran/tuku/raw/master/tu/signIn/hgdx2.png",
        "is_visible": 1,
        "price": 50,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    }
]


@driver.on_startup
async def init_signin_items() -> None:
    """插件启动时初始化签到道具"""
    await register_items(SIGNIN_ITEMS)


@task_manager.cron_task("reset_daily_sign", hour=0, minute=0, second=0)
async def reset_daily_sign() -> None:
    """每天凌晨0点重置所有用户的签到状态"""
    reset_count = await UserSign.reset_all_signed_in_users()
    logger.info(f"每日签到状态重置完成，共重置 {reset_count} 个用户")


@task_manager.cron_task("clear_sign_in_images", hour=23, minute=59, second=0)
async def clear_sign_in_images() -> None:
    """每天23:59清空签到图片"""
    deleted_count = 0
    for file_path in SIGN_IN_IMAGE_PATH.glob("*.png"):
        try:
            file_path.unlink()
            deleted_count += 1
        except Exception as e:
            logger.error(f"清空签到图片失败: {e}")

    logger.info(f"已清空签到图片，共删除 {deleted_count} 个文件")


class SignInUtils:
    """签到工具类，封装签到相关的图片上传、奖励计算、道具操作"""

    @staticmethod
    async def upload_image(
        user_id: str, image_bytes: bytes
    ) -> tuple[str, str, str]:
        """上传签到图片到云存储

        参数:
            user_id: 用户ID
            image_bytes: 图片字节数据

        返回:
            tuple[str, str, str]: 图片URL、宽度、高度，失败则返回空字符串元组
        """
        filename = (
            f"sign_in/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        )
        result = await BedLayout.save_image_bytes(
            file_data=image_bytes,
            filename=filename,
            extension=".png",
            content_type="image/png",
            delete_after_minutes=1,
        )

        image_url = result.get("url", "")
        if not image_url:
            return "", "", ""

        return image_url, result.get("width", ""), result.get("height", "")

    @staticmethod
    def calc_reward(consecutive_days: int) -> dict[str, int]:
        """计算签到奖励

        参数:
            consecutive_days: 连续签到天数

        返回:
            dict[str, int]: 包含金币和好感度经验的奖励字典
        """
        max_base_gold = Config.get_config("signIn", "SIGN_GOLD") or 50
        max_consecutive_bonus = (
            Config.get_config("signIn", "MAX_SIGN_GOLD") or 30
        )
        max_base_favor = (
            Config.get_config("signIn", "BASE_FAVOR_EXPERIENCE") or 30
        )
        max_favor_bonus = (
            Config.get_config("signIn", "CONSECUTIVE_FAVOR_BONUS") or 3
        )

        base_gold = random.randint(1, max_base_gold)
        consecutive_gold_bonus = min(consecutive_days, max_consecutive_bonus)
        base_favor = random.randint(1, max_base_favor)
        consecutive_favor_bonus = min(consecutive_days, max_favor_bonus)

        return {
            "gold": base_gold + consecutive_gold_bonus,
            "favorExperience": base_favor + consecutive_favor_bonus,
            "baseGold": base_gold,
            "consecutiveGoldBonus": consecutive_gold_bonus,
            "baseFavor": base_favor,
            "consecutiveFavorBonus": consecutive_favor_bonus,
        }

    @staticmethod
    async def use_double_card(user_id: str) -> bool:
        """检查并使用好感度值双倍卡

        参数:
            user_id: 用户ID

        返回:
            bool: 是否成功使用双倍卡
        """
        user_items = await ItemInventory.get_items(user_id)

        if not any(
            item["id"] == "double_favor_card" and item["count"] > 0
            for item in user_items
        ):
            return False

        if await ItemInventory.reduce(user_id, "double_favor_card"):
            logger.info(f"用户 {user_id} 成功使用了好感度值双倍卡")
            return True

        logger.debug(f"用户 {user_id} 使用好感度值双倍卡失败")
        return False

    @staticmethod
    async def drop_item(user_id: str) -> bool:
        """签到掉落道具

        参数:
            user_id: 用户ID

        返回:
            bool: 是否成功掉落道具
        """
        drop_rate = Config.get_config("signIn", "ITEM_DROP_RATE") or 50

        if random.randint(1, 100) > drop_rate:
            return False

        if await ItemInventory.add(user_id, "double_favor_card"):
            logger.info(f"用户 {user_id} 签到掉落了好感度值双倍卡")
            return True

        logger.debug(f"用户 {user_id} 签到未掉落道具")
        return False
