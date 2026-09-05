"""NoneBot 签到插件"""

# from nonebot import get_driver
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.models._user.user_sign import UserSignInfo
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.manager import PriorityLifecycle

from .data_source import SIGN_IN_IMAGE_PATH, SignInManage

__plugin_meta__ = PluginMetadata(
    name="签到",
    description="每日签到，证明你在这里",
    usage="""
    每日签到
    指令:
        签到
    * 签到获得随机基础金币奖励(1-配置值)
    * 连续签到每天额外获得1金币，上限为配置值
    * 签到获得随机基础好感度奖励(1-配置值)
    * 连续签到每天额外获得1好感度，上限为配置值
    * 基于自然日(24:00)重置签到状态，跨午夜签到判定为连续签到
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.5",
        menu_type="功能",
        is_show=True,
        commands=[Command(command="签到")],
        configs=[
            RegisterConfig(
                key="SIGN_GOLD",
                value=50,
                help="签到基础金币奖励上限，实际奖励为1到此值的随机整数",
                default_value=50,
                type=int,
            ),
            RegisterConfig(
                key="MAX_SIGN_GOLD",
                value=30,
                help="连续签到奖励金币上限，每连续签到1天额外获得1金币，最高不超过此值",
                default_value=30,
                type=int,
            ),
            RegisterConfig(
                key="ITEM_DROP_RATE",
                value=50,
                help="签到好感度双倍加持卡Ⅰ掉落概率",
                default_value=50,
                type=float,
            ),
            RegisterConfig(
                key="BASE_FAVOR_EXPERIENCE",
                value=30,
                help="签到基础好感度经验奖励上限，实际奖励为1到此值的随机整数",
                default_value=30,
                type=int,
            ),
            RegisterConfig(
                key="CONSECUTIVE_FAVOR_BONUS",
                value=3,
                help="连续签到好感度奖励上限，每连续签到1天额外获得1好感度，最高不超过此值",
                default_value=3,
                type=int,
            ),
            RegisterConfig(
                key="MAX_FAVOR",
                value=9,
                help="最大好感度等级",
                default_value=9,
                type=int,
            ),
            RegisterConfig(
                key="FAVOR_EXPERIENCE_RATE",
                value=1.5,
                help="好感度等级经验增长速率",
                default_value=1.5,
                type=float,
            ),
            RegisterConfig(
                key="MAX_LEVEL",
                value=100,
                help="最大等级",
                default_value=100,
                type=int,
            ),
            RegisterConfig(
                key="LEVEL_EXPERIENCE_RATE",
                value=1.2,
                help="等级等级经验增长速率",
                default_value=1.2,
                type=float,
            ),
        ],
    ).to_dict(),
)






sign_in_cmd = on_alconna(
    Alconna("签到"),
    aliases={"打卡", "/签到"},
    priority=52,
    block=True,
)

reset_sign_cmd = on_alconna(
    Alconna("重置签到"),
    permission=SUPERUSER,
    priority=51,
    block=True,
)


async def _send_sign_card(session: Uninfo, user_id: str, image_bytes: bytes) -> None:
    """发送签到卡片，QQ官方非频道场景优先走Markdown卡片，失败回退图片发送"""
    if PlatformUtils.is_qbot(session) and not PlatformUtils.is_qq_guild(session):
        url, width, height = await SignInManage.upload_image(user_id, image_bytes)
        if url:
            await MessageUtils.build_markdown_message(
                SignInManage.build_markdown(url, width, height),
                SignInManage.build_keyboard(),
            ).finish()
        logger.warning("图片上传失败，回退到图片发送")

    await MessageUtils.build_message(image_bytes).finish()


@sign_in_cmd.handle()
async def handle_sign_in(session: Uninfo) -> None:
    """处理签到请求"""
    logger.info("用户签到请求", command="签到", session=session)
    record = await UserSignInfo.safe_get_or_none(user_id=session.user.id)
    if record and record.is_signed_in == 1:
        image_bytes = await SignInManage.duplicate_card(session, record)
    else:
        image_bytes = await SignInManage.sign_in(session)
    await _send_sign_card(session, session.user.id, image_bytes)


@reset_sign_cmd.handle()
async def handle_reset_sign(session: Uninfo) -> None:
    """处理超级用户重置所有用户签到状态请求"""
    reset_count = await UserSignInfo.reset_all_signed_in_users()
    logger.info(
        f"超级用户 {session.user.id} 手动重置了所有用户的签到状态，"
        f"共重置 {reset_count} 个用户"
    )
    await MessageUtils.build_message(
        f"已成功重置所有用户的签到状态，共重置 {reset_count} 个用户"
    ).finish()


@PriorityLifecycle.on_startup(priority=5)
async def _init_signin_items() -> None:
    """插件启动时注册签到道具"""
    await SignInManage.init_items()



@task_manager.cron("reset_daily_sign", hour=0, minute=0, second=0)
async def _reset_daily_sign() -> None:
    """每天凌晨0点重置所有用户的签到状态"""
    reset_count = await UserSignInfo.reset_all_signed_in_users()
    logger.info(f"每日签到状态重置完成，共重置 {reset_count} 个用户")


@task_manager.cron("clear_sign_in_images", hour=23, minute=59, second=0)
async def _clear_sign_in_images() -> None:
    """每天23:59清空当日签到图片缓存"""
    deleted_count = 0
    for file_path in SIGN_IN_IMAGE_PATH.glob("*.png"):
        try:
            file_path.unlink()
            deleted_count += 1
        except OSError as e:
            logger.error(f"清空签到图片失败: {e}")
    logger.info(f"已清空签到图片，共删除 {deleted_count} 个文件")



