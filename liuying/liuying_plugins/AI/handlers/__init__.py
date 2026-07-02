"""命令处理器

包含对话触发matcher、AI管理命令、TTS命令等。
"""

from .chat_matchers import setup_matchers

__all__ = ["setup_matchers"]
