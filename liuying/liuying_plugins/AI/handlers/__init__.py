"""命令处理器

各命令域的业务逻辑类，matcher 在插件 __init__.py 统一注册。
"""

from .admin_commands import AdminCommands
from .chat_commands import ChatCommands
from .chat_helpers import ChatMatchersHelper
from .memory_commands import MemoryCommands
from .persona_commands import PersonaCommands
from .poke_notice import PokeNotice
from .task_commands import TaskCommands
from .tts_commands import TtsCommands

__all__ = [
    "AdminCommands",
    "ChatCommands",
    "ChatMatchersHelper",
    "MemoryCommands",
    "PersonaCommands",
    "PokeNotice",
    "TaskCommands",
    "TtsCommands",
]
