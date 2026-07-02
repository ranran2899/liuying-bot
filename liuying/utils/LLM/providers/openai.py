"""OpenAI 兼容 API Provider"""
from typing import Any

from liuying.utils.LLM.capabilities import Capability
from liuying.utils.LLM.configs import APIType, ProviderConfig
from liuying.utils.LLM.open_ai.client import OpenAIClient
from liuying.utils.LLM.provider import BaseProvider, register_provider

from .openai_capabilities.audio import OpenAIAudioCapability
from .openai_capabilities.chat import OpenAIChatCapability
from .openai_capabilities.image import OpenAIImageCapability
from .openai_capabilities.video import OpenAIVideoCapability


@register_provider(APIType.OPENAI)
@register_provider(APIType.ARK)
@register_provider(APIType.OPENROUTER)
class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 API Provider

    支持 api_type 为 openai / ark / openrouter 的配置。
    """

    api_type = APIType.OPENAI
    default_capabilities = frozenset({
        Capability.CHAT,
        Capability.IMAGE,
        Capability.AUDIO,
        Capability.VIDEO,
    })

    def __init__(self, config: ProviderConfig):
        """初始化 OpenAI Provider

        Args:
            config: 提供商配置
        """
        super().__init__(config)
        self._client = OpenAIClient()
        self._chat = OpenAIChatCapability(self._client)
        self._image = OpenAIImageCapability(self._client)
        self._audio = OpenAIAudioCapability(self._client)
        self._video = OpenAIVideoCapability(self._client)

    def capabilities(self) -> set[Capability]:
        """获取支持的能力集合

        Returns:
            能力类型集合
        """
        declared = self._config.capabilities
        if declared:
            return {
                Capability(c) for c in declared if c in Capability.values()
            }
        return set(self.default_capabilities)

    def get_capability(self, capability: Capability) -> Any | None:
        """获取指定能力的实现

        Args:
            capability: 能力类型

        Returns:
            能力实现实例，不支持则返回 None
        """
        mapping = {
            Capability.CHAT: self._chat,
            Capability.IMAGE: self._image,
            Capability.AUDIO: self._audio,
            Capability.VIDEO: self._video,
        }
        return mapping.get(capability) if capability in self.capabilities() else None


__all__ = ["OpenAIProvider"]
