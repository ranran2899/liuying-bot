"""
机器人本体更新插件
检查当前机器人版本与仓库最新版本，支持一键更新机器人本体
"""

import os
import platform
import sys

import aiofiles
from nonebot.adapters import Bot
from nonebot.params import ArgStr
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .config import LOG_COMMAND, RESTART_MARK, UPDATE_CONFIRM
from .data_source import UpdateManager

__plugin_meta__ = PluginMetadata(
    name="机器人更新",
    description="检查并更新机器人本体到仓库最新版本",
    usage="""
    超级用户指令
        检查更新
        立即更新
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPERUSER,
        superuser_help="""
        格式:
        检查更新
        立即更新
        """,
    ).to_dict(),
)

_check_matcher = on_alconna(
    Alconna("检查更新"),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

_update_matcher = on_alconna(
    Alconna("立即更新"),
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@_check_matcher.handle()
async def _(session: Uninfo):
    """检查当前机器人版本与仓库最新版本"""
    await MessageUtils.build_message("正在检查更新...").send()
    try:
        version_info = await UpdateManager.check_update()
    except Exception as e:
        logger.error("检查更新失败", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message("检查更新失败，请稍后再试...").finish()
    if version_info.has_update:
        message = (
            f"当前版本: {version_info.local_version}\n"
            f"最新版本: {version_info.remote_version}\n"
            "有新版本可以更新啦\n发送 立即更新 来更新机器人"
        )
    else:
        message = (
            f"当前版本: {version_info.local_version}\n"
            f"最新版本: {version_info.remote_version}\n"
            "已经是最新版本啦"
        )
    logger.info(
        f"检查更新 本地: {version_info.local_version} "
        f"远程: {version_info.remote_version}",
        LOG_COMMAND,
        session=session,
    )
    await MessageUtils.build_message(message).send()


@_update_matcher.handle()
async def _(session: Uninfo):
    """处理立即更新命令，检查版本后进入确认流程"""
    await MessageUtils.build_message("正在检查更新...").send()
    try:
        version_info = await UpdateManager.check_update()
    except Exception as e:
        logger.error("检查更新失败", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message(
            "检查更新失败，无法获取版本信息..."
        ).finish()
    if not version_info.has_update:
        await MessageUtils.build_message("已经是最新版本了...").finish()
    logger.info(
        f"发现新版本 {version_info.remote_version}，等待用户确认更新",
        LOG_COMMAND,
        session=session,
    )
    await MessageUtils.build_message(
        f"发现新版本!\n当前版本: {version_info.local_version}\n"
        f"最新版本: {version_info.remote_version}"
    ).send()


@_update_matcher.got(
    "flag",
    prompt=(
        "是否更新机器人？\n确定请回复[是|好|确定]\n"
        "（更新失败咱们将失去联系，请谨慎！）"
    ),
)
async def _(
    bot: Bot,
    session: Uninfo,
    flag: str = ArgStr("flag"),
):
    """处理更新确认，确认后执行更新并重启"""
    if flag.lower() not in UPDATE_CONFIRM:
        await MessageUtils.build_message("已取消操作...").send(reply_to=True)
        return
    await MessageUtils.build_message("开始更新机器人..请稍等...").send(reply_to=True)
    try:
        file_count = await UpdateManager.update_bot()
    except Exception as e:
        logger.error("更新机器人本体失败", LOG_COMMAND, session=session, e=e)
        await MessageUtils.build_message(
            f"更新机器人失败 e: {e}\n请稍后重试或手动更新"
        ).finish()
    logger.info(
        f"机器人本体更新完成，共更新 {file_count} 个文件",
        LOG_COMMAND,
        session=session,
    )
    await MessageUtils.build_message("文件更新完成，正在同步依赖...").send()
    if not await UpdateManager.update_dependencies():
        await MessageUtils.build_message(
            "依赖同步失败，已取消自动重启...\n"
            "请手动执行 [uv sync] 并重启机器人，以免重启失败"
        ).finish()
    await _do_restart(bot, session)


async def _do_restart(bot: Bot, session: Uninfo) -> None:
    """写入重启标记并重启机器人进程"""
    await MessageUtils.build_message(
        "更新完成，开始重启机器人..请稍等..."
    ).send(reply_to=True)
    async with aiofiles.open(RESTART_MARK, "w", encoding="utf8") as f:
        await f.write(f"{bot.self_id} {session.scene.id}")
    logger.info("更新完成，开始重启机器人...", LOG_COMMAND, session=session)
    _exec_restart()


def _exec_restart() -> None:
    """执行机器人重启操作"""
    match platform.system().lower():
        case "windows":
            os.execl(sys.executable, sys.executable, *sys.argv)
        case _:
            os.system("./restart.sh")
