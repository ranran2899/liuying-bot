"""Agent运行时常量定义

定义Agent循环中使用的各种常量，包括回合动作、输出模式、
证据类型、延迟级别等。
"""

# ===== 回合动作 =====
TURN_ACTION_REPLY = "reply"
"""回复用户"""
TURN_ACTION_SILENCE = "silence"
"""保持沉默"""
TURN_ACTION_ASK_CLARIFY = "ask_clarify"
"""请求澄清"""

# ===== 输出模式 =====
OUTPUT_MODE_CHAT_SHORT = "chat_short"
"""短聊天回复"""
OUTPUT_MODE_CHAT_ANSWER = "chat_answer"
"""完整答案回复"""
OUTPUT_MODE_STRUCTURED_HELP = "structured_help"
"""结构化帮助"""
OUTPUT_MODE_SOURCE_SUMMARY = "source_summary"
"""来源摘要"""
OUTPUT_MODE_SILENCE = "silence"
"""静默"""

# ===== 证据类型 =====
EVIDENCE_KIND_TOOL = "tool"
"""工具证据"""
EVIDENCE_KIND_CONTEXT = "context"
"""上下文证据"""

# ===== 延迟级别 =====
LATENCY_CLASS_FAST = "fast"
"""快速（<1s）"""
LATENCY_CLASS_NETWORK = "network"
"""网络（1-5s）"""
LATENCY_CLASS_SLOW = "slow"
"""慢速（>5s）"""

# ===== 默认值 =====
DEFAULT_AGENT_MAX_STEPS = 10
"""默认Agent最大步数"""

DEFAULT_TIME_BUDGET = 180.0
"""默认时间预算（秒）"""

DEFAULT_TOOL_TIMEOUT = 30.0
"""默认工具超时（秒）"""

DEFAULT_RETRY_COUNT = 2
"""默认重试次数"""

# ===== 工具意图标签 =====
INTENT_TAG_REALTIME = "realtime"
"""实时信息查询"""
INTENT_TAG_MEMORY = "memory"
"""记忆召回"""
INTENT_TAG_IMAGE = "image"
"""图片相关"""
INTENT_TAG_NETWORK = "network"
"""网络请求"""
INTENT_TAG_ADMIN = "admin"
"""管理操作"""
INTENT_TAG_LOCAL = "local"
"""本地操作"""
INTENT_TAG_PLUGIN = "plugin"
"""插件调用"""

# ===== 角色化响应字段 =====
RESPONSE_FIELD_REPLY_TEXT = "reply_text"
RESPONSE_FIELD_INFO_ADDED = "info_added"
RESPONSE_FIELD_USER_ATTITUDE = "user_attitude"
RESPONSE_FIELD_BOT_EMOTION = "bot_emotion"
RESPONSE_FIELD_EXPRESSION_STYLE = "expression_style"
RESPONSE_FIELD_TTS_STYLE_HINT = "tts_style_hint"
RESPONSE_FIELD_STICKER_MOOD_HINT = "sticker_mood_hint"
RESPONSE_FIELD_AMBIGUITY_LEVEL = "ambiguity_level"
RESPONSE_FIELD_RECOMMEND_SILENCE = "recommend_silence"
