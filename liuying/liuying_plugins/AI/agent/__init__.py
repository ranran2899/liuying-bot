"""Agent 智能体循环

提供统一 ReAct 循环入口（runner/runtime）、主动学习（learning）、
社交门控（review/）与贴纸语义分析（sticker/）。
情绪、群风格、记忆巩固/进化/检索改写等核心服务
已回归 core/（emotion/group.profile/memory）。

工具系统已独立为插件根目录的 AI/tools 包（注册表/装饰器/内置工具），
本包不再导出工具系统符号，需要时直接
``from liuying.liuying_plugins.AI.tools import ...``。

本包不提供急切聚合导出：runner 链会拉起 pipeline/core 重依赖，
惰性导出可保证任意加载顺序均无循环导入。
"""

from importlib import import_module

_LAZY_EXPORTS: dict[str, str] = {
    "AgentResult": "runner",
    "AgentRunner": "runner",
}
"""惰性导出符号 → 所属子模块名"""

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str):
    """PEP 562 惰性导出：按需加载子模块后返回符号"""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
