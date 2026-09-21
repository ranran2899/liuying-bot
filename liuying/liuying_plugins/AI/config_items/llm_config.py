"""LLM相关配置项

包含对话模型、嵌入模型、思考模式、Token额度与模型按角色路由等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from ._common import RegisterConfig, cfg

__all__ = ["LLM_CONFIGS"]

LLM_CONFIGS: list[RegisterConfig] = [
    # ===== 对话模型 =====
    cfg(
        "CHAT_MODEL",
        {"provider": None, "model": None},
        "对话模型配置\n"
        " - provider: 供应商，None时用默认\n"
        " - model: 模型名，None时用provider默认",
        dict,
    ),
    # ===== 嵌入模型 =====
    cfg(
        "EMBEDDING",
        {"provider": None, "model": None},
        "嵌入模型配置（用于记忆/知识库向量生成）\n"
        " - provider: 供应商\n"
        " - model: 模型名（如embedding-3，不能用对话模型）",
        dict,
    ),
    # ===== 思考模式 =====
    cfg(
        "THINKING",
        {"enabled": False, "effort": "high"},
        "深度思考配置\n"
        " - enabled: 是否开启深度思考（开启时向模型请求思考链）\n"
        " - effort: 思考强度，可选值：\n"
        "   max: 深度推理（最消耗token）\n"
        "   high: 增强推理（默认）\n"
        "   low: 轻度推理",
        dict,
    ),
    # ===== 用户对话Token额度 =====
    cfg(
        "TOKEN_QUOTA",
        {
            "enabled": True,
            "reminder_cd": 300,
            "min_threshold": 1,
        },
        "用户对话token额度配置\n"
        " - enabled: 是否启用额度限制\n"
        " - reminder_cd: 额度不足提醒冷却（秒）\n"
        " - min_threshold: 可用token最低阈值",
        dict,
    ),
    # ===== 模型按角色路由 =====
    cfg(
        "MODEL_ROUTES",
        {
            "intent": {"model": None, "provider": None, "temperature": 0.1},
            "review": {"model": None, "provider": None, "temperature": 0.1},
            "agent": {"model": None, "provider": None, "temperature": 0.3},
            "sticker": {"model": None, "provider": None, "temperature": 0.4},
            "warmup": {"model": None, "provider": None, "temperature": 0.7},
        },
        "模型按角色路由配置\n"
        "每个角色可独立指定 model/provider/temperature\n"
        "model为None时回退到CHAT_MODEL.model\n"
        "provider为None时回退到CHAT_MODEL.provider\n"
        "跨供应商使用模型时必须配置provider\n"
        " - intent: 意图推断（低温度0.1）\n"
        " - review: 响应审查（低温度0.1）\n"
        " - agent: 统一 ReAct 循环模型（需支持 function-calling，中温度0.3）\n"
        " - sticker: 贴纸选择（中温度0.4）\n"
        " - warmup: 预热任务（高温度0.7）",
        dict,
    ),
    # ===== AI CLI路由降级 =====
    cfg(
        "AI_CLI",
        {"enabled": False, "routes": ""},
        "CLI路由降级配置（HTTP provider全部失败时尝试CLI工具）\n"
        " - enabled: 是否启用\n"
        " - routes: CLI路由列表JSON",
        dict,
    ),
]
"""LLM相关配置项列表"""
