"""
用户信息插件
"""

import asyncio
from datetime import datetime

from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.path_config import TEMP_PATH
from liuying.liuying_plugins.user_info.utils import QQMsgBuilder
from liuying.models._user import UserLevel
from liuying.ui.services import render
from liuying.utils.bed_layout import BedLayout
from liuying.utils.bot.version import BotVersionInfo
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.user import UserGold, UserUid
from liuying.utils.user.curr import UserCurrUtils

user_info_cmd = on_alconna(
    Alconna("我的信息"),
    aliases={"/我的信息"},
    priority=500,
    block=True,
)

user_token_cmd = on_alconna(
    Alconna("我的令牌"),
    aliases={"/我的令牌"},
    priority=500,
    block=True,
)


@user_info_cmd.handle()
async def handle_user_info(session: Uninfo) -> None:
    """处理用户信息请求，展示用户的名称、ID、UUID及注册时间信息"""
    user_id = session.user.id
    user_name = session.user.name
    user_avatar = session.user.avatar
    group_id = session.group.id if session.group else None
    bot_id = session.self_id

    logger.info("用户查看个人信息", command="我的信息", session=session)

    user_uid = await UserUid.get_user_uid(user_id)

    (
        registration_time,
        user_token,
        bot_version,
        user_gold,
        user_level,
        user_copper,
        user_silver,
        user_diamond,
        user_xingqiong,
        user_yuanshi,
        user_tianrew,
    ) = await asyncio.gather(
        UserUid.get_user_register_time(user_id),
        UserUid.get_uid_token(user_uid),
        BotVersionInfo.get_version(),
        UserGold.get_user_gold(user_id),
        UserLevel.get_level(user_id, bot_id, group_id),
        UserCurrUtils.get_user_copper(user_id),
        UserCurrUtils.get_user_silver(user_id),
        UserCurrUtils.get_user_diamond(user_id),
        UserCurrUtils.get_user_xingqiong(user_id),
        UserCurrUtils.get_user_yuanshi(user_id),
        UserCurrUtils.get_user_tianrew(user_id),
    )

    reg_time_str = (
        registration_time.strftime("%Y-%m-%d %H:%M:%S")
        if registration_time
        else "暂时不知道"
    )
    user_info = {
        "user_id": user_id,
        "nickname": user_name,
        "uuid": user_uid,
        "registration_time": reg_time_str,
        "user_token": user_token or "无",
        "avatar_path": user_avatar,
        "bot_version": bot_version,
        "user_gold": user_gold,
        "user_level": user_level,
        "user_copper": user_copper,
        "user_silver": user_silver,
        "user_diamond": user_diamond,
        "user_xingqiong": user_xingqiong,
        "user_yuanshi": user_yuanshi,
        "user_tianrew": user_tianrew,
    }

    if PlatformUtils.is_qbot(session):
        await _send_qq_markdown_user_info(user_info)
    else:
        await _send_image_user_info(user_id, user_info)


@user_token_cmd.handle()
async def handle_user_token(session: Uninfo) -> None:
    """处理用户令牌请求，直接发送当前用户的UID令牌"""
    user_id = session.user.id

    logger.info("用户查看个人令牌", command="我的令牌", session=session)

    user_uid = await UserUid.get_user_uid(user_id)
    user_token = await UserUid.get_uid_token(user_uid)

    if not user_token:
        await MessageUtils.build_message(
            "获取令牌失败，请稍后再试"
        ).finish(reply_to=True)

    msg = f"你的UID: {user_uid}\n你的令牌: {user_token}"
    await MessageUtils.build_message(msg).finish(reply_to=True)


async def _render_image(
    user_id: str,
    user_info: dict,
    viewport: dict[str, int] | None = None,
) -> bytes:
    """渲染用户信息图片

    参数:
        user_id: 用户ID
        user_info: 用户信息字典
        viewport: 视口配置

    返回:
        bytes: 图片字节数据
    """
    template_data = {
        "user_id": user_info["user_id"],
        "nickname": user_info["nickname"],
        "uuid": user_info["uuid"],
        "registration_time": user_info["registration_time"],
        "user_token": user_info["user_token"],
        "avatar_path": user_info.get("avatar_path", ""),
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bot_version": user_info["bot_version"],
        "user_gold": user_info["user_gold"],
        "user_level": user_info["user_level"],
        "user_copper": user_info["user_copper"],
        "user_silver": user_info["user_silver"],
        "user_diamond": user_info["user_diamond"],
        "user_xingqiong": user_info["user_xingqiong"],
        "user_yuanshi": user_info["user_yuanshi"],
        "user_tianrew": user_info["user_tianrew"],
    }

    render_kwargs = {"wait": 2}
    if viewport:
        render_kwargs["viewport"] = viewport

    return await render(
        "pages/builtin/user_info",
        template_data,
        user_id=user_id,
        **render_kwargs,
    )


async def _generate_image(user_info: dict) -> tuple[str, str, str]:
    """生成用户信息图片并上传到云存储

    参数:
        user_info: 用户信息字典

    返回:
        tuple[str, str, str]: 图片URL、宽度、高度
    """
    user_id = user_info["user_id"]
    image_bytes = await _render_image(user_id, user_info)

    temp_dir = TEMP_PATH / "user_info"
    temp_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    image_path = temp_dir / f"user_info_{user_id}_{timestamp}.png"
    image_path.write_bytes(image_bytes)

    filename = f"user_info/{user_id}_{timestamp}.png"
    result = await BedLayout.save_image_bytes(
        file_data=image_bytes,
        filename=filename,
        extension=".png",
        content_type="image/png",
        delete_after_minutes=1,
    )

    image_url = result.get("url", "")
    if not image_url:
        logger.warning("上传图片到云存储失败")
        return "", "", ""

    logger.info(f"上传图片到云存储成功，URL: {image_url}")
    return image_url, result.get("width", ""), result.get("height", "")


async def _send_qq_markdown_user_info(user_info: dict) -> None:
    """发送QQ Markdown格式用户信息

    参数:
        user_info: 用户信息字典
    """
    image_url, width, height = await _generate_image(user_info)

    if not image_url:
        logger.warning("图片上传失败，回退到图片发送")
        await _send_image_user_info(user_info["user_id"], user_info)
        return

    markdown_content = QQMsgBuilder._markdown(image_url, width, height)
    keyboard = QQMsgBuilder._keyboard()

    await MessageUtils.build_markdown_message(markdown_content, keyboard).finish()


async def _send_image_user_info(user_id: str, user_info: dict) -> None:
    """发送图片格式用户信息

    参数:
        user_id: 用户ID
        user_info: 用户信息字典
    """
    image_bytes = await _render_image(
        user_id, user_info
    )

    temp_dir = TEMP_PATH / "user_info"
    temp_dir.mkdir(parents=True, exist_ok=True)

    image_path = temp_dir / f"user_info_{user_id}.png"
    image_path.write_bytes(image_bytes)

    await MessageUtils.build_message(image_path).finish()
