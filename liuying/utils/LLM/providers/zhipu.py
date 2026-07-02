"""智谱 AI Provider，组合智谱特有的全部能力"""
from typing import Any

from liuying.utils.LLM.capabilities import Capability
from liuying.utils.LLM.configs import APIType, ProviderConfig
from liuying.utils.LLM.provider import BaseProvider, register_provider
from liuying.utils.LLM.zhi_pu.client import ZhipuClient

from .zhipu_capabilities.audio import ZhipuAudioCapability
from .zhipu_capabilities.chat import ZhipuChatCapability
from .zhipu_capabilities.document import ZhipuDocumentCapability
from .zhipu_capabilities.embedding import ZhipuEmbeddingCapability
from .zhipu_capabilities.image import ZhipuImageCapability
from .zhipu_capabilities.rerank import ZhipuRerankCapability
from .zhipu_capabilities.tokenizer import ZhipuTokenizerCapability
from .zhipu_capabilities.tools import ZhipuToolsCapability


@register_provider(APIType.ZHIPU)
class ZhipuProvider(BaseProvider):
    """智谱 AI Provider

    支持 api_type 为 zhipu 的配置，涵盖对话、图像、语音、嵌入、
    重排序、文档解析、分词及工具类能力。
    """

    api_type = APIType.ZHIPU
    default_capabilities = frozenset({
        Capability.CHAT,
        Capability.IMAGE,
        Capability.AUDIO,
        Capability.EMBEDDING,
        Capability.RERANK,
        Capability.DOCUMENT,
        Capability.TOKENIZER,
        Capability.TOOLS,
    })

    def __init__(self, config: ProviderConfig):
        """初始化智谱 Provider

        Args:
            config: 提供商配置
        """
        super().__init__(config)
        self._client = ZhipuClient()
        self._chat = ZhipuChatCapability(self._client)
        self._image = ZhipuImageCapability(self._client)
        self._audio = ZhipuAudioCapability(self._client)
        self._embedding = ZhipuEmbeddingCapability(self._client)
        self._rerank = ZhipuRerankCapability(self._client)
        self._document = ZhipuDocumentCapability(self._client)
        self._tokenizer = ZhipuTokenizerCapability(self._client)
        self._tools = ZhipuToolsCapability(self._client)

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
            Capability.EMBEDDING: self._embedding,
            Capability.RERANK: self._rerank,
            Capability.DOCUMENT: self._document,
            Capability.TOKENIZER: self._tokenizer,
            Capability.TOOLS: self._tools,
        }
        return mapping.get(capability) if capability in self.capabilities() else None


__all__ = ["ZhipuProvider"]
