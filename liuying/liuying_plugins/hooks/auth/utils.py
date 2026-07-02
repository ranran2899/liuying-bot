import contextlib
from dataclasses import dataclass

from nonebot.adapters import Event
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.extra.limit import FreqLimiter
from liuying.models.plugin_info import PluginInfo
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .config import LOGGER_COMMAND

base_config = Config.get("hook")


@dataclass(slots=True, frozen=True)
class GroupChannelIds:
    """群组和频道ID数据类

    使用 dataclass 和 slots 优化内存使用
    frozen=True 确保不可变性，提高线程安全
    """
    group_id: str | None = None
    channel_id: str | None = None


def get_group_channel_ids(session: Uninfo) -> GroupChannelIds:
    """从session中提取群组和频道ID

    参数:
        session: Uninfo会话信息

    返回:
        GroupChannelIds: 包含group_id和channel_id的数据对象
    """
    if not session.group:
        return GroupChannelIds()
    if session.group.parent:
        return GroupChannelIds(
            group_id=session.group.parent.id,
            channel_id=session.group.id
        )
    return GroupChannelIds(group_id=session.group.id)


def is_poke(event: Event) -> bool:
    """判断是否为poke类型

    参数:
        event: Event

    返回:
        bool: 是否为poke类型
    """
    with contextlib.suppress(ImportError):
        from nonebot.adapters.onebot.v11 import PokeNotifyEvent
        return isinstance(event, PokeNotifyEvent)
    return False


async def send_message(
    session: Uninfo, message: list | str, check_tag: str | None = None
):
    """发送消息

    参数:
        session: Uninfo
        message: 消息
        check_tag: cd flag
    """
    try:
        match check_tag:
            case None:
                await MessageUtils.build_message(message).send(reply_to=True)
            case _ if freq._flmt.check(check_tag):
                freq._flmt.start_cd(check_tag)
                await MessageUtils.build_message(message).send(reply_to=True)
    except Exception as e:
        logger.error("发送消息失败", LOGGER_COMMAND, session=session, e=e)


class FreqUtils:
    """频率限制工具类"""

    __slots__ = ("_flmt", "_flmt_c", "_flmt_g", "_flmt_s")

    def __init__(self):
        check_notice_info_cd = Config.get_config("hook", "CHECK_NOTICE_INFO_CD")
        if check_notice_info_cd is None or check_notice_info_cd < 0:
            raise ValueError("模块: [hook], 配置项: [CHECK_NOTICE_INFO_CD] 为空或小于0")
        self._flmt = FreqLimiter(check_notice_info_cd)
        self._flmt_g = FreqLimiter(check_notice_info_cd)
        self._flmt_s = FreqLimiter(check_notice_info_cd)
        self._flmt_c = FreqLimiter(check_notice_info_cd)

    def is_send_limit_message(
        self, plugin: PluginInfo, sid: str, is_poke: bool
    ) -> bool:
        """是否发送提示消息

        参数:
            plugin: PluginInfo
            sid: 检测键
            is_poke: 是否是戳一戳

        返回:
            bool: 是否发送提示消息
        """
        if is_poke:
            return False
        if not base_config.get("IS_SEND_TIP_MESSAGE"):
            return False
        if plugin.plugin_type == PluginType.DEPENDANT:
            return False
        return not plugin.ignore_prompt and self._flmt_s.check(sid)


freq = FreqUtils()
