"""统一机器人信息的平台实现

各平台机器人信息接口差异较大，统一按适配器名分发

"""

from nonebot.adapters import Bot

from liuying.configs.config import BotConfig
from liuying.utils.platform.avatar_utils import AvatarUtils
from liuying.utils.platform.helper import PlatformHelper


async def get_bot_info(bot: Bot) -> tuple[str, str]:
    """统一获取机器人昵称与头像url，按适配器名分发到各平台实现

    参数:
        bot: Bot

    返回:
        tuple[str, str]: (昵称, 头像url)
    """
    bot_id = bot.self_id
    match bot.adapter.get_name():
        case "OneBot V11" | "OneBot V12":
            return await _get_onebot_info(bot)
        case "QQ":
            return await _get_qq_official_info(bot)
        case _:
            return bot_id, ""


async def _get_onebot_info(bot: Bot) -> tuple[str, str]:
    """OneBot V11/V12 机器人信息，昵称取登录号信息，头像按QQ号拼接"""
    bot_id = bot.self_id
    if bot.adapter.get_name() == "OneBot V11":
        login_info = await bot.get_login_info()
        nickname = login_info.get("nickname") or bot_id
    else:
        self_info = await bot.get_self_info()
        nickname = (
            self_info.get("user_displayname") or self_info.get("user_name") or bot_id
        )
    avatar_url = ""
    if PlatformHelper.get_platform(bot) == "qq":
        avatar_url = (
            AvatarUtils.get_user_avatar_url(
                bot_id, "qq", BotConfig.get_qbot_uid(bot_id)
            )
            or ""
        )
    return nickname, avatar_url


async def _get_qq_official_info(bot: Bot) -> tuple[str, str]:
    """QQ官方机器人信息，直接调用 bot.me()"""
    bot_id = bot.self_id
    user = await bot.me()
    return user.username or bot_id, user.avatar or ""
