"""输入状态显示

回复前显示"正在输入..."状态，
支持NapCat/LLOneBot的set_input_status API。
"""

from typing import Any

from liuying.utils.log import logger

from ..config import get_config


class InputStatusHandler:
    """输入状态处理器

    通过 set_input_status API 显示"正在输入..."状态，
    仅 NapCat / LLOneBot 系协议端支持。调用失败静默降级，
    不影响主流程。由 INPUT_STATUS_ENABLED 开关统一控制。
    """

    async def show_typing(
        self,
        duration: float,
        *,
        bot: Any = None,
        user_id: str = "",
    ) -> None:
        """显示正在输入状态

        持续 duration 秒，便于在打字延迟前先展示输入状态。
        bot 或 user_id 缺失时仅记录日志，不调用API。

        参数:
            duration: 持续时长（秒），用于日志记录
            bot: Bot对象，None时跳过API调用
            user_id: 目标用户ID
        """
        if not get_config("INPUT_STATUS_ENABLED", False):
            return
        if bot is None or not user_id:
            logger.debug(
                "显示输入状态跳过：缺少 bot 或 user_id",
                command="AI",
            )
            return
        try:
            await bot.call_api(
                "set_input_status",
                user_id=int(user_id),
                event_type=1,
            )
            logger.debug(
                f"已显示输入状态 user={user_id} "
                f"duration={duration:.2f}s",
                command="AI",
            )
        except Exception as e:
            logger.debug(
                f"设置输入状态失败: {e}", command="AI", e=e
            )


input_status_handler = InputStatusHandler()
"""输入状态处理器单例"""
