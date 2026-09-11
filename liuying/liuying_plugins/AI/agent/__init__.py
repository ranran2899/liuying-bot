"""Agent 智能体循环

提供规划-执行-响应三层分离的 Agent 核心循环（runner/runtime）、
MCP 协议桥（mcp/）与各辅助LLM分析模块（情绪/记忆/画像/门控/
主动学习/检索改写/贴纸语义，按角色前缀命名）。

工具系统已独立为插件根目录的 AI/tools 包（注册表/装饰器/内置工具），
本包不再导出工具系统符号，需要时直接
``from liuying.liuying_plugins.AI.tools import ...``。

本包不提供急切聚合导出：runner 链会拉起 core.memory 等重依赖，
而 core.memory.manager 需反向导入本包的记忆演化模块，
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
