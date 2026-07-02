"""Agent相关配置项

包含Agent工具调用、响应审查、交叉验证与主动学习等配置。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["AGENT_CONFIGS"]

AGENT_CONFIGS: list[RegisterConfig] = [
    RegisterConfig(
        key="AGENT_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用Agent工具调用",
        default_value=True,
        type=bool,
    ),
    RegisterConfig(
        key="AGENT_MAX_STEPS",
        value=10,
        module=MODULE,
        help="Agent最大循环步数",
        default_value=10,
        type=int,
    ),
    RegisterConfig(
        key="RESPONSE_TIMEOUT",
        value=180,
        module=MODULE,
        help="响应超时时间（秒）",
        default_value=180,
        type=int,
    ),
    # ===== Phase1: 核心Agent增强 =====
    RegisterConfig(
        key="RESPONSE_REVIEW_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用LLM响应深度审查",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="CROSS_VERIFY_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用工具证据交叉验证",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="ACTIVE_LEARNING_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用主动学习",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="MEMORY_EVOLVE_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆进化",
        default_value=True,
        type=bool,
    ),
]
"""Agent相关配置项列表"""
