"""拟人化相关配置项

包含打字延迟、错别字、贴纸、表情表态、拍一拍、引用回复等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["HUMANIZE_CONFIGS"]

HUMANIZE_CONFIGS: list[RegisterConfig] = [
    # ===== 打字延迟 =====
    RegisterConfig(
        key="HUMANIZE_TYPING",
        value={
            "enabled": True,
            "cps": 7.0,
            "max_delay": 5.0,
        },
        module=MODULE,
        help=(
            "打字延迟拟人化配置\n"
            " - enabled: 是否启用\n"
            " - cps: 打字速度（字符/秒）\n"
            " - max_delay: 最大打字延迟（秒）"
        ),
        default_value={
            "enabled": True,
            "cps": 7.0,
            "max_delay": 5.0,
        },
        type=dict,
    ),
    # ===== 错别字 =====
    RegisterConfig(
        key="HUMANIZE_TYPO_PROBABILITY",
        value=0.0,
        module=MODULE,
        help="错别字注入概率",
        default_value=0.0,
        type=float,
    ),
    # ===== 贴纸 =====
    RegisterConfig(
        key="STICKER",
        value={
            "enabled": True,
            "probability": 0.24,
            "semantic_enabled": True,
            "cache_enabled": True,
            "auto_label_enabled": False,
        },
        module=MODULE,
        help=(
            "贴纸配置\n"
            " - enabled: 是否启用\n"
            " - probability: 触发概率\n"
            " - semantic_enabled: 语义分析\n"
            " - cache_enabled: 缓存\n"
            " - auto_label_enabled: 自动标注"
        ),
        default_value={
            "enabled": True,
            "probability": 0.24,
            "semantic_enabled": True,
            "cache_enabled": True,
            "auto_label_enabled": False,
        },
        type=dict,
    ),
    # ===== 表情表态 =====
    RegisterConfig(
        key="REACTION",
        value={
            "enabled": True,
            "probability": 0.15,
        },
        module=MODULE,
        help=(
            "表情表态配置\n"
            " - enabled: 是否启用\n"
            " - probability: 沉默时表态概率"
        ),
        default_value={
            "enabled": True,
            "probability": 0.15,
        },
        type=dict,
    ),
    # ===== 拍一拍 =====
    RegisterConfig(
        key="POKE",
        value={
            "enabled": True,
            "probability": 0.3,
            "proactive_enabled": False,
        },
        module=MODULE,
        help=(
            "拍一拍配置\n"
            " - enabled: 是否启用拍一拍回复\n"
            " - probability: 被戳后戳回概率\n"
            " - proactive_enabled: 主动拍一拍"
        ),
        default_value={
            "enabled": True,
            "probability": 0.3,
            "proactive_enabled": False,
        },
        type=dict,
    ),
    # ===== 输入状态 =====
    RegisterConfig(
        key="INPUT_STATUS_ENABLED",
        value=False,
        module=MODULE,
        help="是否启用输入状态显示",
        default_value=False,
        type=bool,
    ),
    # ===== 引用回复 =====
    RegisterConfig(
        key="QUOTE_REPLY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用引用回复",
        default_value=True,
        type=bool,
    ),
    # ===== @回复 =====
    RegisterConfig(
        key="AT_REPLY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用@回复",
        default_value=True,
        type=bool,
    ),
    # ===== 碎片化输出 =====
    RegisterConfig(
        key="FRAGMENT",
        value={
            "style": "prompt",
            "max_chars": 40,
        },
        module=MODULE,
        help=(
            "碎片化输出配置\n"
            " - style: 风格（off或prompt）\n"
            " - max_chars: 单段最大字符数"
        ),
        default_value={
            "style": "prompt",
            "max_chars": 40,
        },
        type=dict,
    ),
    # ===== 消息批量缓冲 =====
    RegisterConfig(
        key="REPLY_BUFFER",
        value={
            "enabled": True,
            "group_delay": 1.2,
            "private_delay": 0.8,
        },
        module=MODULE,
        help=(
            "消息批量缓冲配置\n"
            " - enabled: 是否启用\n"
            " - group_delay: 群聊缓冲窗口（秒）\n"
            " - private_delay: 私聊缓冲窗口（秒）"
        ),
        default_value={
            "enabled": True,
            "group_delay": 1.2,
            "private_delay": 0.8,
        },
        type=dict,
    ),
]
"""拟人化相关配置项列表"""
