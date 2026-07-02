"""
机器人重启插件
当用户在聊天中通过"@机器人 重启"格式的指令触发时，机器人应执行重启操作
"""

import os
from pathlib import Path
import platform
import sys

import aiofiles
import nonebot
from nonebot.adapters import Bot
from nonebot.params import ArgStr
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import NICKNAME
from liuying.configs.utils.models import PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="机器人重启",
    description="通过@机器人 重启命令来重启机器人",
    usage="""
    超级用户指令
        重启
        立即重启
    """.strip(),
    extra=PluginExtraData(
        admin_level=10,
        plugin_type=PluginType.SUPERUSER,
        superuser_help="""
        格式:
        @机器人 重启
        立即重启
        """,
    ).to_dict(),
)

_restart_matcher = on_alconna(
    Alconna("重启"),
    permission=SUPERUSER,
    rule=to_me(),
    priority=2,
    block=True,
)

_immediate_restart_matcher = on_alconna(
    Alconna("立即重启"),
    permission=SUPERUSER,
    # rule=to_me(),
    priority=2,
    block=True,
)

driver = nonebot.get_driver()
RESTART_MARK = Path() / "is_restart"
RESTART_CONFIRM = {"true", "是", "好", "确定", "确定是"}


@_restart_matcher.got(
    "flag",
    prompt=f"确定是否重启{NICKNAME}？\n确定请回复[是|好|确定]\n（重启失败咱们将失去联系，请谨慎！）",
)
async def _(
    bot: Bot,
    session: Uninfo,
    flag: str = ArgStr("flag"),
):
    """处理重启命令"""
    if flag.lower() not in RESTART_CONFIRM:
        await MessageUtils.build_message("已取消操作...").send(reply_to=True)
        return

    await _do_restart(bot, session)


@_immediate_restart_matcher.handle()
async def _(
    bot: Bot,
    session: Uninfo,
):
    """处理立即重启命令，跳过确认直接重启"""
    await _do_restart(bot, session)


async def _do_restart(bot: Bot, session: Uninfo) -> None:
    """执行机器人重启操作：写入标记文件并重启进程"""
    await MessageUtils.build_message("开始重启机器人..请稍等...").send(reply_to=True)
    async with aiofiles.open(RESTART_MARK, "w", encoding="utf8") as f:
        await f.write(f"{bot.self_id} {session.scene.id}")
    logger.info("开始重启机器人...", "重启", session=session)
    _restart_bot()


def _restart_bot() -> None:
    """执行机器人重启操作"""
    match platform.system().lower():
        case "windows":
            os.execl(sys.executable, sys.executable, *sys.argv)
        case _:
            os.system("./restart.sh")


@driver.on_bot_connect
async def _(bot: Bot):
    """机器人连接时检查是否为重启后的启动"""
    if not RESTART_MARK.exists():
        return

    try:
        async with aiofiles.open(RESTART_MARK, encoding="utf8") as f:
            content = await f.read()
        bot_id, _ = content.split()
    except (FileNotFoundError, ValueError):
        return

    if bot.self_id != bot_id:
        return

    logger.info(f"机器人 {bot_id} 已成功重启")
    try:
        RESTART_MARK.unlink()
    except OSError:
        pass
