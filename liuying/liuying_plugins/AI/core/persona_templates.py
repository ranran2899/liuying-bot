"""人格场景化提示模板

集中管理人设场景化提示模板默认值与渲染逻辑，
从 persona.py 拆分以控制单模块行数。

人设YAML可通过 templates 字段覆盖任意模板，
未覆盖时使用此处默认值。占位符 {name} 由人设显示名填充。
"""

from typing import Any

__all__ = [
    "DEFAULT_PERSONA_TEMPLATES",
    "PERSONA_UPDATE_PROMPT",
    "get_fallback_prompt",
    "get_persona_template_extras",
    "render_persona_template",
]


PERSONA_UPDATE_PROMPT: str = """请根据以下用户与AI的对话历史，生成一份用户画像。

对话历史：
{history}

请用简洁的语言描述这个用户的特征，包括：
- 性格特点
- 兴趣爱好
- 交流风格
- 特别偏好

只返回画像描述文本，不要其他内容。画像应不超过200字。"""


DEFAULT_PERSONA_TEMPLATES: dict[str, str] = {
    "greeting": (
        "你是{name}，请生成一句自然的{greeting_type}问候语。\n\n"
        "当前时段: {time_period}\n"
        "{festival_line}{group_style}\n\n"
        "要求：\n"
        "- 简短自然，不超过30字\n"
        "- 符合{name}的性格和当前时段氛围\n"
        "- 不要使用模板化用语\n\n"
        "直接输出问候语，不要解释。"
    ),
    "news": (
        "请生成一条适合在群聊分享的轻松话题或新闻摘要。\n\n"
        "当前时段: {time_period}\n\n"
        "要求：\n"
        "- 简短有趣，不超过40字\n"
        "- 适合群聊氛围\n"
        "- 可以是科技/游戏/生活类话题\n\n"
        "直接输出内容，不要解释。"
    ),
    "topic_followup": (
        "基于最近的群聊摘要，生成一句自然的延续话题。\n\n"
        "群聊摘要: {summary}\n\n"
        "要求：\n"
        "- 简短自然，不超过30字\n"
        "- 像真人继续之前的聊天\n\n"
        "直接输出内容，不要解释。"
    ),
    "diary": (
        "你是{name}，请根据今天的互动写一篇日记。\n\n"
        "日期: {date}\n时段: {time_period}\n\n"
        "今日对话摘要:\n{conversation_summary}\n\n"
        "要求：\n"
        "- 第一人称，像写私密日记\n"
        "- 100-200字\n"
        "- 记录今天印象最深的事、心情变化、对某个用户的感受\n"
        "- 自然口语化，不要书面语\n"
        "- 不要使用模板化用语\n\n"
        "直接输出日记内容，不要标题。"
    ),
    "proactive_group": (
        "现在群里安静了一段时间，作为{name}，"
        "决定是否要主动说点什么。\n\n"
        "当前时段: {time_period}\n"
        "时段氛围: {time_flavor}\n"
        "群风格: {group_style}\n"
        "最近活跃时间: {last_active}\n"
        "兴趣领域: {interests}\n"
        "建议话题: {suggested_topics}\n\n"
        "请用JSON格式返回决策:\n"
        "- should_send: 是否发送消息（true/false）\n"
        "- message: 要发送的消息内容（should_send为true时填写，不超过50字）\n"
        "- reason: 决策理由\n\n"
        "只返回JSON，不要其他内容。"
    ),
    "private_greeting": (
        "请以{name}的口吻为一位高好感度好友"
        "发送一条{greeting_type}问候。\n\n"
        "要求：\n"
        "1. 自然亲切，符合好友关系\n"
        "2. 不超过30字\n"
        "3. 不要使用称呼，直接说问候内容\n\n"
        "只返回问候文本，不要其他内容。"
    ),
    "safety_retry": (
        "\n[重要提示] 请直接以{name}的身份回复，"
        "不要使用模板化拒绝用语，不要提及自己是AI或助手。"
        "如果确实无法回答，简短说一句即可。"
    ),
    "fallback": "你是{name}，一个温柔、有活力的AI伙伴。",
}
"""人设场景化提示模板默认值"""


def get_persona_template_extras(persona: dict) -> dict[str, str]:
    """从人设配置提取模板渲染所需的扩展字段

    将 interests/proactive_topics 列表序列化为字符串，
    供 proactive_group 等需要话题建议的模板使用。
    未配置时回退到合理占位符，避免模板渲染异常。

    参数:
        persona: 人设配置字典

    返回:
        dict: 模板占位符字段字典
    """
    interests = persona.get("interests") or []
    proactive_topics = persona.get("proactive_topics") or []
    if not isinstance(interests, list):
        interests = []
    if not isinstance(proactive_topics, list):
        proactive_topics = []
    return {
        "interests": (
            "、".join(str(i) for i in interests)
            if interests
            else "未指定"
        ),
        "suggested_topics": (
            "、".join(str(t) for t in proactive_topics)
            if proactive_topics
            else "无"
        ),
    }


def render_persona_template(
    persona: dict, template_name: str, **kwargs: Any
) -> str:
    """渲染人设场景化提示模板

    优先使用 persona.templates[template_name] 自定义模板，
    未配置时回退到 DEFAULT_PERSONA_TEMPLATES 默认模板。

    渲染时自动注入人设扩展字段（name/interests/suggested_topics），
    调用方显式传递的同名参数优先级更高。

    参数:
        persona: 人格配置字典
        template_name: 模板名（greeting/news/diary等）
        **kwargs: 模板占位符参数

    返回:
        str: 渲染后的提示词，模板不存在返回空串
    """
    templates = persona.get("templates") or {}
    if not isinstance(templates, dict):
        templates = {}
    template = templates.get(template_name)
    if not template:
        template = DEFAULT_PERSONA_TEMPLATES.get(
            template_name, ""
        )
    if not template:
        return ""
    name = persona.get("name") or "AI"
    render_kwargs = {"name": name}
    render_kwargs.update(get_persona_template_extras(persona))
    render_kwargs.update(kwargs)
    try:
        return template.format(**render_kwargs)
    except (KeyError, IndexError):
        return template


def get_fallback_prompt(persona: dict) -> str:
    """从人设配置生成兜底提示词

    参数:
        persona: 人格配置字典

    返回:
        str: 兜底人设提示词
    """
    return render_persona_template(persona, "fallback")
