"""LLM工具包 - 统一的大语言模型调用接口

使用方式:
    from liuying.utils.LLM import llm_manager, Capability

    # 对话
    provider = llm_manager.get_provider("zhipu")
    chat = provider.get_capability(Capability.CHAT)
    result = await chat.chat("glm-4-flash", messages)

    # 查询模型配置
    cfg = llm_manager.get_model_config("glm-4-flash")

    # 获取可用模型
    models = llm_manager.get_available_model_names()
"""
from .capabilities import Capability
from .manager import llm_manager
from .tracker import token_tracker
from .utils import APIError, MultiAPIError

__all__ = [
    "APIError",
    "Capability",
    "MultiAPIError",
    "llm_manager",
    "token_tracker",
]
