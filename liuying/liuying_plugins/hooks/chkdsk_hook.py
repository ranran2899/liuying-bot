from collections import defaultdict
import time
from typing import ClassVar

from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import At
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.ban_console import BanConsole
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .auth.utils import get_group_channel_ids


class BanCheckLimiter:
    """恶意命令触发检测"""

    _instances: ClassVar[dict[tuple[float, int], "BanCheckLimiter"]] = {}

    def __new__(cls, check_time: float, count: int):
        key = (check_time, count)
        if key not in cls._instances:
            instance = super().__new__(cls)
            instance.mint = defaultdict(int)
            instance.mtime = defaultdict(float)
            instance.default_check_time = check_time
            instance.default_count = count
            cls._instances[key] = instance
        return cls._instances[key]

    def add(self, key: str | float):
        """添加计数"""
        if self.mint[key] == 1:
            self.mtime[key] = time.time()
        self.mint[key] += 1

    def check(self, key: str | float) -> bool:
        """检查是否触发限制"""
        current_time = time.time()
        if current_time - self.mtime[key] > self.default_check_time:
            self.mtime[key] = current_time
            self.mint[key] = 0
            return False
        if self.mint[key] >= self.default_count:
            self.mtime[key] = current_time
            self.mint[key] = 0
            return True
        return False


@run_preprocessor
async def _(
    matcher: Matcher, bot: Bot, session: Uninfo, state: T_State, event: Event
):
    """恶意触发命令检测"""
    module = None
    if plugin := matcher.plugin:
        module = plugin.name
        if not (metadata := plugin.metadata):
            return
        extra = metadata.extra
        if extra.get("plugin_type") in {
            PluginType.HIDDEN,
            PluginType.DEPENDANT,
            PluginType.ADMIN,
            PluginType.SUPERUSER,
        }:
            return
    if matcher.type == "notice":
        return

    user_id = session.user.id
    ids = get_group_channel_ids(session)

    malicious_check_time = Config.get_config("hook", "MALICIOUS_CHECK_TIME")
    malicious_ban_count = Config.get_config("hook", "MALICIOUS_BAN_COUNT")
    malicious_ban_time = Config.get_config("hook", "MALICIOUS_BAN_TIME")

    if not all((malicious_check_time, malicious_ban_count, malicious_ban_time)):
        for name, val in [
            ("MALICIOUS_CHECK_TIME", malicious_check_time),
            ("MALICIOUS_BAN_COUNT", malicious_ban_count),
            ("MALICIOUS_BAN_TIME", malicious_ban_time),
        ]:
            if not val:
                logger.warning(
                    f"模块: [hook], 配置项: [{name}] 为空或小于0", "chkdsk_hook"
                )
        return

    if user_id and module:
        _blmt = BanCheckLimiter(malicious_check_time, malicious_ban_count)
        check_key = f"{user_id}__{module}"
        if _blmt.check(check_key):
            await BanConsole.ban(
                user_id,
                ids.group_id,
                9,
                "恶意触发命令检测",
                malicious_ban_time * 60,
                bot.self_id,
            )
            logger.info(
                f"触发了恶意触发检测: {matcher.plugin_name}",
                "HOOK",
                session=session,
            )
            ban_time_display = malicious_ban_time
            await MessageUtils.build_message(
                [
                    At(flag="user", target=user_id),
                    f"检测到恶意触发命令，您将被封禁 {ban_time_display} 分钟",
                ]
            ).send()
            raise IgnoredException("检测到恶意触发命令")
        _blmt.add(check_key)
