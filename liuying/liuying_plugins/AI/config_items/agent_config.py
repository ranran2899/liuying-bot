"""Agent相关配置项

包含Agent工具调用、响应审查、交叉验证与主动学习等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["AGENT_CONFIGS"]

AGENT_CONFIGS: list[RegisterConfig] = [
    # ===== Agent工具调用 =====
    RegisterConfig(
        key="AGENT",
        value={
            "enabled": True,
            "max_steps": 10,
            "response_timeout": 180,
        },
        module=MODULE,
        help=(
            "Agent工具调用配置\n"
            " - enabled: 是否启用\n"
            " - max_steps: 最大循环步数\n"
            " - response_timeout: 响应超时时间（秒）"
        ),
        default_value={
            "enabled": True,
            "max_steps": 10,
            "response_timeout": 180,
        },
        type=dict,
    ),
    # ===== 响应审查 =====
    RegisterConfig(
        key="RESPONSE_REVIEW_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用LLM响应深度审查",
        default_value=False,
        type=bool,
    ),
    # ===== 交叉验证 =====
    RegisterConfig(
        key="CROSS_VERIFY_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用工具证据交叉验证",
        default_value=False,
        type=bool,
    ),
    # ===== 主动学习 =====
    RegisterConfig(
        key="ACTIVE_LEARNING_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用主动学习",
        default_value=False,
        type=bool,
    ),
    # ===== 记忆进化 =====
    RegisterConfig(
        key="MEMORY_EVOLVE_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆进化",
        default_value=True,
        type=bool,
    ),
    # ===== 聊天意图语义帧 =====
    RegisterConfig(
        key="CHAT_INTENT_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用LLM语义帧推断（关闭时仅用关键词规则）",
        default_value=True,
        type=bool,
    ),
    # ===== 用户自定义定时任务 =====
    RegisterConfig(
        key="USER_TASKS_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用用户自定义定时任务",
        default_value=True,
        type=bool,
    ),
    # ===== MCP桥接 =====
    RegisterConfig(
        key="MCP",
        value={
            "enabled": False,
            "servers": "",
        },
        module=MODULE,
        help=(
            "MCP桥接配置（远程工具协议）\n"
            " - enabled: 是否启用\n"
            " - servers: 服务器配置（JSON数组）"
        ),
        default_value={"enabled": False, "servers": ""},
        type=dict,
    ),
]
"""Agent相关配置项列表"""
