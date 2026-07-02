"""LLM 能力协议定义 - 统一各 Provider 的能力接口"""
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from liuying.utils.LLM.web_search.models import SearchResponse


class Capability(StrEnum):
    """能力类型枚举"""

    CHAT = "chat"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    DOCUMENT = "document"
    TOKENIZER = "tokenizer"
    TOOLS = "tools"
    WEB_SEARCH = "web_search"

    @classmethod
    def values(cls) -> list[str]:
        """获取所有能力类型值列表

        Returns:
            能力类型字符串列表
        """
        return [m.value for m in cls]


@runtime_checkable
class ChatCapability(Protocol):
    """对话能力协议"""

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """执行对话

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Returns:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容
        """
        ...

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> Any:
        """流式对话

        Args:
            model: 模型名称
            messages: 对话消息列表
            options: 额外选项，支持标准键 reasoning_enabled 控制深度思考

        Yields:
            流式响应片段
        """
        ...


@runtime_checkable
class ImageCapability(Protocol):
    """图像生成能力协议"""

    async def generate(
        self,
        prompt: str,
        model: str = "dall-e-3",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """生成图像

        Args:
            prompt: 图像描述
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图像 URL 列表
        """
        ...

    async def edit(
        self,
        image: str,
        prompt: str,
        mask: str | None = None,
        model: str = "dall-e-2",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """编辑图像

        Args:
            image: 原始图像路径或 URL
            prompt: 编辑描述
            mask: 蒙版图像路径或 URL
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图像 URL 列表
        """
        ...

    async def create_variation(
        self,
        image: str,
        model: str = "dall-e-2",
        size: str = "1024x1024",
        n: int = 1,
        options: dict[str, Any] | None = None,
    ) -> list[str]:
        """创建图像变体

        Args:
            image: 原始图像路径或 URL
            model: 模型名称
            size: 图像尺寸
            n: 生成数量
            options: 额外选项

        Returns:
            图像 URL 列表
        """
        ...


@runtime_checkable
class AudioCapability(Protocol):
    """语音能力协议"""

    async def text_to_speech(
        self,
        text: str,
        model: str = "tts-1",
        voice: str = "alloy",
        speed: float = 1.0,
        options: dict[str, Any] | None = None,
    ) -> bytes:
        """文本转语音

        Args:
            text: 要转换的文本
            model: TTS 模型名称
            voice: 声音类型
            speed: 语速
            options: 额外选项

        Returns:
            音频字节数据
        """
        ...

    async def speech_to_text(
        self,
        audio: bytes,
        model: str = "whisper-1",
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """语音转文本

        Args:
            audio: 音频文件字节数据
            model: STT 模型名称
            language: 音频语言代码
            options: 额外选项

        Returns:
            转录文本
        """
        ...

    async def translate(
        self,
        audio: bytes,
        model: str = "whisper-1",
        options: dict[str, Any] | None = None,
    ) -> str:
        """音频翻译（翻译为英文）

        Args:
            audio: 音频文件字节数据
            model: 翻译模型名称
            options: 额外选项

        Returns:
            翻译后的文本
        """
        ...


@runtime_checkable
class VideoCapability(Protocol):
    """视频生成能力协议"""

    async def generate(
        self,
        prompt: str,
        model: str = "sora",
        duration: int | None = None,
        resolution: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """生成视频

        Args:
            prompt: 视频描述
            model: 视频模型名称
            duration: 视频时长（秒）
            resolution: 分辨率
            options: 额外选项

        Returns:
            包含视频信息的字典
        """
        ...

    async def get_status(self, video_id: str) -> dict[str, Any]:
        """获取视频生成状态

        Args:
            video_id: 视频任务 ID

        Returns:
            包含状态信息的字典
        """
        ...


@runtime_checkable
class EmbeddingCapability(Protocol):
    """文本嵌入能力协议"""

    async def create(
        self,
        input_text: str | list[str],
        model: str = "embedding-3",
        dimensions: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[list[float]]:
        """创建文本嵌入向量

        Args:
            input_text: 输入文本或文本列表
            model: 嵌入模型名称
            dimensions: 嵌入维度
            options: 额外选项

        Returns:
            嵌入向量列表
        """
        ...

    def get_dimension(self, model: str) -> int:
        """获取模型的默认嵌入维度

        Args:
            model: 模型名称

        Returns:
            嵌入维度数
        """
        ...


@runtime_checkable
class RerankCapability(Protocol):
    """文本重排序能力协议"""

    async def rerank(
        self,
        query: str,
        documents: list[str],
        model: str = "rerank",
        top_n: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """文本重排序

        Args:
            query: 查询文本
            documents: 待排序文档列表
            model: 重排序模型名称
            top_n: 返回前 N 个结果
            options: 额外选项

        Returns:
            重排序结果列表
        """
        ...


@runtime_checkable
class DocumentCapability(Protocol):
    """文档解析能力协议"""

    async def parse(
        self,
        file: bytes | str,
        file_name: str = "",
        model: str = "document-parser",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """解析文档

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名（URL 模式下可选）
            model: 解析模型名称
            options: 额外选项

        Returns:
            解析结果字典
        """
        ...

    async def extract_text(
        self,
        file: bytes | str,
        file_name: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        """提取文档纯文本

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名
            options: 额外选项

        Returns:
            提取的文本内容
        """
        ...


@runtime_checkable
class TokenizerCapability(Protocol):
    """分词能力协议"""

    async def count(
        self,
        text: str | list[dict[str, str]],
        model: str = "glm-4",
    ) -> int:
        """计算文本或消息列表的 token 数量

        Args:
            text: 输入文本或消息列表
            model: 模型名称

        Returns:
            token 数量
        """
        ...

    def estimate(self, text: str) -> int:
        """快速估算 token 数量（不调用 API）

        Args:
            text: 输入文本

        Returns:
            估算的 token 数量
        """
        ...


@runtime_checkable
class ToolsCapability(Protocol):
    """工具能力协议（网络搜索、网页阅读等）"""

    async def web_search(
        self,
        query: str,
        engine: str = "search_pro",
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """网络搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎类型
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索结果字典
        """
        ...

    async def web_read(
        self,
        url: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """网页阅读

        Args:
            url: 网页 URL
            options: 额外选项

        Returns:
            网页内容字典
        """
        ...


@runtime_checkable
class WebSearchCapability(Protocol):
    """统一网络搜索能力协议"""

    async def search(
        self,
        query: str,
        engine: str | None = None,
        count: int = 10,
        options: dict[str, Any] | None = None,
    ) -> "SearchResponse":
        """执行网络搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎名称，None 则使用默认
            count: 返回结果数量
            options: 额外选项

        Returns:
            搜索响应对象
        """
        ...


__all__ = [
    "AudioCapability",
    "Capability",
    "ChatCapability",
    "DocumentCapability",
    "EmbeddingCapability",
    "ImageCapability",
    "RerankCapability",
    "TokenizerCapability",
    "ToolsCapability",
    "VideoCapability",
    "WebSearchCapability",
]
