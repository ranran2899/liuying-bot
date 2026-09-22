"""LLM相关配置项

包含对话模型、嵌入模型、思考模式、Token额度与模型按角色路由等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from ._common import RegisterConfig, cfg

__all__ = ["LLM_CONFIGS"]

LLM_CONFIGS: list[RegisterConfig] = [
    # ===== 嵌入模型 =====
    cfg(
        "EMBEDDING",
        {"provider": None, "model": None},
        "嵌入模型配置（用于记忆/知识库向量生成）\n"
        " - provider: 供应商\n"
        " - model: 模型名（如embedding-3，不能用对话模型）",
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
            "chat": {
                "model": None, "provider": None, "temperature": 0.6,
                "capabilities": [],
                "reasoning": {"enabled": True, "effort": "high"},
            },
            "intent": {
                "model": None, "provider": None, "temperature": 0.1,
                "capabilities": [],
                "reasoning": {"enabled": False, "effort": "high"},
            },
            "review": {
                "model": None, "provider": None, "temperature": 0.1,
                "capabilities": [],
                "reasoning": {"enabled": False, "effort": "high"},
            },
            "agent": {
                "model": None, "provider": None, "temperature": 0.3,
                "capabilities": [],
                "reasoning": {"enabled": False, "effort": "high"},
            },
            "sticker": {
                "model": None, "provider": None, "temperature": 0.4,
                "capabilities": [],
                "reasoning": {"enabled": False, "effort": "high"},
            },
            "warmup": {
                "model": None, "provider": None, "temperature": 0.7,
                "capabilities": [],
                "reasoning": {"enabled": False, "effort": "high"},
            },
        },
        "模型按角色路由配置（chat 为对话主模型，其余角色缺省回退到 chat）\n"
        "每个角色可独立指定 model/provider/temperature/capabilities/reasoning\n"
        "chat 角色的 model/provider 即全局主模型\n"
        "非 chat 角色 model/provider 为 None 时回退到 chat 角色\n"
        "跨供应商使用模型时必须配置 provider\n"
        'capabilities 统一声明该模型支持的能力，词表：'
        '"vision"(看图/多模态输入)、"tools"(原生 function-calling)，'
        "空列表表示未声明（看图能力回退到关键词/探测判定）\n"
        "reasoning 声明该角色是否使用深度思考及强度：\n"
        " - enabled: 是否开启深度思考（按模型自定义，chat 默认开）\n"
        " - effort: 思考强度 max/high/low\n"
        " - chat: 对话主模型与正文生成（默认开启深度思考）\n"
        " - intent: 意图推断（低温度0.1）\n"
        " - review: 响应审查（低温度0.1）\n"
        " - agent: 统一 ReAct 循环模型（需 function-calling，中温度0.3）\n"
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
