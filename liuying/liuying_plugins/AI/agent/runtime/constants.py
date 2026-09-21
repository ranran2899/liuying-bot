"""Agent运行时常量定义

定义工具元数据与循环默认值：证据/来源类型、延迟级别、
工具意图标签、工具超时等。
"""

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
DEFAULT_TOOL_TIMEOUT = 30.0
"""默认工具超时（秒）"""

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
