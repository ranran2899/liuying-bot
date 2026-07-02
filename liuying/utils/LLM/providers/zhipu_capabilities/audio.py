"""智谱 AI 语音能力实现"""
from typing import Any

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.LLM.utils import APIError, ResponseParser
from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuAudioCapability:
    """智谱 AI 语音能力（TTS/STT）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化语音能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def text_to_speech(
        self,
        text: str,
        model: str = "tts-1",
        voice: str = "alloy",
        speed: float = 1.0,
        options: dict[str, Any] | None = None,
    ) -> bytes:
        """文本转语音（TTS）

        Args:
            text: 要转换的文本
            model: TTS 模型名称
            voice: 声音类型
            speed: 语速
            options: 额外选项

        Returns:
            音频字节数据
        """
        request_data: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed,
        }

        if options:
            request_data.update(options)

        url = f"{self._client.base_url}/audio/speech"
        headers = self._client.get_headers()

        response = await AsyncHttpx.post(
            url=url, json=request_data, headers=headers, timeout=120
        )

        if isinstance(response, dict) and response.get("error"):
            error_info = response["error"]
            msg = (
                error_info.get("message", "TTS失败")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            raise APIError(f"TTS失败: {msg}", "TTS_ERROR", "zhipu")

        return response if isinstance(response, bytes) else bytes(response)

    async def speech_to_text(
        self,
        audio: bytes,
        model: str = "whisper-1",
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """语音转文本（STT/Whisper）

        Args:
            audio: 音频文件字节数据
            model: 模型名称
            language: 音频语言代码
            options: 额外选项

        Returns:
            转录文本
        """
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data: dict[str, Any] = {
            "model": model,
            "response_format": "json",
        }

        if language:
            data["language"] = language
        if options:
            data.update(options)

        response = await self._client.post_multipart(
            "audio/transcriptions", files, data, timeout=120
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
            model: 模型名称
            options: 额外选项

        Returns:
            翻译后的文本
        """
        files = {"file": ("audio.wav", audio, "audio/wav")}
        data: dict[str, Any] = {"model": model}

        if options:
            data.update(options)

        response = await self._client.post_multipart(
            "audio/translations", files, data, timeout=120
        )
        return ResponseParser.parse_transcription_response(response)

    async def speech_to_text_from_url(
        self,
        audio_url: str,
        model: str = "whisper-1",
        language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """通过 URL 进行语音转文本

        Args:
            audio_url: 音频文件 URL
            model: 模型名称
            language: 语言代码
            options: 额外选项

        Returns:
            转录文本
        """
        request_data: dict[str, Any] = {"model": model, "url": audio_url}

        if language:
            request_data["language"] = language
        if options:
            request_data.update(options)

        response = await self._client.post(
            "audio/transcriptions", request_data, timeout=120
        )
        return ResponseParser.parse_transcription_response(response)


__all__ = ["ZhipuAudioCapability"]
