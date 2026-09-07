"""杂项配置项

包含主开关、人格、响应长度、WebUI、日记等不便归类的配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["MISC_CONFIGS"]

MISC_CONFIGS: list[RegisterConfig] = [
    cfg(
        "ENABLE_AI",
        False,
        "是否启用AI对话",
        bool,
    ),
    cfg(
        "DEFAULT_PERSONA",
        "liuying",
        "默认人格名",
        str,
    ),
    cfg(
        "MAX_RESPONSE_LENGTH",
        200,
        "最大响应长度",
        int,
    ),
    cfg(
        "COST_GOLD",
        0,
        "调用花费金币",
        int,
    ),
    cfg(
        "WEBUI_ENABLED",
        True,
        "是否启用WebUI管理接口（挂载到本体web_ui插件）",
        bool,
    ),
    cfg(
        "DIARY_ENABLED",
        True,
        "是否启用日记系统",
        bool,
    ),
    cfg(
        "PROACTIVE_DIAGNOSTICS_ENABLED",
        False,
        "是否启用主动诊断",
        bool,
    ),
    cfg(
        "PEER_BOT_IDS",
        "",
        "其他bot用户ID列表（逗号分隔），用于环境感知静默",
        str,
    ),
    cfg(
        "THREAD_TRACKER_ENABLED",
        True,
        "是否启用话题线程追踪",
        bool,
    ),
    cfg(
        "TARGET_INFERENCE_ENABLED",
        True,
        "是否启用消息目标推断（群聊精准回复，避免误回复@他人）",
        bool,
    ),
]
"""杂项配置项列表"""

