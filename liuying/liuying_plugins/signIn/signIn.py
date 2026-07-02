"""
签到插件核心
"""
import asyncio

from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Button, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.models._user.user_intro import UserIntroInfo
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.user import UserExp, UserGold, UserSign, UserUid

from .image import gen_sign_img
from .utils import SIGN_IN_IMAGE_PATH, SignInUtils

sign_in_cmd = on_alconna(
    Alconna("签到"),
    aliases={"打卡", "/签到"},
    priority=52,
    block=True
)

reset_sign_cmd = on_alconna(
    Alconna("重置签到"),
    permission=SUPERUSER,
    priority=51,
    block=True
)


async def build_user_data(
    user_id: str,
    user_name: str,
    is_duplicate: bool = False,
    total_days_offset: int = 0,
    platform: str = "unknown"
) -> dict:
    """构建用户数据

    参数:
        user_id: 用户ID
        user_name: 用户名称
        is_duplicate: 是否重复签到
        total_days_offset: 总签到天数偏移量
        platform: 平台信息

    返回:
        dict: 用户数据字典
    """
    (
        favor_exp_info,
        user_uid,
        total_days,
        consecutive_days,
        first_sign_date,
        last_sign_date,
    ) = await asyncio.gather(
        UserExp.get_both_progress(user_id),
        UserUid.get_user_uid(user_id),
        UserSign.get_total_days(user_id),
        UserSign.get_consecutive_days(user_id),
        UserSign.get_first_sign_in_date(user_id),
        UserSign.get_last_sign_in_date(user_id),
    )

    favor_info = favor_exp_info["favor"]
    return {
        "uid": user_uid,
        "userName": user_name,
        "favorInfo": {
            "level": favor_info["favor"],
            "experience": favor_info["current_exp"],
            "nextLevelExperience": favor_info["next_exp"],
        },
        "totalSignInDays": total_days + total_days_offset,
        "signInInfo": {"consecutive_days": consecutive_days},
        "firstSignDate": first_sign_date,
        "lastSignDate": last_sign_date,
        "platform": platform,
        "isDuplicate": is_duplicate,
        "usedDoubleCard": False,
        "droppedItem": False,
    }


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


def build_keyboard() -> list[list[Button]]:
    """构建QQ消息按钮

    返回:
        list[list[Button]]
    """
    return [
        [
            Button(
                flag="enter",
                label="运势",
                clicked_label="运势",
                id="btn_fortune",
                text="/运势",
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
                id="btn_signin",
                text="/签到",
                permission="all",
            ),
        ],
    ]


async def send_sign_in_message(
    session: Uninfo,
    user_id: str,
    image_bytes: bytes
) -> None:
    """发送签到消息

    参数:
        session: 会话信息
        user_id: 用户ID
        image_bytes: 图片字节数据
    """
    if PlatformUtils.is_qbot(session) and not PlatformUtils.is_qq_guild(session):
        url, width, height = await SignInUtils.upload_image(user_id, image_bytes)
        if url:
            markdown_content = build_markdown(url, width, height)
            keyboard = build_keyboard()
            await MessageUtils.build_markdown_message(
                markdown_content, keyboard
            ).finish()
        logger.warning("图片上传失败，回退到图片发送")

    await MessageUtils.build_message(image_bytes).finish()


@sign_in_cmd.handle()
async def handle_sign_in(session: Uninfo) -> None:
    """处理签到请求"""
    user_id = session.user.id
    user_name = session.user.name
    platform = session.adapter
    avatar = session.user.avatar
    logger.info("用户签到请求", command="签到", session=session)

    await asyncio.gather(
        UserIntroInfo.set_nickname(user_id, user_name),
        UserIntroInfo.set_avatar(user_id, avatar or ""),
        UserIntroInfo.set_platform(user_id, platform),
    )

    image_path = SIGN_IN_IMAGE_PATH / f"{user_id}.png"

    if await UserSign.check_user_sign_status(user_id) == 1:
        if image_path.exists():
            image_bytes = image_path.read_bytes()
            await send_sign_in_message(session, user_id, image_bytes)
            return

        user_data = await build_user_data(
            user_id, user_name, is_duplicate=True, platform=platform
        )
        image_bytes = await gen_sign_img(
            user_id, user_name, user_data, {"gold": 0, "favorExperience": 0}, avatar
        )
        await send_sign_in_message(session, user_id, image_bytes)
        return

    await process_normal_sign_in(session, user_id, user_name, platform, avatar)


async def process_normal_sign_in(
    session: Uninfo,
    user_id: str,
    user_name: str,
    platform: str,
    avatar: str | None
) -> None:
    """处理正常签到流程

    参数:
        session: 会话信息
        user_id: 用户ID
        user_name: 用户名称
        platform: 平台信息
        avatar: 用户头像URL
    """
    await UserSign.sign(user_id)

    consecutive_days = await UserSign.get_consecutive_days(user_id)
    reward = SignInUtils.calc_reward(consecutive_days)

    used_double_card, dropped_item = await asyncio.gather(
        SignInUtils.use_double_card(user_id),
        SignInUtils.drop_item(user_id)
    )

    if used_double_card:
        reward["favorExperience"] *= 2

    await asyncio.gather(
        UserExp.add_favor_exp(user_id, reward["favorExperience"]),
        UserGold.add_user_gold(user_id, reward["gold"])
    )

    user_data = await build_user_data(
        user_id,
        user_name,
        is_duplicate=False,
        total_days_offset=1,
        platform=platform,
    )
    user_data["usedDoubleCard"] = used_double_card
    user_data["droppedItem"] = dropped_item

    image_bytes = await gen_sign_img(
        user_id, user_name, user_data, reward, avatar
    )
    await send_sign_in_message(session, user_id, image_bytes)


@reset_sign_cmd.handle()
async def handle_reset_sign(session: Uninfo) -> None:
    """处理超级用户重置所有用户签到状态请求"""
    reset_count = await UserSign.reset_all_signed_in_users()
    logger.info(
        f"超级用户 {session.user.id} 手动重置了所有用户的签到状态，"
        f"共重置 {reset_count} 个用户"
    )
    await MessageUtils.build_message(
        f"已成功重置所有用户的签到状态，共重置 {reset_count} 个用户"
    ).finish()
