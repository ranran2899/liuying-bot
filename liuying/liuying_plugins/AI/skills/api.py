"""技能包运行时API

SkillRuntime 是纯数据容器，作为依赖注入载体将主插件服务传递给技能包。
技能包通过 runtime 字段访问主插件的 LLM/记忆/知识库/配置等服务，
而非直接导入全局单例，实现松耦合。
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = ["SkillRuntime"]


@dataclass(slots=True)
class SkillRuntime:
    """技能包运行时

    依赖注入载体，由主插件在启动期构造并传递给技能包的 build_tools(runtime)。
    技能包通过本对象访问主插件服务，不直接导入全局单例。

    Attributes:
        plugin_config: 配置读取回调 get_config(key, default)
        logger: 日志器实例
        get_now: 获取当前本地时间的回调
        llm_helper: LLM助手实例（对话/嵌入/TTS/图片/搜索）
        memory_manager: 记忆管理器实例（召回/巩固/进化）
        knowledge_base: 插件知识库实例（本地SQLite）
        persona_manager: 人格管理器实例（人格切换/system_prompt构建）
        data_dir: 数据目录路径
        scheduler: 定时任务调度器
        get_bots: 获取所有bot实例的回调
    """

    plugin_config: Callable[..., Any]
    logger: Any
    get_now: Callable[[], datetime]
    llm_helper: Any | None = None
    memory_manager: Any | None = None
    knowledge_base: Any | None = None
    persona_manager: Any | None = None
    data_dir: Any | None = None
    scheduler: Any | None = None
    get_bots: Callable[[], dict[str, Any]] | None = None

    def config(self, key: str, default: Any = None) -> Any:
        """读取插件配置

        参数:
            key: 配置键
            default: 默认值

        返回:
            Any: 配置值
        """
        return self.plugin_config(key, default)
