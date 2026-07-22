"""模型按角色路由

按功能角色（意图推断/响应审查/Agent工具/贴纸选择/预热任务）
路由到不同的模型与温度配置，实现精细化模型管理。

角色定义：
- intent:  意图推断（低温度，需要确定性）
- review:  响应审查（低温度，需要严谨判断）
- agent:   Agent工具调用（中温度，平衡创造与准确）
- sticker: 贴纸选择（中温度，需要语义理解）
- warmup:  预热任务（高温度，用于主动发言等创意场景）
- chat:    常规对话（默认角色，回退到 CHAT_MODEL）

未配置角色模型时，自动回退到 CHAT_MODEL，保证向后兼容。
"""

from dataclasses import dataclass
from typing import Any

from ...config import get_config

__all__ = [
    "ROLE_AGENT",
    "ROLE_CHAT",
    "ROLE_INTENT",
    "ROLE_REVIEW",
    "ROLE_STICKER",
    "ROLE_WARMUP",
    "ModelRole",
    "ModelRouter",
    "model_router",
]

ROLE_INTENT = "intent"
"""意图推断角色"""

ROLE_REVIEW = "review"
"""响应审查角色"""

ROLE_AGENT = "agent"
"""Agent工具调用角色"""

ROLE_STICKER = "sticker"
"""贴纸选择角色"""

ROLE_WARMUP = "warmup"
"""预热任务角色"""

ROLE_CHAT = "chat"
"""常规对话角色（默认）"""

_DEFAULT_TEMPERATURES: dict[str, float] = {
    ROLE_INTENT: 0.1,
    ROLE_REVIEW: 0.1,
    ROLE_AGENT: 0.3,
    ROLE_STICKER: 0.4,
    ROLE_WARMUP: 0.7,
    ROLE_CHAT: 0.6,
}
"""各角色默认温度"""


@dataclass(slots=True)
class ModelRole:
    """模型角色配置

    Attributes:
        model: 模型名（空串表示用默认 CHAT_MODEL）
        temperature: 温度参数
        provider: 指定provider名（空串表示用默认）
    """

    model: str = ""
    temperature: float = 0.6
    provider: str = ""

    def apply_to_options(
        self, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """将角色配置应用到LLM调用options

        参数:
            options: 原始options，None时创建新字典

        返回:
            dict: 合并后的options
        """
        merged: dict[str, Any] = dict(options) if options else {}
        if "temperature" not in merged:
            merged["temperature"] = self.temperature
        return merged


class ModelRouter:
    """模型按角色路由器

    按角色查询对应的模型名、温度与provider配置。
    未配置角色模型时回退到 CHAT_MODEL / CHAT_PROVIDER。
    """

    def resolve(self, role: str) -> ModelRole:
        """解析角色对应的模型配置

        参数:
            role: 角色名（ROLE_INTENT/ROLE_REVIEW/ROLE_AGENT/
                ROLE_STICKER/ROLE_WARMUP/ROLE_CHAT）

        返回:
            ModelRole: 模型角色配置
        """
        model_key = f"MODEL_{role.upper()}"
        temp_key = f"MODEL_{role.upper()}_TEMPERATURE"
        provider_key = f"MODEL_{role.upper()}_PROVIDER"

        # 角色专属模型未配置时回退到 CHAT_MODEL
        model = str(
            get_config(model_key, "")
            or get_config("CHAT_MODEL", "")
            or ""
        )
        temperature = float(
            get_config(temp_key, _DEFAULT_TEMPERATURES.get(role, 0.6))
        )
        provider = str(
            get_config(provider_key, "")
            or get_config("CHAT_PROVIDER", "")
            or ""
        )
        return ModelRole(
            model=model, temperature=temperature, provider=provider
        )

    def resolve_chat(self) -> ModelRole:
        """解析常规对话角色配置

        返回:
            ModelRole: 常规对话模型配置
        """
        return self.resolve(ROLE_CHAT)


model_router = ModelRouter()
"""模型按角色路由器单例"""
