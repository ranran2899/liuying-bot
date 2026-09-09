"""平台工具统一入口

聚合 utils/platform 包内各工具类的公开方法，提供 PlatformUtils 单一调用入口

"""

from collections.abc import Awaitable, Callable

from nonebot.adapters import Bot
from nonebot_plugin_alconna.uniseg import UniMessage

from liuying.utils.platform.avatar_utils import AvatarUtils
from liuying.utils.platform.bot import BotInfoUtils
from liuying.utils.platform.broadcast import broadcast_group
from liuying.utils.platform.group import GroupListUtils, GroupUtils
from liuying.utils.platform.group.member_list import MemberListUtils
from liuying.utils.platform.group.member_manage import MemberManageUtils
from liuying.utils.platform.helper import PlatformHelper
from liuying.utils.platform.user import UserUtils


class PlatformUtils(
    PlatformHelper,
    AvatarUtils,
    UserUtils,
    GroupListUtils,
    GroupUtils,
    MemberListUtils,
    BotInfoUtils,
    MemberManageUtils,
):
    """平台工具统一入口

    继承聚合各工具类的全部公开方法，并将包内模块级公开函数封装为类方法
    """

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
