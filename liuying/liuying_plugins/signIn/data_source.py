"""签到插件数据源：道具初始化、奖励结算、卡片生成与上传"""

import asyncio
from datetime import datetime
import json
import random

from nonebot_plugin_alconna import Button
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.configs.path_config import TEMP_PATH
from liuying.liuying_plugins.economy.shop import register_items
from liuying.liuying_plugins.economy.shop.inventory import ItemInventory
from liuying.liuying_plugins.economy.shop.rarity import RaritySystem
from liuying.liuying_plugins.economy.shop.template import TemplateRepository
from liuying.models._user.user_exp import UserExpInfo
from liuying.models._user.user_info import UserInfo
from liuying.models._user.user_intro import UserIntroInfo
from liuying.models._user.user_sign import UserSignInfo
from liuying.models._user.user_sign_log import UserSignLog
from liuying.ui.services import render
from liuying.utils.bed_layout import BedLayout
from liuying.utils.calendar import Greeting, TimeSeason
from liuying.utils.log import logger
from liuying.utils.utils import format_image_url

SIGN_IN_IMAGE_PATH = TEMP_PATH / "signIn"
"""签到卡片本地缓存目录，当日重复签到直接复用"""
if not SIGN_IN_IMAGE_PATH.exists():
    SIGN_IN_IMAGE_PATH.mkdir(parents=True)

SIGNIN_ITEMS: list[dict] = [
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


class SignInManage:
    """签到业务管理：资料同步、签到结算、奖励发放、卡片渲染与上传"""

    @staticmethod
    async def init_items() -> None:
        """插件启动时注册签到道具"""
        await register_items(SIGNIN_ITEMS)

    @staticmethod
    def calc_reward(consecutive_days: int) -> dict[str, int]:
        """根据连续签到天数计算奖励

        参数:
            consecutive_days: 连续签到天数

        返回:
            dict[str, int]: 包含金币与好感度经验明细的奖励字典
        """
        base_gold = random.randint(1, Config.get_config("signIn", "SIGN_GOLD") or 50)
        base_favor = random.randint(
            1, Config.get_config("signIn", "BASE_FAVOR_EXPERIENCE") or 30
        )
        gold_bonus = min(
            consecutive_days, Config.get_config("signIn", "MAX_SIGN_GOLD") or 30
        )
        favor_bonus = min(
            consecutive_days,
            Config.get_config("signIn", "CONSECUTIVE_FAVOR_BONUS") or 3,
        )
        return {
            "gold": base_gold + gold_bonus,
            "favorExperience": base_favor + favor_bonus,
            "baseGold": base_gold,
            "consecutiveGoldBonus": gold_bonus,
            "baseFavor": base_favor,
            "consecutiveFavorBonus": favor_bonus,
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
        """签到概率掉落好感度值双倍卡

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

    @staticmethod
    async def build_user_data(
        record: UserSignInfo,
        user_name: str,
        platform: str,
        *,
        is_duplicate: bool,
    ) -> dict:
        """基于已有签到记录构建渲染所需的用户数据

        参数:
            record: 用户签到记录
            user_name: 用户名称
            platform: 平台信息
            is_duplicate: 是否重复签到

        返回:
            dict: 用户数据字典
        """
        favor_exp_info, user_uid = await asyncio.gather(
            UserExpInfo.get_both_progress(record.user_id),
            UserInfo.get_user_uid(record.user_id),
        )
        favor = favor_exp_info["favor"]
        return {
            "uid": user_uid,
            "userName": user_name,
            "favorInfo": {
                "level": favor["favor"],
                "experience": favor["current_exp"],
                "nextLevelExperience": favor["next_exp"],
            },
            "totalSignInDays": record.total_days,
            "signInInfo": {"consecutive_days": record.consecutive_days},
            "firstSignDate": record.first_sign_in_date,
            "lastSignDate": record.last_sign_in_date,
            "platform": platform,
            "isDuplicate": is_duplicate,
            "usedDoubleCard": False,
            "droppedItem": False,
        }

    @staticmethod
    async def _sync_profile(
        user_id: str, user_name: str, avatar: str | None, platform: str
    ) -> None:
        """同步用户昵称/头像/平台到用户介绍表"""
        await UserIntroInfo.update_profile(user_id, user_name, avatar or "", platform)

    @classmethod
    async def sign_in(cls, session: Uninfo) -> bytes:
        """执行签到结算并生成签到卡片

        参数:
            session: 会话信息

        返回:
            bytes: 签到卡片图片字节数据
        """
        user_id = session.user.id
        user_name = session.user.name
        platform = session.adapter
        avatar = session.user.avatar

        await cls._sync_profile(user_id, user_name, avatar, platform)

        record = await UserSignInfo.sign(user_id)
        reward = cls.calc_reward(record.consecutive_days)

        used_double_card, dropped_item = await asyncio.gather(
            cls.use_double_card(user_id), cls.drop_item(user_id)
        )
        if used_double_card:
            reward["favorExperience"] *= 2

        await asyncio.gather(
            UserExpInfo.add_favor_exp(user_id, reward["favorExperience"]),
            UserInfo.add_gold(user_id=user_id, gold=reward["gold"]),
        )

        user_data = await cls.build_user_data(
            record, user_name, platform, is_duplicate=False
        )
        user_data["usedDoubleCard"] = used_double_card
        user_data["droppedItem"] = dropped_item
        return await cls.gen_sign_img(user_id, user_name, user_data, reward, avatar)

    @classmethod
    async def duplicate_card(cls, session: Uninfo, record: UserSignInfo) -> bytes:
        """生成重复签到卡片，优先复用当日缓存图片

        参数:
            session: 会话信息
            record: 已查询到的用户签到记录

        返回:
            bytes: 签到卡片图片字节数据
        """
        user_id = session.user.id
        user_name = session.user.name
        platform = session.adapter
        avatar = session.user.avatar

        await cls._sync_profile(user_id, user_name, avatar, platform)

        image_path = SIGN_IN_IMAGE_PATH / f"{user_id}.png"
        if image_path.exists():
            return image_path.read_bytes()

        user_data = await cls.build_user_data(
            record, user_name, platform, is_duplicate=True
        )
        return await cls.gen_sign_img(
            user_id, user_name, user_data, {"gold": 0, "favorExperience": 0}, avatar
        )

    @staticmethod
    async def _build_item_info() -> dict | None:
        """构建掉落道具的展示信息

        返回:
            dict | None: 道具展示信息，模板不存在时返回None
        """
        template = await TemplateRepository.find("double_favor_card")
        if not template:
            return None

        rarity = template.get("rarity", 1)
        return {
            "id": template.get("id", ""),
            "name": template.get("name", ""),
            "description": RaritySystem.get_tier_description(
                rarity, template.get("description", "")
            ),
            "type": template.get("type", "普通"),
            "rarity": rarity,
            "rarity_label": RaritySystem.get_label(rarity),
            "image_url": format_image_url(template.get("image_url", "")),
            "name_color": RaritySystem.get_name_color(rarity),
            "description_color": RaritySystem.get_description_color(rarity),
        }

    @staticmethod
    async def gen_sign_img(
        user_id: str,
        user_name: str,
        user_info: dict,
        reward: dict[str, int],
        avatar: str | None = None,
    ) -> bytes:
        """渲染签到卡片并写入本地缓存

        参数:
            user_id: 用户ID
            user_name: 用户名称
            user_info: 用户信息字典
            reward: 奖励信息字典
            avatar: 用户头像URL

        返回:
            bytes: 图片字节数据
        """
        image_path = SIGN_IN_IMAGE_PATH / f"{user_id}.png"

        favor_info = user_info["favorInfo"]
        next_level_exp = favor_info["nextLevelExperience"]
        progress_percentage = (
            100
            if next_level_exp <= 0
            else min(100, int(favor_info["experience"] / next_level_exp * 100))
        )

        first_sign_date = user_info.get("firstSignDate")
        last_sign_date = user_info.get("lastSignDate")

        first_sign_date_str = first_sign_time_str = first_time_description = ""
        if first_sign_date:
            first_sign_date_str = first_sign_date.strftime("%Y.%m.%d")
            first_sign_time_str = first_sign_date.strftime("%H:%M")
            first_time_description = TimeSeason.get_time_description(
                f"{first_sign_date.strftime('%m.%d')} {first_sign_time_str}"
            )

        last_sign_date_str = last_sign_time_str = ""
        if last_sign_date:
            last_sign_date_str = last_sign_date.strftime("%Y.%m.%d")
            last_sign_time_str = last_sign_date.strftime("%H:%M")

        meet_days = (
            max(1, (datetime.now() - first_sign_date).days) if first_sign_date else 0
        )

        chart_data = await UserSignLog.get_recent_six_months_data(user_id)
        dropped_item_info = (
            await SignInManage._build_item_info() if user_info["droppedItem"] else None
        )

        template_data = {
            "uid": user_info["uid"],
            "userName": user_name,
            "totalSignInDays": str(user_info["totalSignInDays"]),
            "consecutiveDays": str(user_info["signInInfo"]["consecutive_days"]),
            "rewardGold": str(reward["gold"]),
            "rewardFavor": str(reward["favorExperience"]),
            "baseFavor": str(reward.get("baseFavor", reward["favorExperience"])),
            "usedDoubleCard": user_info["usedDoubleCard"],
            "isDuplicate": user_info["isDuplicate"],
            "droppedItem": user_info["droppedItem"],
            "droppedItemInfo": dropped_item_info,
            "avatar": avatar,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "greeting": Greeting.get_greeting(),
            "firstSignDate": first_sign_date_str,
            "firstSignTime": first_sign_time_str,
            "firstTimeDescription": first_time_description,
            "lastSignDate": last_sign_date_str,
            "lastSignTime": last_sign_time_str,
            "meetDays": str(meet_days),
            "platform": user_info.get("platform", "unknown"),
            "chartMonths": json.dumps(chart_data["months"]),
            "chartCounts": json.dumps(chart_data["counts"]),
            "favorLevel": str(favor_info["level"]),
            "favorExperience": str(favor_info["experience"]),
            "nextLevelExperience": str(next_level_exp),
            "progressPercentage": str(progress_percentage),
        }

        image_bytes = await render(
            "pages/builtin/signIn",
            data=template_data,
            user_id=user_id,
            wait=2,
        )

        image_path.write_bytes(image_bytes)
        return image_bytes

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
    def build_markdown(image_url: str, width: str, height: str) -> str:
        """构建QQ Markdown内容

        参数:
            image_url: 图片URL
            width: 图片宽度
            height: 图片高度

        返回:
            str: Markdown格式字符串
        """
        return f"![签到卡片 #{width}px #{height}px]({image_url})\n---"

    @staticmethod
    def build_keyboard() -> list[list[Button]]:
        """构建QQ消息按钮

        返回:
            list[list[Button]]
        """
        return [
            [
                Button(
                    flag="enter",
                    label="商店",
                    clicked_label="商店",
                    id="btn_shop",
                    text="商店",
                    permission="all",
                ),
                Button(
                    flag="enter",
                    label="帮助",
                    clicked_label="帮助",
                    id="btn_help",
                    text="/帮助",
                    permission="all",
                ),
            ],
            [
                Button(
                    flag="enter",
                    label="签到",
                    clicked_label="签到",
                    id="",
                    text="/签到",
                    permission="all",
                ),
            ],
        ]
