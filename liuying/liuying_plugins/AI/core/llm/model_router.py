"""模型按角色路由

按功能角色（意图推断/响应审查/Agent工具/贴纸选择/预热任务）
路由到不同的模型与温度配置，实现精细化模型管理。

角色定义：
- intent:  意图推断（低温度，需要确定性）
- review:  响应审查（低温度，需要严谨判断）
- agent:   统一 ReAct 循环工具编排阶段（只做工具决策与收束，
  不写正文，中温度）
- sticker: 贴纸选择（中温度，需要语义理解）
- warmup:  预热任务（高温度，用于主动发言等创意场景）
- chat:    常规对话（默认角色，回退到 CHAT_MODEL），
  正文（人格回复）统一由本角色生成

未配置角色模型时，自动回退到 CHAT_MODEL，保证向后兼容。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ...config import get_config

__all__ = [
    "ROLE_AGENT",
    "ROLE_CHAT",
    "ROLE_INTENT",
    "ROLE_REVIEW",
    "ROLE_STICKER",
    "ROLE_WARMUP",
    "LLMRole",
    "ModelRole",
    "ModelRouter",
    "model_router",
]


class LLMRole(StrEnum):
    """模型功能角色枚举

    以字符串枚举统一角色标识，消除裸串拼写风险；成员即 str，
    与配置中的字符串键、旧代码中的 ROLE_* 常量完全兼容。
    """

    INTENT = "intent"
    REVIEW = "review"
    AGENT = "agent"
    STICKER = "sticker"
    WARMUP = "warmup"
    CHAT = "chat"


ROLE_INTENT = LLMRole.INTENT
"""意图推断角色"""

ROLE_REVIEW = LLMRole.REVIEW
"""响应审查角色"""

ROLE_AGENT = LLMRole.AGENT
"""统一 ReAct 循环工具编排阶段角色（只做工具决策与收束，不写正文）"""

ROLE_STICKER = LLMRole.STICKER
"""贴纸选择角色"""

ROLE_WARMUP = LLMRole.WARMUP
"""预热任务角色"""

ROLE_CHAT = LLMRole.CHAT
"""常规对话角色（默认，正文由此角色生成）"""

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

        对配置异常（非dict/None/非法数值）做防御性处理，
        保证任何配置形态下都返回有效的 ModelRole。

        参数:
            role: 角色名（ROLE_INTENT/ROLE_REVIEW/ROLE_AGENT/
                ROLE_STICKER/ROLE_WARMUP/ROLE_CHAT）

        返回:
            ModelRole: 模型角色配置
        """
        # 嵌套配置：MODEL_ROUTES 为按角色分组的字典
        routes = get_config("MODEL_ROUTES", {})
        role_config = (
            routes.get(role, {}) if isinstance(routes, dict) else {}
        )
        if not isinstance(role_config, dict):
            role_config = {}

        # CHAT_MODEL 同样防御非 dict 形态
        chat_model_cfg = get_config("CHAT_MODEL", {})
        if not isinstance(chat_model_cfg, dict):
            chat_model_cfg = {}

        # 角色专属 model/provider 未配置（None/空串）时回退到 CHAT_MODEL
        model = str(
            role_config.get("model")
            or chat_model_cfg.get("model")
            or ""
        )
        provider = str(
            role_config.get("provider")
            or chat_model_cfg.get("provider")
            or ""
        )

        # temperature 防御 None/非法值，回退到角色默认温度
        default_temp = _DEFAULT_TEMPERATURES.get(role, 0.6)
        try:
            temperature = float(
                role_config.get("temperature", default_temp)
            )
        except (TypeError, ValueError):
            temperature = default_temp

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
