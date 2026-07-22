"""记忆相关配置项

包含记忆系统开关、召回、衰减、巩固与历史窗口等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["MEMORY_CONFIGS"]

MEMORY_CONFIGS: list[RegisterConfig] = [
    # ===== 记忆系统开关 =====
    RegisterConfig(
        key="MEMORY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆系统",
        default_value=True,
        type=bool,
    ),
    # ===== 记忆召回 =====
    RegisterConfig(
        key="MEMORY_RECALL",
        value={
            "top_k": 5,
            "mode": "auto",
        },
        module=MODULE,
        help=(
            "记忆召回配置\n"
            " - top_k: 召回数量\n"
            " - mode: 召回模式（auto/fast/deep）"
        ),
        default_value={"top_k": 5, "mode": "auto"},
        type=dict,
    ),
    # ===== 记忆衰减 =====
    RegisterConfig(
        key="MEMORY_DECAY_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆衰减",
        default_value=True,
        type=bool,
    ),
    # ===== 记忆巩固 =====
    RegisterConfig(
        key="MEMORY_CONSOLIDATION_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用记忆巩固",
        default_value=True,
        type=bool,
    ),
    # ===== 历史对话窗口 =====
    RegisterConfig(
        key="HISTORY_LEN",
        value=20,
        module=MODULE,
        help="历史对话窗口长度",
        default_value=20,
        type=int,
    ),
    # ===== 知识检索查询改写 =====
    RegisterConfig(
        key="KNOWLEDGE_QUERY_REWRITE_ENABLED",
        value=True,
        module=MODULE,
        help="是否启用检索查询改写（LLM识别梗/黑话/缩写补出正式名）",
        default_value=True,
        type=bool,
    ),
    # ===== LLM嵌入模型 =====
    RegisterConfig(
        key="MEMORY_USE_LLM_EMBEDDING",
        value=False,
        module=MODULE,
        help=(
            "是否启用LLM嵌入模型（需配置EMBEDDING配置组，"
            "启用后记忆向量质量提升，失败自动降级到本地哈希）"
        ),
        default_value=False,
        type=bool,
    ),
]
"""记忆相关配置项列表"""
