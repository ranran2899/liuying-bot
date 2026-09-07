"""Agent相关配置项

包含Agent工具调用、响应审查与主动学习等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from ._common import RegisterConfig, cfg

__all__ = ["AGENT_CONFIGS"]

AGENT_CONFIGS: list[RegisterConfig] = [
    # ===== Agent工具调用 =====
    cfg(
        "AGENT",
        {
            "enabled": True,
            "max_steps": 10,
            "response_timeout": 180,
        },
        "Agent工具调用配置\n"
        " - enabled: 是否启用\n"
        " - max_steps: 最大循环步数\n"
        " - response_timeout: 响应超时时间（秒）",
        dict,
    ),
    # ===== 响应审查 =====
    cfg(
        "RESPONSE_REVIEW_ENABLED",
        False,
        "是否启用LLM响应深度审查",
        bool,
    ),
    # ===== 主动学习 =====
    cfg(
        "ACTIVE_LEARNING_ENABLED",
        False,
        "是否启用主动学习",
        bool,
    ),
    # ===== 记忆进化 =====
    cfg(
        "MEMORY_EVOLVE_ENABLED",
        True,
        "是否启用记忆进化",
        bool,
    ),
    # ===== 聊天意图语义帧 =====
    cfg(
        "CHAT_INTENT_ENABLED",
        True,
        "是否启用LLM语义帧推断（关闭时仅用关键词规则）",
        bool,
    ),
    # ===== 用户自定义定时任务 =====
    cfg(
        "USER_TASKS_ENABLED",
        True,
        "是否启用用户自定义定时任务",
        bool,
    ),
    # ===== MCP桥接 =====
    cfg(
        "MCP",
        {"enabled": False, "servers": ""},
        "MCP桥接配置（远程工具协议）\n"
        " - enabled: 是否启用\n"
        " - servers: 服务器配置（JSON数组）",
        dict,
    ),
]
"""Agent相关配置项列表"""
