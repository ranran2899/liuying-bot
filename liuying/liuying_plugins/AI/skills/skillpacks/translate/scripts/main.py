"""翻译技能入口"""

from typing import Any

from . import impl


async def run(
    text: str, target_language: str = "简体中文"
) -> str:
    """CLI调试入口

    参数:
        text: 待翻译文本
        target_language: 目标语言

    返回:
        str: 译文
    """
    return await impl.translate(
        text=text, target_language=target_language
    )


def build_tools(runtime: Any) -> list:
    """生产入口，由loader调用

    参数:
        runtime: SkillRuntime 实例

    返回:
        list: AgentTool 列表
    """
    return [impl.build_translate_tool(runtime)]
