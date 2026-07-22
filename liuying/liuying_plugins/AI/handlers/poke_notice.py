"""拍一拍响应

监听群内戳一戳事件，按概率戳回去。
仅响应戳bot自己的事件，避免bot乱戳别人。
"""

import random

from nonebot import on_notice
from nonebot.adapters import Bot, Event

from liuying.utils.log import logger

from ..config import get_config
from ..core.runtime import ProtocolHelper

__all__ = ["setup_poke_notice"]


def setup_poke_notice() -> None:
    """注册拍一拍响应notice监听

    监听群内戳一戳（poke）事件，当戳的对象是bot自己时，
    按 POKE_BACK_ENABLED + POKE_BACK_PROBABILITY 决定是否戳回去。
    """
    notice_matcher = on_notice(priority=60, block=False)

    @notice_matcher.handle()
    async def _handle_poke(bot: Bot, event: Event) -> None:
        """处理戳一戳事件

        参数:
            bot: Bot对象
            event: 事件对象
        """
        if not get_config("POKE", {}).get("enabled", True):
            return

        notice_type = str(
            getattr(event, "notice_type", "") or ""
        ).strip()
        sub_type = str(
            getattr(event, "sub_type", "") or ""
        ).strip()
        if notice_type != "notify" or sub_type != "poke":
            return

        self_id = str(getattr(bot, "self_id", "") or "")
        target_id = str(
            getattr(event, "target_id", "") or ""
        )
        if not target_id or target_id != self_id:
            return

        user_id = str(getattr(event, "user_id", "") or "")
        if not user_id or user_id == self_id:
            return

        group_id = str(
            getattr(event, "group_id", "") or ""
        )

        prob = get_config("POKE", {}).get("probability", 0.3)
        if random.random() >= prob:
            return

        ok = await ProtocolHelper.poke(
            bot,
            user_id=user_id,
            group_id=group_id,
        )
        if ok:
            logger.debug(
                f"拍一拍响应: 戳回 {user_id} "
                f"group={group_id}",
                command="AI",
                group_id=group_id or None,
            )
