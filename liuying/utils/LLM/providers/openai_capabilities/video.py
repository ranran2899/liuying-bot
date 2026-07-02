"""OpenAI 兼容 API 视频生成能力实现"""
import asyncio
from typing import Any

from liuying.utils.LLM.open_ai.client import OpenAIClient
from liuying.utils.LLM.utils import APIError


class OpenAIVideoCapability:
    """OpenAI 兼容 API 视频生成能力"""

    def __init__(self, client: OpenAIClient | None = None):
        """初始化视频能力

        Args:
            client: OpenAI 客户端实例
        """
        self._client = client or OpenAIClient()

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
        provider = self._client.get_random_provider()

        request_data: dict[str, Any] = {"model": model, "prompt": prompt}
        if duration:
            request_data["duration"] = duration
        if resolution:
            request_data["resolution"] = resolution
        if options:
            request_data.update(options)

        response = await self._client.post(
            provider, "videos/generations", request_data, timeout=300
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return response

    async def get_status(self, video_id: str) -> dict[str, Any]:
        """获取视频生成状态

        Args:
            video_id: 视频任务 ID

        Returns:
            包含状态信息的字典
        """
        provider = self._client.get_random_provider()

        response = await self._client.get(
            provider, f"videos/{video_id}", timeout=60
        )

        if not isinstance(response, dict):
            raise APIError(
                f"响应格式错误: {response}", "INVALID_RESPONSE", "openai"
            )

        return response

    async def wait_for_completion(
        self,
        video_id: str,
        poll_interval: int = 10,
        max_wait: int = 600,
    ) -> dict[str, Any]:
        """等待视频生成完成

        Args:
            video_id: 视频任务 ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）

        Returns:
            包含视频信息的字典
        """
        waited = 0
        while waited < max_wait:
            status = await self.get_status(video_id)

            match status.get("status"):
                case "completed":
                    return status
                case "failed":
                    raise APIError(
                        f"视频生成失败: {status.get('error', '未知错误')}",
                        "VIDEO_FAILED",
                        "openai",
                    )

            await asyncio.sleep(poll_interval)
            waited += poll_interval

        raise APIError(
            f"视频生成超时: 等待超过 {max_wait} 秒",
            "VIDEO_TIMEOUT",
            "openai",
        )

    async def cancel(self, video_id: str) -> bool:
        """取消视频生成任务

        Args:
            video_id: 视频任务 ID

        Returns:
            是否取消成功
        """
        provider = self._client.get_random_provider()

        try:
            response = await self._client.post(
                provider, f"videos/{video_id}/cancel", timeout=30
            )
            return isinstance(response, dict) and response.get("status") == "cancelled"
        except Exception:
            return False


__all__ = ["OpenAIVideoCapability"]
