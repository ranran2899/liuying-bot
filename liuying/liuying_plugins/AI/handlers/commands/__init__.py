"""AI命令处理器集合

re-export 各命令域的 setup 函数，供 chat_matchers 统一调用。
"""

from .chat_commands import setup_chat_commands
from .memory_commands import setup_memory_commands
from .persona_commands import setup_persona_commands
from .tts_commands import setup_tts_commands

__all__ = [
    "setup_chat_commands",
    "setup_memory_commands",
    "setup_persona_commands",
    "setup_tts_commands",
]
