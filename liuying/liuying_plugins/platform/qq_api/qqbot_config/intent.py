"""QQ机器人意图字段定义

字段名与新版QQ适配器(nonebot.adapters.qq)的 Intents 模型一一对应,
由 BotInfo 构建时经 pydantic 校验
"""

INTENT_DESCRIPTIONS: dict[str, str] = {
    "guilds": "频道事件",
    "guild_members": "频道成员事件",
    "guild_messages": "频道消息事件",
    "guild_message_reactions": "频道消息表态事件",
    "direct_message": "私信事件",
    "open_forum_event": "论坛事件(公开版)",
    "audio_live_member": "语音直播成员事件",
    "group_members": "群成员事件",
    "c2c_group_at_messages": "C2C和群@消息事件",
    "interaction": "互动事件",
    "message_audit": "消息审核事件",
    "forum_event": "论坛事件",
    "audio_action": "音频操作事件",
    "at_messages": "@消息事件",
}
"""意图字段中文描述"""

VALID_INTENT_FIELDS = frozenset(INTENT_DESCRIPTIONS)
"""有效的意图字段集合"""

DEFAULT_INTENT: dict[str, bool] = {
    "guilds": True,
    "guild_members": True,
    "guild_messages": False,
    "guild_message_reactions": True,
    "direct_message": False,
    "open_forum_event": False,
    "audio_live_member": False,
    "group_members": True,
    "c2c_group_at_messages": True,
    "interaction": False,
    "message_audit": True,
    "forum_event": False,
    "audio_action": False,
    "at_messages": True,
}
"""默认QQ机器人意图(群聊场景需要 group_members 与 c2c_group_at_messages)"""
