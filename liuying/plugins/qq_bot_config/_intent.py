"""QQ机器人意图字段定义"""

from enum import StrEnum
from typing import Self


class IntentField(StrEnum):
    """QQ机器人意图字段枚举

    每个成员的 description 属性存储中文描述,
    避免 INTENT_DESCRIPTIONS 单独维护造成重复
    """

    GUILDS = "guilds", "频道事件"
    """频道事件"""
    GUILD_MEMBERS = "guild_members", "频道成员事件"
    """频道成员事件"""
    GUILD_MESSAGES = "guild_messages", "频道消息事件"
    """频道消息事件"""
    GUILD_MESSAGE_REACTIONS = "guild_message_reactions", "频道消息表态事件"
    """频道消息表态事件"""
    DIRECT_MESSAGE = "direct_message", "私信事件"
    """私信事件"""
    OPEN_FORUM_EVENT = "open_forum_event", "论坛事件(公开版)"
    """论坛事件(公开版)"""
    AUDIO_LIVE_MEMBER = "audio_live_member", "语音直播成员事件"
    """语音直播成员事件"""
    GROUP_MEMBERS = "group_members", "群成员事件"
    """群成员事件"""
    C2C_GROUP_AT_MESSAGES = "c2c_group_at_messages", "C2C和群@消息事件"
    """C2C和群@消息事件"""
    INTERACTION = "interaction", "互动事件"
    """互动事件"""
    MESSAGE_AUDIT = "message_audit", "消息审核事件"
    """消息审核事件"""
    FORUM_EVENT = "forum_event", "论坛事件"
    """论坛事件"""
    AUDIO_ACTION = "audio_action", "音频操作事件"
    """音频操作事件"""
    AT_MESSAGES = "at_messages", "@消息事件"
    """@消息事件"""

    description: str
    """字段中文描述"""

    def __new__(cls, value: str, description: str) -> Self:
        """构造枚举成员

        参数:
            value: 枚举值字符串
            description: 字段中文描述
        """
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        return member


INTENT_DESCRIPTIONS: dict[str, str] = {
    field.value: field.description for field in IntentField
}
"""意图字段描述映射(由枚举自动生成)"""

DEFAULT_INTENT: dict[str, bool] = {
    IntentField.GUILDS: True,
    IntentField.GUILD_MEMBERS: True,
    IntentField.GUILD_MESSAGES: False,
    IntentField.GUILD_MESSAGE_REACTIONS: True,
    IntentField.DIRECT_MESSAGE: False,
    IntentField.OPEN_FORUM_EVENT: False,
    IntentField.AUDIO_LIVE_MEMBER: False,
    IntentField.GROUP_MEMBERS: True,
    IntentField.C2C_GROUP_AT_MESSAGES: True,
    IntentField.INTERACTION: False,
    IntentField.MESSAGE_AUDIT: True,
    IntentField.FORUM_EVENT: False,
    IntentField.AUDIO_ACTION: False,
    IntentField.AT_MESSAGES: True,
}
"""默认QQ机器人意图"""

VALID_INTENT_FIELDS = frozenset(IntentField)
"""有效的意图字段集合"""
