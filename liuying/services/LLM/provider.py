"""LLM Provider 抽象基类与注册机制"""
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from .capabilities import (
    AudioCapability,
    Capability,
    ChatCapability,
    DocumentCapability,
    EmbeddingCapability,
    ImageCapability,
    RerankCapability,
    TokenizerCapability,
    ToolsCapability,
    VideoCapability,
    WebSearchCapability,
)
from .configs import ProviderConfig
from .utils import APIError

_PROVIDER_REGISTRY: dict[str, type["BaseProvider"]] = {}


def register_provider(api_type: str) -> Any:
    """Provider 注册装饰器

    Args:
        api_type: API 类型标识

    Returns:
        装饰器函数
    """

    def wrapper(cls: type["BaseProvider"]) -> type["BaseProvider"]:
        """将 Provider 类注册到注册表

        Args:
            cls: Provider 类

        Returns:
            注册后的 Provider 类
        """
        _PROVIDER_REGISTRY[api_type] = cls
        return cls

    return wrapper


def get_provider_class(api_type: str) -> type["BaseProvider"] | None:
    """根据 API 类型获取已注册的 Provider 类

    Args:
        api_type: API 类型标识

    Returns:
        Provider 类，未注册则返回 None
    """
    return _PROVIDER_REGISTRY.get(api_type)


def get_registered_api_types() -> list[str]:
    """获取所有已注册的 API 类型

    Returns:
        API 类型字符串列表
    """
    return list(_PROVIDER_REGISTRY.keys())


class BaseProvider(ABC):
    """LLM Provider 抽象基类

    所有 LLM Provider 必须继承此类，并通过 @register_provider 注册。
    """

    api_type: ClassVar[str] = ""
    default_capabilities: ClassVar[frozenset[Capability]] = frozenset()

    def __init__(self, config: ProviderConfig):
        """初始化 Provider

        Args:
            config: 提供商配置
        """
        self._config = config

    @property
    def name(self) -> str:
        """获取 Provider 名称

        Returns:
            Provider 名称
        """
        return self._config.name

    @property
    def config(self) -> ProviderConfig:
        """获取 Provider 配置

        Returns:
            提供商配置对象
        """
        return self._config

    @abstractmethod
    def capabilities(self) -> set[Capability]:
        """获取当前 Provider 支持的所有能力

        Returns:
            能力类型集合
        """
        ...

    @abstractmethod
    def get_capability(self, capability: Capability) -> Any | None:
        """获取指定能力的实现实例

        Args:
            capability: 能力类型

        Returns:
            能力实现实例，不支持则返回 None
        """
        ...

    def has_capability(self, capability: Capability) -> bool:
        """判断是否支持指定能力

        Args:
            capability: 能力类型

        Returns:
            是否支持
        """
        return capability in self.capabilities()

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """便捷方法：执行对话

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Returns:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容

        Raises:
            APIError: 当前 Provider 不支持对话能力
        """
        cap = self.get_capability(Capability.CHAT)
        if not isinstance(cap, ChatCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持对话能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.chat(model, messages, options)

    async def image_generate(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """便捷方法：生成图像

        Args:
            prompt: 图像描述
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图像 URL 列表
        """
        cap = self.get_capability(Capability.IMAGE)
        if not isinstance(cap, ImageCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持图像生成能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.generate(prompt, model, size, n, options)

    async def audio_tts(
        self,
        text: str,
        model: str = "tts-1",
        voice: str = "alloy",
        speed: float = 1.0,
        options: dict[str, Any] | None = None,
    ) -> bytes:
        """便捷方法：文本转语音

        Args:
            text: 要转换的文本
            model: TTS 模型名称
            voice: 声音类型
            speed: 语速
            options: 额外选项

        Returns:
            音频字节数据
        """
        cap = self.get_capability(Capability.AUDIO)
        if not isinstance(cap, AudioCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持语音能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.text_to_speech(text, model, voice, speed, options)

    async def audio_stt(
        self,
        audio: bytes,
        model: str = "whisper-1",
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """便捷方法：语音转文本

        Args:
            audio: 音频字节数据
            model: STT 模型名称
            language: 音频语言代码
            options: 额外选项

        Returns:
            转录文本
        """
        cap = self.get_capability(Capability.AUDIO)
        if not isinstance(cap, AudioCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持语音能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.speech_to_text(audio, model, language, options)

    async def video_generate(
        self,
        prompt: str,
        model: str = "sora",
        duration: int | None = None,
        resolution: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """便捷方法：生成视频

        Args:
            prompt: 视频描述
            model: 视频模型名称
            duration: 视频时长（秒）
            resolution: 分辨率
            options: 额外选项

        Returns:
            包含视频信息的字典
        """
        cap = self.get_capability(Capability.VIDEO)
        if not isinstance(cap, VideoCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持视频生成能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.generate(prompt, model, duration, resolution, options)

    async def embedding_create(
        self,
        input_text: str | list[str],
        model: str = "embedding-3",
        dimensions: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        """便捷方法：创建文本嵌入

        Args:
            input_text: 输入文本或文本列表
            model: 嵌入模型名称
            dimensions: 嵌入维度
            options: 额外选项

        Returns:
            嵌入向量列表
        """
        cap = self.get_capability(Capability.EMBEDDING)
        if not isinstance(cap, EmbeddingCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持文本嵌入能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.create(input_text, model, dimensions, options)

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank",
        top_n: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """便捷方法：文本重排序

        Args:
            query: 查询文本
            documents: 待排序文档列表
            model: 重排序模型名称
            top_n: 返回前 N 个结果
            options: 额外选项

        Returns:
            重排序结果列表
        """
        cap = self.get_capability(Capability.RERANK)
        if not isinstance(cap, RerankCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持重排序能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.rerank(query, documents, model, top_n, options)

    async def document_parse(
        self,
        file: bytes | str,
        file_name: str = "",
        model: str = "document-parser",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """便捷方法：解析文档

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名
            model: 解析模型名称
            options: 额外选项

        Returns:
            解析结果字典
        """
        cap = self.get_capability(Capability.DOCUMENT)
        if not isinstance(cap, DocumentCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持文档解析能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.parse(file, file_name, model, options)

    async def tokenizer_count(
        self,
        text: str | list[dict[str, str]],
        model: str = "glm-4",
    ) -> int:
        """便捷方法：计算 token 数量

        Args:
            text: 输入文本或消息列表
            model: 模型名称

        Returns:
            token 数量
        """
        cap = self.get_capability(Capability.TOKENIZER)
        if not isinstance(cap, TokenizerCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持分词能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.count(text, model)

    async def tools_web_search(
        self,
        query: str,
        engine: str = "search_pro",
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """便捷方法：工具级网络搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎类型
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索结果字典
        """
        cap = self.get_capability(Capability.TOOLS)
        if not isinstance(cap, ToolsCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持工具能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.web_search(query, engine, count, options)

    async def web_search(
        self,
        query: str,
        engine: str | None = None,
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """便捷方法：统一网络搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎名称，None 则使用默认
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索响应对象
        """
        cap = self.get_capability(Capability.WEB_SEARCH)
        if not isinstance(cap, WebSearchCapability):
            raise APIError(
                f"Provider '{self.name}' 不支持网络搜索能力",
                "CAPABILITY_NOT_SUPPORTED",
                self.name,
            )
        return await cap.search(query, engine, count, options)


__all__ = [
    "BaseProvider",
    "get_provider_class",
    "get_registered_api_types",
    "register_provider",
]
