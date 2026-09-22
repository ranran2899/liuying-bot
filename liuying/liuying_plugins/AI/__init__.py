"""流萤AI插件

AI对话核心 + 主动行为 + 工具调用 + 拟人化发送 + 完整记忆系统 + TTS + 贴纸。
深度整合流萤本体系统：LLM/数据库/缓存/定时任务/好感度/权限。

所有 matcher 在本模块统一注册，业务逻辑委托给 handlers 包中的
逻辑类（ChatCommands/AdminCommands/TaskCommands 等）。
"""

from nonebot import on_message, on_notice
from nonebot.adapters import Bot, Event
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, UniMsg, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, PluginSetting
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.rules import admin_check

from .config import PluginConfig, get_config
from .core.knowledge_index import knowledge_base
from .core.llm import llm_helper, token_ledger
from .core.memory import memory_manager
from .core.runtime import runtime_switch
from .handlers import (
    AdminCommands,
    ChatCommands,
    ChatMatchersHelper,
    MemoryCommands,
    PersonaCommands,
    PokeNotice,
    TaskCommands,
    TtsCommands,
)
from .jobs import setup_jobs
from .skills import SkillRuntime, skill_loader
from .tools.external import smart_tool_bridge
from .tools.mcp import mcp_bridge

__plugin_meta__ = PluginMetadata(
    name="流萤AI",
    description="AI对话核心 + 主动行为 + 工具调用 + 拟人化发送 + 完整记忆 + TTS + 贴纸",
    usage="""
    @bot [消息] - 与流萤AI对话（也可私聊）
    bot人格切换 [名称] - 切换/查看AI人格
    我的画像 - 查看你的用户画像
    bot记忆 - 查看AI记忆摘要
    清空对话历史 - 清空对话历史
    清空记忆 - 清空当前人格的所有记忆数据
    bot说 [文本] - TTS语音合成
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.NORMAL,
        menu_type="AI",
        is_show=True,
        configs=PluginConfig,
        setting=PluginSetting(
            level=5,
            default_status=True,
            cost_gold=0,
        ),
        commands=[
            Command(
                command="bot人格切换 [名称]",
                description="切换/查看AI人格",
            ),
            Command(
                command="我的画像",
                description="查看你的用户画像",
            ),
            Command(
                command="清空对话历史",
                description="清空对话历史",
            ),
            Command(
                command="清空记忆",
                description="清空当前人格的所有记忆数据",
            ),
            Command(
                command="bot说 [文本]",
                description="TTS语音合成",
            ),
            Command(
                command="流萤AI状态",
                description="查看AI功能开关状态（管理员）",
            ),
            Command(
                command="流萤AI开关 [功能] [on/off]",
                description="设置全局功能开关（管理员）",
            ),
        ],
        superuser_help="""
        超级用户命令:
        - 清空对话历史: 清空对话历史
        - bot人格切换 [名称]: 切换AI人格
        - 流萤AI状态: 查看AI子功能开关
        - 流萤AI开关 [功能] [on/off]: 全局AI子功能开关
        - 全局清空记忆: 清空所有用户的所有人格记忆与对话记录

        注意: ban/unban/黑名单/管理员授权请使用流萤本体命令:
        - ban/unban/ban列表: 使用 admin.ban 插件
        - 管理员授权: 使用 admin.bot_perm 插件
        - 插件整体开关: 使用 admin.plugin_switch 插件
        """,
    ).to_dict(),
)


# ==================== 消息监听 ====================

# 群内其他bot发言检测（高优先级，不阻断后续matcher）
peer_cmd = on_message(priority=100, block=False)


@peer_cmd.handle()
async def handle_peer_detection(session: Uninfo, message: UniMsg) -> None:
    """检测群内其他bot发言并触发静默"""
    await ChatCommands.handle_peer_detection(session, message)


# AI对话主入口：私聊自动命中，群聊@bot或回复bot时命中
private_msg_cmd = on_message(
    rule=to_me(),
    priority=520,
    block=False
)


@private_msg_cmd.handle()
async def handle_private_message(
    event: Event, session: Uninfo, message: UniMsg
) -> None:
    """处理私聊或@bot/回复bot的消息"""
    await ChatCommands.handle_chat_message(event, session, message)


# ==================== 群通知 ====================

# group_ban notice 监听以感知群禁言状态
group_ban_matcher = on_notice(priority=50, block=False)


@group_ban_matcher.handle()
async def handle_group_ban(bot: Bot, event: Event) -> None:
    """处理群禁言notice事件"""
    await ChatMatchersHelper.handle_group_ban(bot, event)


# 拍一拍响应：戳bot自己时按概率戳回去
poke_matcher = on_notice(priority=60, block=False)


@poke_matcher.handle()
async def handle_poke(bot: Bot, event: Event) -> None:
    """处理戳一戳事件"""
    await PokeNotice.handle_poke(bot, event)


# ==================== 人格命令 ====================

persona_cmd = on_alconna(
    Alconna("bot人格切换", Args["name?", str]),
    aliases={"AI人格切换", "bot人设切换"},
    priority=49,
    block=True,
)

profile_cmd = on_alconna(
    Alconna("我的画像"),
    aliases={"查看我的画像"},
    priority=49,
    block=True,
)


@persona_cmd.handle()
async def handle_persona(session: Uninfo, name: str = "") -> None:
    """切换/查看AI人格"""
    await PersonaCommands.handle_persona(session, name)


@profile_cmd.handle()
async def handle_profile(session: Uninfo) -> None:
    """查看用户画像"""
    await PersonaCommands.handle_profile(session)


# ==================== 记忆命令 ====================

memory_cmd = on_alconna(
    Alconna("bot记忆"),
    aliases={"AI记忆"},
    priority=49,
    block=True,
)

clear_cmd = on_alconna(
    Alconna("清空对话历史"),
    aliases={"bot清空对话", "清除对话"},
    priority=49,
    block=True,
)

clear_memory_cmd = on_alconna(
    Alconna("清空记忆"),
    aliases={"bot清空记忆", "清除记忆"},
    priority=49,
    block=True,
)


@memory_cmd.handle()
async def handle_memory(session: Uninfo) -> None:
    """查看记忆摘要"""
    await MemoryCommands.handle_memory(session)


@clear_cmd.handle()
async def handle_clear(session: Uninfo) -> None:
    """清空对话历史"""
    await MemoryCommands.handle_clear(session)


@clear_memory_cmd.handle()
async def handle_clear_memory(session: Uninfo) -> None:
    """清空记忆"""
    await MemoryCommands.handle_clear_memory(session)


# ==================== TTS命令 ====================

tts_cmd = on_alconna(
    Alconna("bot说", Args["text", str]),
    aliases={"AI说"},
    priority=49,
    block=True,
)


@tts_cmd.handle()
async def handle_tts(session: Uninfo, text: str = "") -> None:
    """TTS语音合成"""
    await TtsCommands.handle_tts(session, text)


# ==================== 用户定时任务命令 ====================

task_list_cmd = on_alconna(
    Alconna("bot任务列表"),
    aliases={"AI任务列表", "bot定时任务", "AI定时任务"},
    priority=49,
    block=True,
)

task_create_cmd = on_alconna(
    Alconna(
        "bot任务创建",
        Args["cron", str]["message", str],
    ),
    aliases={"AI任务创建"},
    priority=49,
    block=True,
)

task_cancel_cmd = on_alconna(
    Alconna("bot任务取消", Args["task_no", str]),
    aliases={"AI任务取消"},
    priority=49,
    block=True,
)

task_pause_cmd = on_alconna(
    Alconna("bot任务暂停", Args["task_no", str]),
    aliases={"AI任务暂停"},
    priority=49,
    block=True,
)

task_resume_cmd = on_alconna(
    Alconna("bot任务恢复", Args["task_no", str]),
    aliases={"AI任务恢复"},
    priority=49,
    block=True,
)


@task_list_cmd.handle()
async def handle_task_list(session: Uninfo) -> None:
    """查看定时任务列表"""
    await TaskCommands.handle_list(session)


@task_create_cmd.handle()
async def handle_task_create(
    session: Uninfo, cron: str = "", message: str = ""
) -> None:
    """创建定时任务"""
    await TaskCommands.handle_create(session, cron, message)


@task_cancel_cmd.handle()
async def handle_task_cancel(session: Uninfo, task_no: str = "") -> None:
    """取消定时任务"""
    await TaskCommands.handle_cancel(session, task_no)


@task_pause_cmd.handle()
async def handle_task_pause(session: Uninfo, task_no: str = "") -> None:
    """暂停定时任务"""
    await TaskCommands.handle_pause(session, task_no)


@task_resume_cmd.handle()
async def handle_task_resume(session: Uninfo, task_no: str = "") -> None:
    """恢复定时任务"""
    await TaskCommands.handle_resume(session, task_no)


# ==================== AI管理命令 ====================

ai_status_cmd = on_alconna(
    Alconna("流萤AI状态"),
    aliases={"AI状态", "流萤AI体检"},
    rule=admin_check(5),
    priority=48,
    block=True,
)

ai_switch_cmd = on_alconna(
    Alconna(
        "流萤AI开关",
        Args["feature", str]["state", str],
    ),
    aliases={"AI开关"},
    rule=admin_check(5),
    priority=48,
    block=True,
)

ai_clear_all_memory_cmd = on_alconna(
    Alconna("全局清空记忆"),
    aliases={"AI全局清空记忆", "流萤AI全局清空"},
    rule=admin_check(10),
    priority=48,
    block=True,
)


@ai_status_cmd.handle()
async def handle_ai_status(session: Uninfo) -> None:
    """查看AI功能开关状态"""
    await AdminCommands.handle_status(session)


@ai_switch_cmd.handle()
async def handle_ai_switch(
    session: Uninfo, feature: str = "", state: str = ""
) -> None:
    """设置全局AI功能开关"""
    await AdminCommands.handle_switch(session, feature, state)


@ai_clear_all_memory_cmd.handle()
async def handle_ai_clear_all_memory(session: Uninfo) -> None:
    """全局清空所有记忆数据"""
    await AdminCommands.handle_clear_all_memory(session)


@PriorityLifecycle.on_startup(priority=20)
async def _init_ai_plugin() -> None:
    """AI插件初始化

    初始化内置知识库（独立 SQLite，与 liuying_db 解耦），
    注册定时任务和技能包。

    通过 PriorityLifecycle 注册，优先级=20，作为业务插件在核心服务
    （数据库/LLM/缓存，优先级<=10）就绪后加载。
    """
    if not get_config("ENABLE_AI", False):
        logger.info("AI插件已禁用", command="AI")
        return

    await knowledge_base.init()
    logger.info(
        f"AI插件初始化完成，人格: {get_config('DEFAULT_PERSONA', 'liuying')}",
        command="AI",
    )

    # 内置Agent工具在 tools 包导入时自动注册
    logger.debug("Agent内置工具已自动注册", command="AI")

    # 初始化运行时开关（从配置加载全局状态）
    runtime_switch.initialize()
    logger.debug("运行时开关已初始化", command="AI")

    await setup_jobs()


    # 显式注入主插件服务给技能包（LLM助手 + 记忆管理器）
    runtime = SkillRuntime(
        llm_helper=llm_helper,
        memory_manager=memory_manager,
    )
    tool_count = skill_loader.register_all(runtime=runtime)
    logger.debug(
        f"AI技能包已加载，注册工具{tool_count}个", command="AI"
    )

    # 注册MCP远程工具（涉及子进程通信，需在异步上下文中执行）
    mcp_count = await skill_loader.register_mcp_tools()
    if mcp_count:
        logger.debug(
            f"MCP远程工具已注册{mcp_count}个", command="AI"
        )

    # 注册本体插件声明的智能模式函数工具（smart_tools桥接）
    smart_count = smart_tool_bridge.register_all()
    if smart_count:
        logger.info(
            f"已注册本体插件智能工具{smart_count}个", command="AI"
        )


@PriorityLifecycle.on_shutdown(priority=5)
async def _shutdown_ai_plugin() -> None:
    """AI插件关闭清理
    """
    # 关闭MCP连接池，释放全部子进程
    await mcp_bridge.close()
    await token_ledger.prune_old(days=1)
    logger.info("AI插件已关闭", command="AI")
