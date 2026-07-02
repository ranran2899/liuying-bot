"""QQ机器人意图字段定义"""

from enum import StrEnum


class IntentField(StrEnum):
    """QQ机器人意图字段枚举"""

    GUILDS = "guilds"
    """频道事件"""
    GUILD_MEMBERS = "guild_members"
    """频道成员事件"""
    GUILD_MESSAGES = "guild_messages"
    """频道消息事件"""
    GUILD_MESSAGE_REACTIONS = "guild_message_reactions"
    """频道消息表态事件"""
    DIRECT_MESSAGE = "direct_message"
    """私信事件"""
    OPEN_FORUM_EVENT = "open_forum_event"
    """论坛事件(公开版)"""
    AUDIO_LIVE_MEMBER = "audio_live_member"
    """语音直播成员事件"""
    C2C_GROUP_AT_MESSAGES = "c2c_group_at_messages"
    """C2C和群@消息事件"""
    INTERACTION = "interaction"
    """互动事件"""
    MESSAGE_AUDIT = "message_audit"
    """消息审核事件"""
    FORUM_EVENT = "forum_event"
    """论坛事件"""
    AUDIO_ACTION = "audio_action"
    """音频操作事件"""
    AT_MESSAGES = "at_messages"
    """@消息事件"""


INTENT_DESCRIPTIONS: dict[str, str] = {
    IntentField.GUILDS: "频道事件",
    IntentField.GUILD_MEMBERS: "频道成员事件",
    IntentField.GUILD_MESSAGES: "频道消息事件",
    IntentField.GUILD_MESSAGE_REACTIONS: "频道消息表态事件",
    IntentField.DIRECT_MESSAGE: "私信事件",
    IntentField.OPEN_FORUM_EVENT: "论坛事件(公开版)",
    IntentField.AUDIO_LIVE_MEMBER: "语音直播成员事件",
    IntentField.C2C_GROUP_AT_MESSAGES: "C2C和群@消息事件",
    IntentField.INTERACTION: "互动事件",
    IntentField.MESSAGE_AUDIT: "消息审核事件",
    IntentField.FORUM_EVENT: "论坛事件",
    IntentField.AUDIO_ACTION: "音频操作事件",
    IntentField.AT_MESSAGES: "@消息事件",
}
"""意图字段描述映射"""

DEFAULT_INTENT: dict[str, bool] = {
    IntentField.GUILDS: True,
    IntentField.GUILD_MEMBERS: True,
    IntentField.GUILD_MESSAGES: False,
    IntentField.GUILD_MESSAGE_REACTIONS: True,
    IntentField.DIRECT_MESSAGE: False,
    IntentField.OPEN_FORUM_EVENT: False,
    IntentField.AUDIO_LIVE_MEMBER: False,
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
