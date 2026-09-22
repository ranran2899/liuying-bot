"""记忆相关配置项

包含记忆系统开关、召回、衰减、巩固与历史窗口等配置。
"""

from ._common import RegisterConfig, cfg

__all__ = ["MEMORY_CONFIGS"]

MEMORY_CONFIGS: list[RegisterConfig] = [
    # ===== 记忆系统开关 =====
    cfg(
        "MEMORY_ENABLED",
        True,
        "是否启用记忆系统",
        bool,
    ),
    # ===== 记忆召回 =====
    cfg(
        "MEMORY_RECALL",
        {"top_k": 5},
        "记忆召回配置\n - top_k: 召回数量",
        dict,
    ),
    # ===== 记忆衰减 =====
    cfg(
        "MEMORY_DECAY_ENABLED",
        True,
        "是否启用记忆衰减",
        bool,
    ),
    # ===== 记忆巩固 =====
    cfg(
        "MEMORY_CONSOLIDATION_ENABLED",
        True,
        "是否启用记忆巩固",
        bool,
    ),
    # ===== 历史对话窗口 =====
    cfg(
        "HISTORY_LEN",
        20,
        "历史对话窗口长度",
        int,
    ),
    # ===== 知识检索查询改写 =====
    cfg(
        "KNOWLEDGE_QUERY_REWRITE_ENABLED",
        False,
        "是否启用检索查询改写（LLM识别梗/黑话/缩写补出正式名；"
        "位于消息热路径会叠加一次LLM调用延迟，仅深度召回场景建议开启）",
        bool,
    ),
    # ===== LLM嵌入模型 =====
    cfg(
        "MEMORY_USE_LLM_EMBEDDING",
        False,
        "是否启用LLM嵌入模型（需配置EMBEDDING配置组，启用后记忆向量质量提升，失败自动降级到本地哈希）",
        bool,
    ),
]
"""记忆相关配置项列表"""
