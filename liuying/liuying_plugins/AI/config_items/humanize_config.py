"""拟人化相关配置项

包含打字延迟、错别字、贴纸、表情表态、拍一拍、引用回复等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["HUMANIZE_CONFIGS"]

HUMANIZE_CONFIGS: list[RegisterConfig] = [
    # ===== 打字延迟 =====
    cfg(
        "HUMANIZE_TYPING",
        {
            "enabled": True,
            "cps": 7.0,
            "max_delay": 5.0,
        },
        "打字延迟拟人化配置\n"
        " - enabled: 是否启用\n"
        " - cps: 打字速度（字符/秒）\n"
        " - max_delay: 最大打字延迟（秒）",
        dict,
    ),
    # ===== 错别字 =====
    cfg(
        "HUMANIZE_TYPO_PROBABILITY",
        0.0,
        "错别字注入概率",
        float,
    ),
    # ===== 贴纸 =====
    cfg(
        "STICKER",
        {
            "enabled": True,
            "probability": 0.24,
            "semantic_enabled": True,
            "cache_enabled": True,
            "auto_label_enabled": False,
        },
        "贴纸配置\n"
        " - enabled: 是否启用\n"
        " - probability: 触发概率\n"
        " - semantic_enabled: 语义分析\n"
        " - cache_enabled: 缓存\n"
        " - auto_label_enabled: 自动标注",
        dict,
    ),
    # ===== 表情表态 =====
    cfg(
        "REACTION",
        {"enabled": True, "probability": 0.15},
        "表情表态配置\n - enabled: 是否启用\n - probability: 沉默时表态概率",
        dict,
    ),
    # ===== 拍一拍 =====
    cfg(
        "POKE",
        {
            "enabled": True,
            "probability": 0.3,
            "proactive_enabled": False,
        },
        "拍一拍配置\n"
        " - enabled: 是否启用拍一拍回复\n"
        " - probability: 被戳后戳回概率\n"
        " - proactive_enabled: 主动拍一拍",
        dict,
    ),
    # ===== 输入状态 =====
    cfg(
        "INPUT_STATUS_ENABLED",
        False,
        "是否启用输入状态显示",
        bool,
    ),
    # ===== 引用回复 =====
    cfg(
        "QUOTE_REPLY_ENABLED",
        True,
        "是否启用引用回复",
        bool,
    ),
    # ===== @回复 =====
    cfg(
        "AT_REPLY_ENABLED",
        True,
        "是否启用@回复",
        bool,
    ),
    # ===== 碎片化输出 =====
    cfg(
        "FRAGMENT",
        {"style": "prompt", "max_chars": 40},
        "碎片化输出配置\n - style: 风格（off或prompt）\n - max_chars: 单段最大字符数",
        dict,
    ),
    # ===== 消息批量缓冲 =====
    cfg(
        "REPLY_BUFFER",
        {
            "enabled": True,
            "group_delay": 1.2,
            "private_delay": 0.8,
        },
        "消息批量缓冲配置\n"
        " - enabled: 是否启用\n"
        " - group_delay: 群聊缓冲窗口（秒）\n"
        " - private_delay: 私聊缓冲窗口（秒）",
        dict,
    ),
]
"""拟人化相关配置项列表"""
