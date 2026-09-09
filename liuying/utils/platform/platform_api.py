"""平台工具统一入口

聚合 utils/platform 包内各工具类的公开方法，提供 PlatformUtils 单一调用入口

"""

from collections.abc import Awaitable, Callable

from nonebot.adapters import Bot
from nonebot_plugin_alconna.uniseg import UniMessage

from liuying.utils.platform.avatar_utils import AvatarUtils
from liuying.utils.platform.bot import get_bot_info
from liuying.utils.platform.broadcast import broadcast_group
from liuying.utils.platform.group import GroupListUtils, GroupUtils
from liuying.utils.platform.group.member_list import MemberListUtils
from liuying.utils.platform.group.member_manage import ban_group_user, kick_group_user
from liuying.utils.platform.helper import PlatformHelper
from liuying.utils.platform.user import UserUtils


class PlatformUtils(
    PlatformHelper,
    AvatarUtils,
    UserUtils,
    GroupListUtils,
    GroupUtils,
    MemberListUtils,
):
    """平台工具统一入口

    继承聚合各工具类的全部公开方法，并将包内模块级公开函数封装为类方法
    """

    @classmethod
    async def get_bot_info(cls, bot: Bot) -> tuple[str, str]:
        """统一获取机器人昵称与头像url

        参数:
            bot: Bot

        返回:
            tuple[str, str]: (昵称, 头像url)
        """
        return await get_bot_info(bot)

    @classmethod
    async def broadcast_group(
        cls,
        message: str | UniMessage,
        bot: Bot | list[Bot] | None = None,
        bot_id: str | set[str] | None = None,
        ignore_group: list[str] | None = None,
        check_func: Callable[[Bot, str], Awaitable] | None = None,
        log_cmd: str | None = None,
        platform: str | None = None,
    ) -> int:
        """广播消息到所有群聊

        参数:
            message: 广播消息内容
            bot: 指定bot对象
            bot_id: 指定bot id
            ignore_group: 忽略群聊列表
            check_func: 发送前对群聊检测方法，判断是否发送
            log_cmd: 日志标记
            platform: 指定平台

        返回:
            int: 成功发送次数
        """
        return await broadcast_group(
            message=message,
            bot=bot,
            bot_id=bot_id,
            ignore_group=ignore_group,
            check_func=check_func,
            log_cmd=log_cmd,
            platform=platform,
        )

    @classmethod
    async def ban_group_user(
        cls, bot: Bot, user_id: str, group_id: str, duration: int
    ) -> None:
        """统一群禁言

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id
            duration: 禁言时长(分钟)
        """
        await ban_group_user(bot, user_id, group_id, duration)

    @classmethod
    async def kick_group_user(
        cls,
        bot: Bot,
        user_id: str,
        group_id: str,
        *,
        reject_add_request: bool = False,
    ) -> None:
        """统一踢出群成员

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id
            reject_add_request: 是否拒绝该用户再次入群
        """
        await kick_group_user(
            bot, user_id, group_id, reject_add_request=reject_add_request
        )
