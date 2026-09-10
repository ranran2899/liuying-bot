"""技能包运行时API

SkillRuntime 是纯数据容器，作为依赖注入载体将主插件服务传递给技能包。
技能包通过 runtime 字段访问主插件的 LLM 服务，
而非直接导入全局单例，实现松耦合。
"""

from dataclasses import dataclass
from typing import Any

__all__ = ["SkillRuntime"]


@dataclass(slots=True)
class SkillRuntime:
    """技能包运行时

    依赖注入载体，由主插件在启动期构造并传递给技能包的 build_tools(runtime)。
    技能包通过本对象访问主插件服务，不直接导入全局单例。

    Attributes:
        llm_helper: LLM助手实例（对话/嵌入/TTS/图片/搜索）
        memory_manager: 记忆管理器实例（用户画像/事实存取）
    """

    llm_helper: Any | None = None
    memory_manager: Any | None = None
