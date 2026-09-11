"""多语翻译实现

用低温度的独立 LLM 调用做翻译，与主对话解耦，
避免翻译要求污染人格提示词导致回复风格漂移。
"""

from typing import Any

from liuying.liuying_plugins.AI.agent.runtime.constants import (
    EVIDENCE_KIND_TOOL,
    INTENT_TAG_NETWORK,
    LATENCY_CLASS_NETWORK,
)
from liuying.liuying_plugins.AI.core.llm.model_router import (
    ROLE_AGENT,
    model_router,
)
from liuying.liuying_plugins.AI.tools import AgentTool

_MAX_TEXT_LENGTH = 1500
"""单次翻译文本上限，超出截断以控制token"""

_TRANSLATE_TEMPERATURE = 0.2
"""翻译温度，取低值保证稳定"""

_LANG_ALIASES: dict[str, str] = {
    "中文": "简体中文",
    "zh": "简体中文",
    "汉语": "简体中文",
    "繁体": "繁体中文",
    "英文": "英语",
    "en": "英语",
    "日文": "日语",
    "ja": "日语",
    "韩文": "韩语",
    "ko": "韩语",
    "法文": "法语",
    "德文": "德语",
    "俄文": "俄语",
}
"""目标语言别名归一化表"""

_SYSTEM_PROMPT = (
    "你是专业翻译。严格遵守：\n"
    "1. 只输出译文，不要解释、不要标注原文、不要加引号\n"
    "2. 保留原文的换行与列表结构\n"
    "3. 人名、品牌、代码标识符保持原样不译\n"
    "4. 网络用语按目标语言的同类口语表达来译，不要直译字面"
)
"""翻译系统提示"""


def normalize_language(target: str) -> str:
    """归一化目标语言名

    参数:
        target: 用户或模型给出的语言名

    返回:
        str: 规范语言名，空输入返回简体中文
    """
    text = (target or "").strip()
    if not text:
        return "简体中文"
    return _LANG_ALIASES.get(text.lower(), _LANG_ALIASES.get(text, text))


async def translate(
    text: str,
    target_language: str = "简体中文",
    llm_helper: Any = None,
) -> str:
    """翻译文本

    参数:
        text: 待翻译文本
        target_language: 目标语言
        llm_helper: LLM助手实例

    返回:
        str: 译文，或不可用原因说明
    """
    if llm_helper is None:
        return "翻译不可用：未配置LLM助手"
    content = (text or "").strip()
    if not content:
        return "请提供要翻译的文本"
    if len(content) > _MAX_TEXT_LENGTH:
        content = content[:_MAX_TEXT_LENGTH]

    language = normalize_language(target_language)
    # LLM 调用属外部不确定性，失败需降级为可读提示而非中断 Agent 循环。
    try:
        role = model_router.resolve(ROLE_AGENT)
        result = await llm_helper.chat_text(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"翻译成{language}：\n{content}",
                },
            ],
            model=role.model or None,
            options=role.apply_to_options(
                {"temperature": _TRANSLATE_TEMPERATURE}
            ),
            provider_name=role.provider or None,
        )
    except Exception as e:
        return f"翻译失败: {type(e).__name__}"

    result = (result or "").strip()
    return result or "翻译结果为空，请重试"


def build_translate_tool(runtime: Any) -> AgentTool:
    """构建翻译工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: 翻译工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(
        text: str, target_language: str = "简体中文"
    ) -> str:
        """翻译handler

        参数:
            text: 待翻译文本
            target_language: 目标语言

        返回:
            str: 译文
        """
        return await translate(
            text=text,
            target_language=target_language,
            llm_helper=llm_helper,
        )

    return AgentTool(
        name="translate_text",
        description=(
            "将文本翻译成指定语言。用户明确要求翻译、"
            "或需要理解外语原文含义时调用"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "待翻译的原文",
                },
                "target_language": {
                    "type": "string",
                    "description": (
                        "目标语言，如 简体中文/英语/日语，"
                        "默认简体中文"
                    ),
                },
            },
            "required": ["text"],
        },
        func=_handler,
        intent_tags=[INTENT_TAG_NETWORK],
        latency_class=LATENCY_CLASS_NETWORK,
        requires_network=True,
        evidence_kind=EVIDENCE_KIND_TOOL,
    )
