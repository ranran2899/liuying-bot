"""
签到图片生成模块
"""
from datetime import datetime
import json

from liuying.liuying_plugins.economy.shop.template import TemplateRepository
from liuying.models._user.user_sign_log import UserSignLog
from liuying.ui.services import render
from liuying.utils.calendar import Greeting, TimeSeason
from liuying.utils.utils import format_image_url

from .utils import SIGN_IN_IMAGE_PATH


async def gen_sign_img(
    user_id: str,
    user_name: str,
    user_info: dict,
    reward: dict[str, int],
    avatar: str | None = None,
) -> bytes:
    """生成签到图片

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
    progress_percentage = 100 if next_level_exp <= 0 else min(
        100, int(favor_info["experience"] / next_level_exp * 100)
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

    dropped_item_info = None
    if user_info["droppedItem"]:
        template = await TemplateRepository.find_template("double_favor_card")
        if template:
            dropped_item_info = {
                "id": template.get("id", ""),
                "name": template.get("name", ""),
                "description": template.get("description", ""),
                "type": template.get("type", "普通"),
                "image_url": format_image_url(template.get("image_url", "")),
                "name_color": template.get("name_color", ""),
                "description_color": template.get("description_color", ""),
            }

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
