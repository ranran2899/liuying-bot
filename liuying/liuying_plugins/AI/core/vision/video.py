"""视频理解

通过下载视频、抽取关键帧、调用多模态LLM分析视频内容。
当视频帧抽取不可用时，降级到基于音频与文字描述的分析。
"""

import asyncio
import base64
import io
from typing import Any

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

__all__ = ["VideoUnderstanding", "video_understanding"]


_VIDEO_MAX_BYTES = 32 * 1024 * 1024
"""视频最大字节数（32MB）"""


_VIDEO_DOWNLOAD_TIMEOUT = 30.0
"""视频下载超时（秒）"""


_VIDEO_FRAME_TIMEOUT = 20.0
"""视频帧抽取超时（秒）"""


_VIDEO_SAMPLE_FRAMES = 4
"""视频采样帧数"""


_VIDEO_FRAME_LONG_EDGE = 1280
"""视频帧拼图长边"""


_VIDEO_ANALYZE_PROMPT = (
    "请用中文简要描述这个视频的内容，包括主要画面、"
    "人物动作与场景变化，不超过80字。"
)
"""视频分析prompt"""


_FALLBACK_PROMPT = (
    "请基于以下视频描述信息，用中文简要总结视频内容，"
    "不超过60字。"
)
"""降级分析prompt"""


async def _download_video(url: str) -> bytes | None:
    """下载视频二进制数据

    参数:
        url: 视频URL

    返回:
        bytes | None: 视频二进制数据，失败返回None
    """
    try:
        data = await AsyncHttpx.get_content(url, timeout=_VIDEO_DOWNLOAD_TIMEOUT)
        if data and len(data) <= _VIDEO_MAX_BYTES:
            return data
        logger.warning(
            f"视频过大或为空: {len(data) if data else 0}",
            command="AI",
        )
        return None
    except Exception as e:
        logger.warning(
            f"视频下载失败: {url}: {e}",
            command="AI",
            e=e,
        )
        return None


def _extract_frames_sync(video_data: bytes) -> list[bytes]:
    """同步抽取视频关键帧并返回JPEG列表

    使用Pillow尝试解码（GIF/动态WebP等），失败返回空列表。

    参数:
        video_data: 视频二进制数据

    返回:
        list[bytes]: JPEG帧二进制列表
    """
    if Image is None:
        return []
    try:
        with Image.open(io.BytesIO(video_data)) as img:
            n_frames = getattr(img, "n_frames", 1)
            if n_frames <= 1:
                return []
            step = max(1, n_frames // _VIDEO_SAMPLE_FRAMES)
            indices = list(range(0, n_frames, step))[:_VIDEO_SAMPLE_FRAMES]
            frames: list[bytes] = []
            for idx in indices:
                img.seek(idx)
                frame = img.convert("RGB")
                scale = min(
                    1.0,
                    _VIDEO_FRAME_LONG_EDGE / max(frame.width, frame.height),
                )
                if scale < 1.0:
                    new_size = (
                        int(frame.width * scale),
                        int(frame.height * scale),
                    )
                    frame = frame.resize(new_size)
                buf = io.BytesIO()
                frame.save(buf, format="JPEG", quality=80)
                frames.append(buf.getvalue())
            return frames
    except Exception as e:
        logger.debug(
            f"视频帧抽取失败: {e}",
            command="AI",
            e=e,
        )
        return []


def _build_frames_message(frames: list[bytes], prompt: str) -> list[dict[str, Any]]:
    """构建多帧视觉消息

    参数:
        frames: JPEG帧二进制列表
        prompt: 分析提示

    返回:
        list[dict]: 多模态消息列表
    """
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for frame in frames:
        b64 = base64.b64encode(frame).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )
    return [{"role": "user", "content": content}]


class VideoUnderstanding:
    """视频理解器

    支持下载视频、抽取关键帧并通过多模态LLM分析。
    视频帧不可用时降级到基于文字描述与音频提示的分析。
    """

    def __init__(self) -> None:
        """初始化视频理解器"""

    def _is_enabled(self) -> bool:
        """检查视频理解是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("VIDEO_UNDERSTANDING_ENABLED", True))

    async def _analyze_frames(
        self, frames: list[bytes], duration_hint: int
    ) -> str:
        """通过关键帧分析视频

        参数:
            frames: JPEG帧二进制列表
            duration_hint: 视频时长提示（秒）

        返回:
            str: 视频内容描述
        """
        prompt = _VIDEO_ANALYZE_PROMPT
        if duration_hint > 0:
            prompt = f"{prompt}（视频时长约{duration_hint}秒）"
        messages = _build_frames_message(frames, prompt)
        return await llm_helper.chat_text(messages)

    async def _fallback_describe(
        self, url: str, duration_hint: int
    ) -> str:
        """降级分析：基于URL与时长提示用LLM推断

        参数:
            url: 视频URL
            duration_hint: 视频时长提示

        返回:
            str: 视频内容描述
        """
        hint = f"视频时长约{duration_hint}秒。" if duration_hint else ""
        messages = [
            {
                "role": "user",
                "content": (
                    f"{_FALLBACK_PROMPT}\n"
                    f"视频来源: {url}\n{hint}"
                ),
            }
        ]
        try:
            return await llm_helper.chat_text(messages)
        except Exception as e:
            logger.warning(
                f"视频降级分析失败: {e}",
                command="AI",
                e=e,
            )
            return "视频内容暂时无法理解。"

    async def understand(
        self, url: str, duration_hint: int = 0
    ) -> str:
        """理解视频内容

        优先下载并抽取关键帧分析；抽取失败时降级到文字描述。

        参数:
            url: 视频URL
            duration_hint: 视频时长提示（秒），0表示未知

        返回:
            str: 视频内容描述
        """
        if not self._is_enabled():
            return "视频理解未启用。"

        video_data = await _download_video(url)
        if not video_data:
            return await self._fallback_describe(url, duration_hint)

        try:
            frames = await asyncio.wait_for(
                asyncio.to_thread(_extract_frames_sync, video_data),
                timeout=_VIDEO_FRAME_TIMEOUT,
            )
        except TimeoutError:
            logger.warning("视频帧抽取超时", command="AI")
            frames = []
        except Exception as e:
            logger.warning(
                f"视频帧抽取异常: {e}",
                command="AI",
                e=e,
            )
            frames = []

        if not frames:
            return await self._fallback_describe(url, duration_hint)

        try:
            description = await self._analyze_frames(frames, duration_hint)
            return description.strip() or "视频内容暂时无法理解。"
        except Exception as e:
            logger.warning(
                f"视频帧分析失败，降级到描述: {e}",
                command="AI",
                e=e,
            )
            return await self._fallback_describe(url, duration_hint)


video_understanding = VideoUnderstanding()
"""视频理解器单例"""
