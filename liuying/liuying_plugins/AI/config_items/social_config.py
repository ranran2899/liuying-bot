"""社交与主动行为配置项

包含主动行为、群静默、社交智能、同伴感知、跟队形与热聊保护等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["SOCIAL_CONFIGS"]

SOCIAL_CONFIGS: list[RegisterConfig] = [
    # ===== 主动行为 =====
    RegisterConfig(
        key="PROACTIVE",
        value={
            "enabled": True,
            "interval_minutes": 30,
            "group_idle_minutes": 90,
            "daily_limit": 3,
        },
        module=MODULE,
        help=(
            "主动行为配置\n"
            " - enabled: 是否启用\n"
            " - interval_minutes: 检查间隔（分钟）\n"
            " - group_idle_minutes: 群空闲触发阈值（分钟）\n"
            " - daily_limit: 每日上限"
        ),
        default_value={
            "enabled": True,
            "interval_minutes": 30,
            "group_idle_minutes": 90,
            "daily_limit": 3,
        },
        type=dict,
    ),
    # ===== 群深夜静默 =====
    RegisterConfig(
        key="GROUP_QUIET",
        value={
            "start": 0,
            "end": 7,
        },
        module=MODULE,
        help=(
            "群深夜静默配置\n"
            " - start: 开始小时\n"
            " - end: 结束小时"
        ),
        default_value={"start": 0, "end": 7},
        type=dict,
    ),
    # ===== 社交智能 =====
    RegisterConfig(
        key="SOCIAL_INTELLIGENCE_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用社交智能",
        default_value=True,
        type=bool,
    ),
    # ===== 社交LLM闸门 =====
    RegisterConfig(
        key="SOCIAL_GATE_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用社交LLM闸门",
        default_value=False,
        type=bool,
    ),
    # ===== 社交配额 =====
    RegisterConfig(
        key="SOCIAL_QUOTA",
        value={
            "per_user": 5,
            "cooldown": 3600,
        },
        module=MODULE,
        help=(
            "社交配额配置\n"
            " - per_user: 每用户每日主动消息配额\n"
            " - cooldown: 单场景冷却时间（秒）"
        ),
        default_value={"per_user": 5, "cooldown": 3600},
        type=dict,
    ),
    # ===== 同伴感知 =====
    RegisterConfig(
        key="PEER_AWARENESS_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用同伴感知",
        default_value=True,
        type=bool,
    ),
    # ===== 跟队形 =====
    RegisterConfig(
        key="REPEAT_FOLLOW_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用跟队形",
        default_value=True,
        type=bool,
    ),
    # ===== 热聊保护 =====
    RegisterConfig(
        key="HOT_CHAT",
        value={
            "enabled": True,
            "min_pass_rate": 0.3,
        },
        module=MODULE,
        help=(
            "热聊保护配置\n"
            " - enabled: 是否启用\n"
            " - min_pass_rate: 随机发言最低通过率"
        ),
        default_value={"enabled": True, "min_pass_rate": 0.3},
        type=dict,
    ),
    # ===== 群风格自动学习 =====
    RegisterConfig(
        key="GROUP_STYLE_AUTOBUILD",
        value={
            "enabled": True,
            "interval": 12,
        },
        module=MODULE,
        help=(
            "群风格自动学习配置\n"
            " - enabled: 是否启用\n"
            " - interval: 学习间隔（小时）"
        ),
        default_value={"enabled": True, "interval": 12},
        type=dict,
    ),
    # ===== 主动拍一拍每日上限 =====
    RegisterConfig(
        key="PROACTIVE_POKE_DAILY_LIMIT",
        value=3,
        module=MODULE,
        help="主动拍一拍每日触发上限",
        default_value=3,
        type=int,
    ),
]
"""社交与主动行为配置项列表"""
