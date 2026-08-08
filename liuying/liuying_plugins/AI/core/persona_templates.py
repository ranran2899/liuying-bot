"""人格配置辅助工具

提供好感度态度映射与人格描述提取能力。
场景化提示模板已内联到各消费方代码模块，
本模块不再集中管理模板渲染逻辑。
"""

__all__ = [
    "FAVOR_ATTITUDES",
    "extract_persona_desc",
]


FAVOR_ATTITUDES: dict[str, str] = {
    "陌生": "礼貌但保持距离，不主动套近乎",
    "初识": "友好但不过分亲近，保持基本礼貌",
    "熟悉": "可以自然交流，偶尔开玩笑",
    "友好": "态度温和，愿意帮助对方",
    "信任": "像朋友一样自然，可以分享日常",
    "亲密": "关系很好，可以聊更多话题",
    "挚友": "像老朋友一样自然，可以畅所欲言",
    "至交": "非常亲密，可以分享内心想法",
    "知己": "心灵相通，可以深入交流",
    "恋人": "温柔亲密，主动表达关心和爱意",
}
"""好感度态度档"""


def extract_persona_desc(persona: dict) -> str:
    """从人格配置提取简短描述

    优先使用 description 字段；未配置时回退到从 system_prompt
    提取首行有效内容。

    参数:
        persona: 人格配置字典

    返回:
        str: 简短描述（不超过80字）
    """
    desc = persona.get("description") or ""
    if isinstance(desc, str) and desc.strip():
        return desc.strip()[:80]
    prompt = persona.get("system_prompt", "")
    if not prompt:
        return ""
    first_line = ""
    for line in prompt.split("\n"):
        line = line.strip()
        _skip = ("姓名", "年龄", "性别")
        if line and not any(line.startswith(s) for s in _skip):
            first_line = line
            break
    if not first_line:
        first_line = prompt.strip().split("\n")[0].strip()
    return first_line[:80]
