"""OpenAI 兼容 API 语音能力实现"""
from pathlib import Path
from typing import Any

from liuying.utils.LLM.open_ai.client import OpenAIClient
from liuying.utils.LLM.utils import APIError, ResponseParser


class OpenAIAudioCapability:
    """OpenAI 兼容 API 语音能力"""

    def __init__(self, client: OpenAIClient | None = None):
        """初始化语音能力

        Args:
            client: OpenAI 客户端实例
        """
        self._client = client or OpenAIClient()

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
        provider = self._client.get_random_provider()

        request_data: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed,
        }
        if options:
            request_data.update(options)

        response = await self._client.post_raw(
            provider, "audio/speech", request_data, timeout=120
        )

        if isinstance(response, dict) and response.get("error"):
            error_info = response["error"]
            msg = (
                error_info.get("message", "TTS失败")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            raise APIError(f"TTS失败: {msg}", "TTS_ERROR", "openai")

        return response if isinstance(response, bytes) else bytes(response)

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
        provider = self._client.get_random_provider()
        base_url = self._client.get_base_url(provider)
        headers = self._client.get_headers(provider)
        headers.pop("Content-Type", None)

        files = {"file": ("audio.wav", audio, "audio/wav")}
        data: dict[str, Any] = {"model": model}
        if language:
            data["language"] = language
        if options:
            data.update(options)

        response = await self._client.post_multipart(
            base_url,
            "audio/transcriptions",
            files,
            data,
            headers,
            timeout=120,
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return ResponseParser.parse_transcription_response(response)

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
        provider = self._client.get_random_provider()
        base_url = self._client.get_base_url(provider)
        headers = self._client.get_headers(provider)
        headers.pop("Content-Type", None)

        files = {"file": ("audio.wav", audio, "audio/wav")}
        data: dict[str, Any] = {"model": model}
        if options:
            data.update(options)

        response = await self._client.post_multipart(
            base_url,
            "audio/translations",
            files,
            data,
            headers,
            timeout=120,
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return ResponseParser.parse_transcription_response(response)

    async def speech_to_text_from_file(
        self,
        audio_file: str,
        model: str = "whisper-1",
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """从文件路径进行语音转文本

        Args:
            audio_file: 音频文件路径
            model: STT 模型名称
            language: 音频语言代码
            options: 额外选项

        Returns:
            转录文本
        """
        audio_bytes = Path(audio_file).read_bytes()
        return await self.speech_to_text(audio_bytes, model, language, options)

    async def translate_from_file(
        self,
        audio_file: str,
        model: str = "whisper-1",
        options: dict[str, Any] | None = None,
    ) -> str:
        """从文件路径进行音频翻译

        Args:
            audio_file: 音频文件路径
            model: 翻译模型名称
            options: 额外选项

        Returns:
            翻译后的文本
        """
        audio_bytes = Path(audio_file).read_bytes()
        return await self.translate(audio_bytes, model, options)

    async def get_available_voices(self) -> list[str]:
        """获取可用的声音类型列表

        Returns:
            声音类型列表
        """
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


__all__ = ["OpenAIAudioCapability"]
