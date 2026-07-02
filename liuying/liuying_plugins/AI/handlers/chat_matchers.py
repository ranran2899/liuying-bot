"""对话matcher注册

注册AI对话触发、人格切换、画像查看、记忆查看、清空、TTS等命令。
统一通过 on_alconna + nonebot_plugin_uninfo 实现多平台支持。
并注册 group_ban notice 监听以感知群禁言状态。

各命令的具体处理逻辑按域拆分至 commands 子包，
本模块仅负责统一调度与群禁言notice注册。
"""

from liuying.utils.log import logger

from .chat_helpers import ChatMatchersHelper
from .commands import (
    setup_chat_commands,
    setup_memory_commands,
    setup_persona_commands,
    setup_tts_commands,
)

__all__ = ["setup_matchers"]


def setup_matchers() -> None:
    """注册所有AI matcher

    在插件启动时调用，依次注册：
    - 聊天对话matcher（私聊/@bot）
    - 人格切换与画像查看命令
    - 记忆查看与清空命令
    - TTS合成命令
    - group_ban notice 监听
    """
    setup_chat_commands()
    setup_persona_commands()
    setup_memory_commands()
    setup_tts_commands()
    ChatMatchersHelper._register_group_ban_notice()

    logger.info(
        "AI matcher注册完成",
        command="AI",
    )
