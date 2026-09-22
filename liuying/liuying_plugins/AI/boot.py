"""AI插件运行期启动引导

把运行资源引导（知识库/定时任务/技能包/远程工具）与 matcher
注册分离：插件启动钩子调用一次 ensure_ai_ready；管理员在运行期
打开总开关后再次调用即可补挂定时任务与技能包，无需重启。
幂等：重复调用只生效一次。
"""

from liuying.utils.log import logger

from .config import get_config
from .core.knowledge_index import knowledge_base
from .core.llm import llm_helper
from .core.memory import memory_manager
from .core.runtime import Feature, runtime_switch
from .jobs import setup_jobs
from .skills import SkillRuntime, skill_loader
from .tools.external import smart_tool_bridge

_ai_ready = False
"""运行资源是否已完成引导（幂等标记）"""


async def ensure_ai_ready() -> bool:
    """确保AI运行资源已引导（幂等）

    总开关关闭时不动作返回 False；否则依次完成知识库初始化、
    定时任务注册与技能包/MCP/智能工具挂载，重复调用直接返回。

    返回:
        bool: 运行是否就绪（总开关开启且已完成引导）
    """
    global _ai_ready
    if not runtime_switch.is_enabled(Feature.AI):
        return False
    if _ai_ready:
        return True

    await knowledge_base.init()
    logger.info(
        "AI插件初始化完成，"
        f"默认人格: {get_config('DEFAULT_PERSONA', 'liuying')}",
        command="AI",
    )

    await setup_jobs()

    # 显式注入主插件服务给技能包（LLM助手 + 记忆管理器）
    runtime = SkillRuntime(
        llm_helper=llm_helper,
        memory_manager=memory_manager,
    )
    tool_count = skill_loader.register_all(runtime=runtime)
    logger.debug(f"AI技能包已加载，注册工具{tool_count}个", command="AI")

    # 注册MCP远程工具（涉及子进程通信，需在异步上下文中执行）
    mcp_count = await skill_loader.register_mcp_tools()
    if mcp_count:
        logger.debug(f"MCP远程工具已注册{mcp_count}个", command="AI")

    # 注册本体插件声明的智能模式函数工具（smart_tools桥接）
    smart_count = smart_tool_bridge.register_all()
    if smart_count:
        logger.info(
            f"已注册本体插件智能工具{smart_count}个", command="AI"
        )

    _ai_ready = True
    return True


def is_ai_ready() -> bool:
    """运行资源是否已完成引导

    返回:
        bool: 是否已引导
    """
    return _ai_ready


__all__ = ["ensure_ai_ready", "is_ai_ready"]
