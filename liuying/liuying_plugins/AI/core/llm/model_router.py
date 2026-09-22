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
- chat:    对话主模型（默认角色，正文统一由本角色生成），
  也是其余角色缺省时的回退基准

未配置角色模型/provider 时，自动回退到 MODEL_ROUTES 的 chat 角色。
"""

from dataclasses import dataclass, field
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
    "ModelCapability",
    "ModelRole",
    "ModelRouter",
    "declared_capabilities",
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


class ModelCapability(StrEnum):
    """模型级能力标识

    MODEL_ROUTES 各角色 capabilities 字段的推荐词表，用于统一
    声明"某个模型能做什么"（看图、function-calling 等）。仅作
    声明与解析之用，不改变各调用链路的既有行为。
    """

    VISION = "vision"
    """看图/多模态输入能力"""

    TOOLS = "tools"
    """原生 function-calling 工具调用能力"""


_DEFAULT_TEMPERATURES: dict[str, float] = {
    ROLE_INTENT: 0.1,
    ROLE_REVIEW: 0.1,
    ROLE_AGENT: 0.3,
    ROLE_STICKER: 0.4,
    ROLE_WARMUP: 0.7,
    ROLE_CHAT: 0.6,
}
"""各角色默认温度"""

_VALID_EFFORTS = frozenset({"max", "high", "low"})
"""深度思考合法强度：max（深度推理）/ high（增强推理）/ low（轻度推理）"""

_REASONING_OPTION_KEY = "_reasoning"
"""角色思考意图随 options 透传给 helper 的保留键（发给 provider 前剥离）"""


@dataclass(slots=True)
class ModelRole:
    """模型角色配置

    Attributes:
        model: 模型名（空串表示回退到 chat 角色）
        temperature: 温度参数
        provider: 指定provider名（空串表示回退到 chat 角色）
        capabilities: 声明该模型支持的能力集合（统一词表见
            ModelCapability），如 ["vision", "tools"]；空列表
            表示未声明，具体能力判定回退到各自的启发式方式
        reasoning: 该角色是否使用深度思考
        reasoning_effort: 思考强度（max/high/low）
    """

    model: str = ""
    temperature: float = 0.6
    provider: str = ""
    capabilities: list[str] = field(default_factory=list)
    reasoning: bool = False
    reasoning_effort: str = "high"

    def supports(self, capability: str) -> bool:
        """判断本角色模型是否声明了某能力

        参数:
            capability: 能力标识（ModelCapability 成员或其字符串值）

        返回:
            bool: capabilities 中是否包含该能力
        """
        wanted = str(capability).lower()
        return any(str(c).lower() == wanted for c in self.capabilities)

    def apply_to_options(
        self, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """将角色配置应用到LLM调用options

        附带本角色的深度思考意图（保留键 _reasoning），由 helper
        按 provider 家族转成原生参数并在发给 provider 前剥离。

        参数:
            options: 原始options，None时创建新字典

        返回:
            dict: 合并后的options
        """
        merged: dict[str, Any] = dict(options) if options else {}
        merged.setdefault("temperature", self.temperature)
        merged[_REASONING_OPTION_KEY] = {
            "enabled": self.reasoning,
            "effort": self.reasoning_effort,
        }
        return merged


class ModelRouter:
    """模型按角色路由器

    按角色查询对应的模型名、温度、provider、能力与深度思考配置。
    未配置角色模型时回退到 MODEL_ROUTES 的 chat 角色。
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
        if not isinstance(routes, dict):
            routes = {}
        role_config = routes.get(role) or {}
        if not isinstance(role_config, dict):
            role_config = {}
        # chat 角色是对话主模型，也是其余角色 model/provider 的回退基准
        chat_config = routes.get("chat") or {}
        if not isinstance(chat_config, dict):
            chat_config = {}

        # 角色专属 model/provider 未配置（None/空串）时回退到 chat 角色
        model = str(
            role_config.get("model") or chat_config.get("model") or ""
        )
        provider = str(
            role_config.get("provider")
            or chat_config.get("provider")
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

        # capabilities 防御非 list 形态，非声明时保持空列表
        raw_capabilities = role_config.get("capabilities", [])
        capabilities = (
            [str(c) for c in raw_capabilities]
            if isinstance(raw_capabilities, list)
            else []
        )

        # reasoning 防御非 dict 形态；effort 非法值回退 high
        reasoning_cfg = role_config.get("reasoning")
        if not isinstance(reasoning_cfg, dict):
            reasoning_cfg = {}
        reasoning = bool(reasoning_cfg.get("enabled", False))
        raw_effort = str(
            reasoning_cfg.get("effort", "high") or ""
        ).strip().lower()
        reasoning_effort = raw_effort if raw_effort in _VALID_EFFORTS else "high"

        return ModelRole(
            model=model,
            temperature=temperature,
            provider=provider,
            capabilities=capabilities,
            reasoning=reasoning,
            reasoning_effort=reasoning_effort,
        )

    def resolve_chat(self) -> ModelRole:
        """解析常规对话角色配置

        返回:
            ModelRole: 常规对话模型配置
        """
        return self.resolve(ROLE_CHAT)


def declared_capabilities(model: str) -> set[str] | None:
    """汇总 MODEL_ROUTES 中对指定模型显式声明的能力集合

    按模型名匹配任一角色路由的 capabilities 声明，作为"模型能力"
    的集中判定入口，供视觉路由、能力自述诊断等统一复用。

    参数:
        model: 模型名

    返回:
        set[str] | None: 归一化小写的能力集合；None 表示该模型未
            被任何角色显式声明能力（调用方应回退到启发式判定）
    """
    if not model:
        return None
    routes = get_config("MODEL_ROUTES", {})
    if not isinstance(routes, dict):
        return None
    model_lower = model.lower()
    declared: set[str] | None = None
    for role_config in routes.values():
        if not isinstance(role_config, dict):
            continue
        if str(role_config.get("model") or "").lower() != model_lower:
            continue
        capabilities = role_config.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            continue
        if declared is None:
            declared = set()
        declared.update(str(c).lower() for c in capabilities)
    return declared


model_router = ModelRouter()
"""模型按角色路由器单例"""
