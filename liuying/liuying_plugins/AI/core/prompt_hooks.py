"""提示词钩子注册表

按 phase + priority 执行提示词注入钩子，支持热插拔。
单个钩子异常时静默降级，不影响其它钩子。

支持5个phase：
- preprocess: 预处理阶段
- system_prelude: 系统提示词前奏
- system_context: 系统提示词上下文
- system_postlude: 系统提示词后奏
- message: 消息构建阶段
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from liuying.utils.log import logger

__all__ = [
    "HookContext",
    "PromptHookRegistry",
    "get_hook_registry",
    "register_prompt_hook",
]


HookPhase = Literal[
    "preprocess",
    "system_prelude",
    "system_context",
    "system_postlude",
    "message",
]
"""钩子阶段类型"""


PromptHook = Callable[
    ["HookContext"], Awaitable[str | None]
]
"""钩子函数类型"""


@dataclass(slots=True)
class HookContext:
    """提示词注入钩子的上下文快照

    允许钩子在不触碰 reply_processor 细节的情况下读取状态。

    Attributes:
        user_id: 用户ID
        group_id: 群组ID
        is_private: 是否私聊
        message_text: 消息文本
        has_image_input: 是否有图片输入
        current_time_str: 当前时间字符串
        persona_name: 人格名称
        extra: 额外数据字典
    """

    user_id: str = ""
    group_id: str = ""
    is_private: bool = False
    message_text: str = ""
    has_image_input: bool = False
    current_time_str: str = ""
    persona_name: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _HookEntry:
    """钩子注册条目

    Attributes:
        name: 钩子名称
        hook: 钩子函数
        priority: 优先级（越小越先执行）
        phase: 钩子阶段
    """

    name: str
    hook: PromptHook
    priority: int
    phase: HookPhase = "system_context"


class PromptHookRegistry:
    """全局提示词注入钩子注册表

    按 phase + priority 执行钩子。
    单个钩子异常时静默降级，不影响其它钩子。
    """

    def __init__(self) -> None:
        """初始化钩子注册表"""
        self._entries: list[_HookEntry] = []

    def register(
        self,
        name: str,
        hook: PromptHook,
        priority: int = 50,
        phase: HookPhase = "system_context",
    ) -> None:
        """注册一个提示词钩子

        参数:
            name: 钩子名称
            hook: 钩子函数
            priority: 优先级（越小越先执行）
            phase: 钩子阶段
        """
        self._entries.append(
            _HookEntry(
                name=name,
                hook=hook,
                priority=priority,
                phase=phase,
            )
        )
        self._entries.sort(
            key=lambda e: (e.phase, e.priority, e.name)
        )

    async def run_all(
        self,
        ctx: HookContext,
        *,
        phase: HookPhase = "system_context",
    ) -> list[str]:
        """执行指定阶段的所有钩子

        参数:
            ctx: 钩子上下文
            phase: 钩子阶段

        返回:
            list[str]: 钩子返回的非空文本列表
        """
        results: list[str] = []
        for entry in self._entries:
            if entry.phase != phase:
                continue
            try:
                chunk = await entry.hook(ctx)
                if chunk and chunk.strip():
                    results.append(chunk.strip())
            except Exception as e:
                logger.warning(
                    f"提示词钩子 '{entry.name}' "
                    f"执行失败: {e}",
                    command="AI",
                    e=e,
                )
        return results


_registry = PromptHookRegistry()
"""全局钩子注册表单例"""


def get_hook_registry() -> PromptHookRegistry:
    """获取全局钩子注册表

    返回:
        PromptHookRegistry: 钩子注册表
    """
    return _registry


def register_prompt_hook(
    name: str,
    hook: PromptHook,
    priority: int = 50,
    phase: HookPhase = "system_context",
) -> None:
    """注册一个提示词钩子到全局注册表

    参数:
        name: 钩子名称
        hook: 钩子函数
        priority: 优先级（越小越先执行）
        phase: 钩子阶段
    """
    _registry.register(
        name, hook, priority=priority, phase=phase
    )
