"""社交与主动行为配置项

包含主动行为、群静默、社交智能、同伴感知与群风格自动学习等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from ._common import RegisterConfig, cfg

__all__ = ["SOCIAL_CONFIGS"]

SOCIAL_CONFIGS: list[RegisterConfig] = [
    # ===== 主动行为 =====
    cfg(
        "PROACTIVE",
        {
            "enabled": True,
            "interval_minutes": 30,
            "group_idle_minutes": 90,
            "daily_limit": 3,
        },
        "主动行为配置\n"
        " - enabled: 是否启用\n"
        " - interval_minutes: 检查间隔（分钟）\n"
        " - group_idle_minutes: 群空闲触发阈值（分钟）\n"
        " - daily_limit: 每日上限",
        dict,
    ),
    # ===== 群深夜静默 =====
    cfg(
        "GROUP_QUIET",
        {"start": 0, "end": 7},
        "群深夜静默配置\n - start: 开始小时\n - end: 结束小时",
        dict,
    ),
    # ===== 社交智能 =====
    cfg(
        "SOCIAL_INTELLIGENCE_ENABLED",
        True,
        "是否启用社交智能",
        bool,
    ),
    # ===== 社交LLM闸门 =====
    cfg(
        "SOCIAL_GATE_ENABLED",
        False,
        "是否启用社交LLM闸门",
        bool,
    ),
    # ===== 社交配额 =====
    cfg(
        "SOCIAL_QUOTA",
        {"per_user": 5, "cooldown": 3600},
        "社交配额配置\n"
        " - per_user: 每用户每日主动消息配额\n"
        " - cooldown: 单场景冷却时间（秒）",
        dict,
    ),
    # ===== 同伴感知 =====
    cfg(
        "PEER_AWARENESS_ENABLED",
        True,
        "是否启用同伴感知",
        bool,
    ),
    # ===== 群风格自动学习 =====
    cfg(
        "GROUP_STYLE_AUTOBUILD",
        {"enabled": True, "interval": 12},
        "群风格自动学习配置\n - enabled: 是否启用\n - interval: 学习间隔（小时）",
        dict,
    ),
    # ===== 主动拍一拍每日上限 =====
    cfg(
        "PROACTIVE_POKE_DAILY_LIMIT",
        3,
        "主动拍一拍每日触发上限",
        int,
    ),
]
"""社交与主动行为配置项列表"""
