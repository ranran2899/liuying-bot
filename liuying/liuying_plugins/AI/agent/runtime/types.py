"""Agent 循环共享数据类型

承载工具编排循环与主模型回复阶段共用的数据类：角色化响应、
工具调用记录与循环产出。单独成模块以解耦 ``loop`` 与
``reply_composer``，避免二者相互导入产生循环依赖。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PersonaResponse:
    """角色化响应

    Attributes:
        reply_text: 回复正文
        info_added: 是否补充了新信息
        user_attitude: 推测的用户态度
        bot_emotion: AI情绪
        expression_style: 表达风格
        tts_style_hint: TTS风格提示
        sticker_mood_hint: 表情包情绪提示
        ambiguity_level: 回复模糊度
        recommend_silence: 是否建议静默
        ask_clarify: 是否需要澄清
        elapsed: 生成耗时（秒）
        raw_response: 原始回复文本（调试用）
    """

    reply_text: str = ""
    info_added: bool = False
    user_attitude: str = "neutral"
    bot_emotion: str = "neutral"
    expression_style: str = "casual"
    tts_style_hint: str = ""
    sticker_mood_hint: str = ""
    ambiguity_level: float = 0.0
    recommend_silence: bool = False
    ask_clarify: bool = False
    elapsed: float = 0.0
    raw_response: str = ""

    @property
    def is_silence(self) -> bool:
        """是否静默"""
        return self.recommend_silence or not self.reply_text.strip()

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 响应字典
        """
        return {
            "reply_text": self.reply_text,
            "info_added": self.info_added,
            "user_attitude": self.user_attitude,
            "bot_emotion": self.bot_emotion,
            "expression_style": self.expression_style,
            "tts_style_hint": self.tts_style_hint,
            "sticker_mood_hint": self.sticker_mood_hint,
            "ambiguity_level": self.ambiguity_level,
            "recommend_silence": self.recommend_silence,
            "ask_clarify": self.ask_clarify,
            "elapsed": round(self.elapsed, 3),
        }


@dataclass(slots=True)
class ToolCallRecord:
    """工具调用记录

    Attributes:
        tool_name: 工具名
        args: 调用参数
        result: 调用结果
        elapsed: 耗时（秒）
        success: 是否成功
        error: 错误信息（失败时）
        timestamp: 调用时间戳
        metadata: 工具元数据
    """

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    elapsed: float = 0.0
    success: bool = False
    error: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 调用记录字典
        """
        return {
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "result": self.result[:500],
            "elapsed": round(self.elapsed, 3),
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class AgentOutcome:
    """Agent 循环产出

    Attributes:
        response: 角色化响应
        tool_calls: 工具调用记录列表
        steps: 实际执行步数
        metrics: 执行指标
        image_url: 生成的图片URL，None表示无图片
        elapsed: 总耗时（秒）
    """

    response: PersonaResponse
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    steps: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    image_url: str | None = None
    elapsed: float = 0.0
