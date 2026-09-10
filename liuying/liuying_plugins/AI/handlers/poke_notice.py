"""拍一拍响应逻辑

监听群内戳一戳事件，按概率戳回去。
仅响应戳bot自己的事件，避免bot乱戳别人。
"""

import random

from nonebot.adapters import Bot, Event

from liuying.utils.log import logger

from ..config import get_config
from ..core.runtime import ProtocolHelper

__all__ = [
    "PokeNotice",
]


class PokeNotice:
    """拍一拍响应逻辑

    matcher 在插件 __init__ 统一注册，此处仅承接业务逻辑。
    """

    @staticmethod
    async def handle_poke(bot: Bot, event: Event) -> None:
        """处理戳一戳事件

        当戳的对象是bot自己时，按 POKE 配置决定是否戳回去。

        参数:
            bot: Bot对象
            event: 事件对象
        """
        # 廉价过滤前置：绝大多数notice事件不是戳一戳，
        # 避免白读一次配置
        notice_type = str(
            getattr(event, "notice_type", "") or ""
        ).strip()
        sub_type = str(
            getattr(event, "sub_type", "") or ""
        ).strip()
        if notice_type != "notify" or sub_type != "poke":
            return

        poke_cfg = get_config("POKE", {}) or {}
        if not poke_cfg.get("enabled", True):
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

        prob = poke_cfg.get("probability", 0.3)
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
