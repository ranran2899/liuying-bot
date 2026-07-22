"""LLM相关配置项

包含对话模型、嵌入模型、轻量模型、思考模式与Token额度等配置。
采用嵌套字典组织相关配置项，提升可读性。
"""

from liuying.configs.utils import RegisterConfig

from ._common import MODULE

__all__ = ["LLM_CONFIGS"]

LLM_CONFIGS: list[RegisterConfig] = [
    # ===== 对话模型 =====
    RegisterConfig(
        key="CHAT_MODEL",
        value={
            "provider": None,
            "model": None,
        },
        module=MODULE,
        help=(
            "对话模型配置\n"
            " - provider: 供应商，None时用默认\n"
            " - model: 模型名，None时用provider默认"
        ),
        default_value={"provider": None, "model": None},
        type=dict,
    ),
    # ===== 嵌入模型 =====
    RegisterConfig(
        key="EMBEDDING",
        value={
            "provider": None,
            "model": None,
        },
        module=MODULE,
        help=(
            "嵌入模型配置（用于记忆/知识库向量生成）\n"
            " - provider: 供应商\n"
            " - model: 模型名（如embedding-3，不能用对话模型）"
        ),
        default_value={"provider": None, "model": None},
        type=dict,
    ),
    # ===== 思考模式 =====
    RegisterConfig(
        key="THINKING_MODE_ENABLED",
        value=False,
        module=MODULE,
        help="是否开启深度思考请求（开启时向模型请求思考链）",
        default_value=False,
        type=bool,
    ),
    # ===== 轻量模型（已废弃，由MODEL_ROUTES替代） =====
    RegisterConfig(
        key="LITE_MODEL",
        value={
            "enabled": False,
            "provider": None,
            "name": None,
        },
        module=MODULE,
        help=(
            "轻量模型配置（已废弃，由MODEL_ROUTES替代）\n"
            " - enabled: 是否启用\n"
            " - provider: 供应商\n"
            " - name: 模型名"
        ),
        default_value={
            "enabled": False,
            "provider": None,
            "name": None,
        },
        type=dict,
    ),
    # ===== 主模型策略 =====
    RegisterConfig(
        key="STRICT_MAIN_MODEL",
        value=False,
        module=MODULE,
        help="是否严格使用主模型不降级",
        default_value=False,
        type=bool,
    ),
    RegisterConfig(
        key="MONTHLY_TOKEN_QUOTA",
        value=0,
        module=MODULE,
        help="月度token额度（0=不限）",
        default_value=0,
        type=int,
    ),
    # ===== 用户对话Token额度 =====
    RegisterConfig(
        key="TOKEN_QUOTA",
        value={
            "enabled": True,
            "reminder_cd": 300,
            "min_threshold": 1,
        },
        module=MODULE,
        help=(
            "用户对话token额度配置\n"
            " - enabled: 是否启用额度限制\n"
            " - reminder_cd: 额度不足提醒冷却（秒）\n"
            " - min_threshold: 可用token最低阈值"
        ),
        default_value={
            "enabled": True,
            "reminder_cd": 300,
            "min_threshold": 1,
        },
        type=dict,
    ),
    # ===== 模型按角色路由 =====
    RegisterConfig(
        key="MODEL_ROUTES",
        value={
            "intent": {
                "model": None,
                "provider": None,
                "temperature": 0.1,
            },
            "review": {
                "model": None,
                "provider": None,
                "temperature": 0.1,
            },
            "agent": {
                "model": None,
                "provider": None,
                "temperature": 0.3,
            },
            "sticker": {
                "model": None,
                "provider": None,
                "temperature": 0.4,
            },
            "warmup": {
                "model": None,
                "provider": None,
                "temperature": 0.7,
            },
        },
        module=MODULE,
        help=(
            "模型按角色路由配置\n"
            "每个角色可独立指定 model/provider/temperature\n"
            "model为None时回退到CHAT_MODEL.model\n"
            "provider为None时回退到CHAT_MODEL.provider\n"
            "跨供应商使用模型时必须配置provider\n"
            " - intent: 意图推断（低温度0.1）\n"
            " - review: 响应审查（低温度0.1）\n"
            " - agent: Agent工具调用（中温度0.3）\n"
            " - sticker: 贴纸选择（中温度0.4）\n"
            " - warmup: 预热任务（高温度0.7）"
        ),
        default_value={
            "intent": {
                "model": None,
                "provider": None,
                "temperature": 0.1,
            },
            "review": {
                "model": None,
                "provider": None,
                "temperature": 0.1,
            },
            "agent": {
                "model": None,
                "provider": None,
                "temperature": 0.3,
            },
            "sticker": {
                "model": None,
                "provider": None,
                "temperature": 0.4,
            },
            "warmup": {
                "model": None,
                "provider": None,
                "temperature": 0.7,
            },
        },
        type=dict,
    ),
    # ===== AI CLI路由降级 =====
    RegisterConfig(
        key="AI_CLI",
        value={
            "enabled": False,
            "routes": "",
        },
        module=MODULE,
        help=(
            "CLI路由降级配置（HTTP provider全部失败时尝试CLI工具）\n"
            " - enabled: 是否启用\n"
            ' - routes: CLI路由列表JSON（如[{"name":"gemini_cli",'
            '"command":["gemini"],"use_stdin":true,"timeout":30,"priority":1}]）'
        ),
        default_value={"enabled": False, "routes": ""},
        type=dict,
    ),
]
"""LLM相关配置项列表"""
