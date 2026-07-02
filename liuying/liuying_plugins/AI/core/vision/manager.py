"""视觉理解

图片/GIF/视频理解：多模态LLM调用 + GIF关键帧采样 +
视觉能力探测。
"""

import asyncio
import base64
from dataclasses import dataclass
import io
from typing import Any

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[assignment]

from liuying.services.cache import CacheDict

from ..llm import llm_helper as _default_llm_helper
from .capabilities import vision_router

__all__ = [
    "GifSummary",
    "ImageSummary",
    "build_vision_messages",
    "summarize_gif",
    "summarize_image",
]


_VISION_PROMPT = "请用中文简要描述这张图片的内容，不超过50字。"
"""视觉理解prompt"""


_GIF_VISION_PROMPT = "请用中文简要描述这个GIF动图的内容，不超过50字。"
"""GIF视觉理解prompt"""


_GIF_MAX_BYTES = 8 * 1024 * 1024
"""GIF最大字节数"""


_GIF_MAX_FRAMES = 180
"""GIF最大解码帧数"""


_GIF_SAMPLE_FRAMES = 8
"""GIF采样帧数"""


_GIF_CONTACT_SHEET_LONG_EDGE = 1600
"""GIF拼图长边"""


_GIF_TIMEOUT = 12.0
"""GIF处理超时（秒）"""


_GIF_CACHE_MAX = 256
"""GIF摘要缓存最大数量"""


_gif_cache = CacheDict(
    "AI_VISION_GIF", expire=3600, max_size=_GIF_CACHE_MAX
)
"""GIF摘要LRU缓存（最多256条，1小时TTL）"""

@dataclass(slots=True)
class ImageSummary:
    """图片摘要结果

    Attributes:
        description: 描述文本
        success: 是否成功
        error: 错误信息
    """

    description: str = ""
    success: bool = False
    error: str = ""


@dataclass(slots=True)
class GifSummary:
    """GIF摘要结果

    Attributes:
        summary: 摘要文本
        frame_count: 总帧数
        sampled_frames: 采样帧数
        duration_ms: 持续时间（毫秒）
        success: 是否成功
        error: 错误信息
    """

    summary: str = ""
    frame_count: int = 0
    sampled_frames: int = 0
    duration_ms: int = 0
    success: bool = False
    error: str = ""


def _to_data_url(data: bytes, mime: str = "image/jpeg") -> str:
    """转base64 data URL

    参数:
        data: 二进制数据
        mime: MIME类型

    返回:
        str: data URL
    """
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _select_frame_indices(
    total: int,
    sample: int,
) -> list[int]:
    """等距采样帧索引（含末帧）

    参数:
        total: 总帧数
        sample: 采样数

    返回:
        list[int]: 帧索引列表
    """
    if total <= 0 or sample <= 0:
        return []
    if total <= sample:
        return list(range(total))

    if sample == 1:
        return [total - 1]

    last = total - 1
    indices = sorted(
        {round(i * last / (sample - 1)) for i in range(sample)}
    )
    return indices


async def summarize_image(
    image_data: bytes,
    mime: str = "image/jpeg",
    llm_helper: Any = None,
    *,
    prompt: str | None = None,
    use_vision_router: bool = True,
) -> ImageSummary:
    """用多模态LLM描述图片

    优先通过 vision_router 路由到支持视觉的 provider，
    路由失败时降级到默认 llm_helper.chat。

    参数:
        image_data: 图片二进制数据
        mime: MIME类型
        llm_helper: LLM助手，None时延迟导入
        prompt: 自定义prompt
        use_vision_router: 是否启用视觉能力路由

    返回:
        ImageSummary: 图片摘要
    """
    if not image_data:
        return ImageSummary(error="空图片数据")

    if llm_helper is None:
        llm_helper = _default_llm_helper

    use_prompt = prompt or _VISION_PROMPT
    data_url = _to_data_url(image_data, mime)

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": use_prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        }
    ]

    route_provider: str | None = None
    route_model: str | None = None
    fallback_note = ""

    if use_vision_router:
        try:
            route = await vision_router.route_vision_request()
            if route.success:
                route_provider = route.provider or None
                route_model = route.model or None
            elif route.fallback_used:
                fallback_note = route.fallback_reason or ""
        except Exception as e:
            fallback_note = f"视觉路由异常: {e}"

    try:
        description = await llm_helper.chat_text(
            messages,
            model=route_model,
            provider_name=route_provider,
        )
        return ImageSummary(
            description=description.strip(),
            success=True,
            error=fallback_note,
        )
    except Exception as e:
        return ImageSummary(error=str(e))


def _build_gif_contact_sheet_sync(
    gif_data: bytes,
) -> tuple[bytes, int, int, int]:
    """构建GIF拼图（同步，CPU密集型）

    参数:
        gif_data: GIF二进制数据

    返回:
        tuple[bytes, int, int, int]: (jpeg数据, 总帧数, 采样帧数, 持续ms)
    """
    if Image is None:
        raise ImportError("需要Pillow库支持GIF处理")

    with Image.open(io.BytesIO(gif_data)) as img:
        n_frames = getattr(img, "n_frames", 1)
        duration_ms = 0
        for i in range(n_frames):
            img.seek(i)
            duration_ms += getattr(img, "duration", 0) or 100

        sample_indices = _select_frame_indices(
            n_frames, min(_GIF_SAMPLE_FRAMES, n_frames)
        )
        if not sample_indices:
            sample_indices = [0]

        frames: list[Image.Image] = []
        for idx in sample_indices:
            img.seek(idx)
            frame = img.convert("RGB")
            frames.append(frame.copy())

    if not frames:
        raise ValueError("无法解码GIF帧")

    max_w = max(f.width for f in frames)
    max_h = max(f.height for f in frames)
    scale = min(
        1.0,
        _GIF_CONTACT_SHEET_LONG_EDGE / max(max_w * len(frames), max_h),
    )
    thumb_w = max(1, int(max_w * scale))
    thumb_h = max(1, int(max_h * scale))

    contact = Image.new(
        "RGB",
        (thumb_w * len(frames), thumb_h),
        (255, 255, 255),
    )
    for i, frame in enumerate(frames):
        thumb = frame.resize((thumb_w, thumb_h))
        contact.paste(thumb, (i * thumb_w, 0))

    buf = io.BytesIO()
    contact.save(buf, format="JPEG", quality=85)
    return (
        buf.getvalue(),
        n_frames,
        len(sample_indices),
        duration_ms,
    )


async def summarize_gif(
    gif_data: bytes,
    llm_helper: Any = None,
    *,
    cache_key: str = "",
) -> GifSummary:
    """用多模态LLM描述GIF

    先采样关键帧拼成JPEG，再调用视觉LLM描述。

    参数:
        gif_data: GIF二进制数据
        llm_helper: LLM助手
        cache_key: 缓存键

    返回:
        GifSummary: GIF摘要
    """
    if not gif_data:
        return GifSummary(error="空GIF数据")

    if len(gif_data) > _GIF_MAX_BYTES:
        return GifSummary(error="GIF过大")

    if cache_key:
        cached = _gif_cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        # GIF 解码为 CPU 密集型操作，通过 to_thread 避免阻塞事件循环
        result = await asyncio.wait_for(
            asyncio.to_thread(_build_gif_contact_sheet_sync, gif_data),
            timeout=_GIF_TIMEOUT,
        )
    except TimeoutError:
        return GifSummary(error="GIF处理超时")
    except Exception as e:
        return GifSummary(error=f"GIF处理失败: {e}")

    jpeg_data, frame_count, sampled, duration_ms = result

    image_summary = await summarize_image(
        jpeg_data,
        mime="image/jpeg",
        llm_helper=llm_helper,
        prompt=_GIF_VISION_PROMPT,
    )

    summary = GifSummary(
        summary=image_summary.description,
        frame_count=frame_count,
        sampled_frames=sampled,
        duration_ms=duration_ms,
        success=image_summary.success,
        error=image_summary.error,
    )

    if cache_key and summary.success:
        _gif_cache.set(cache_key, summary)

    return summary


def build_vision_messages(
    text: str,
    image_data: bytes,
    mime: str = "image/jpeg",
) -> list[dict[str, Any]]:
    """构建视觉理解消息列表

    参数:
        text: 文本提示
        image_data: 图片数据
        mime: MIME类型

    返回:
        list[dict]: 消息列表
    """
    data_url = _to_data_url(image_data, mime)
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                },
            ],
        }
    ]
