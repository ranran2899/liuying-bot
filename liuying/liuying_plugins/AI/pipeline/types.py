"""回复处理数据类型

定义 ReplyContext 和 ReplyResult 数据结构。
"""

from dataclasses import dataclass, field
from typing import Any

from nonebot_plugin_alconna import Image


@dataclass(slots=True)
class ReplyContext:
    """回复上下文

    Attributes:
        user_id: 用户ID
        group_id: 群组ID，None为私聊
        platform: 平台名
        bot_id: 机器人ID
        text: 用户消息文本
        is_at_bot: 是否@机器人
        is_private: 是否私聊
        image_data: 图片二进制数据，None表示无图片
        image_mime: 图片MIME类型
        persona_name: 当前bot人格名（用于人设间数据隔离）
    """

    user_id: str
    group_id: str | None
    platform: str | None
    bot_id: str | None
    text: str
    is_at_bot: bool = False
    is_private: bool = False
    image_data: bytes | None = None
    image_mime: str = "image/jpeg"
    persona_name: str = "default"


@dataclass(slots=True)
class ReplyResult:
    """回复结果

    Attributes:
        text: 回复文本
        segments: 碎片化段列表（非空时优先使用）
        sticker: 贴纸路径，None为不发贴纸
        tts_audio: TTS音频数据，None为不发TTS
        image_url: 生成图片的URL，None为不发图片
        typing_delay: 打字延迟（秒）
        gap_delays: 段间延迟列表（与segments对齐）
        tool_calls: 工具调用记录
        metadata: 附加元信息
    """

    text: str
    segments: list[str] = field(default_factory=list)
    sticker: Image | None = None
    tts_audio: bytes | None = None
    image_url: str | None = None
    typing_delay: float = 0.0
    gap_delays: list[float] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
