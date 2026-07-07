"""流萤AI插件

AI对话核心 + 主动行为 + 工具调用 + 拟人化发送 + 完整记忆系统 + TTS + 贴纸。
深度整合流萤本体系统：LLM/数据库/缓存/定时任务/好感度/权限。
"""

from nonebot import get_driver
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import Command, PluginExtraData, PluginSetting
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

from .agent.tools import (  # 公开API供第三方注册工具
    AgentTool,
    register_external_tool,
    tool_registry,
)
from .config import PluginConfig, get_config
from .core.knowledge_db import knowledge_base
from .models import (  # noqa: F401  导入触发模型注册
    ConversationRecord,
    ConversationTurn,
    EmotionState,
    GroupContextSnapshot,
    KnowledgeQueryLog,
    MemoryItem,
    StickerFeedback,
    StickerItem,
    StickerUsage,
    TokenLedgerRecord,
    UserPersonaProfile,
    UserPersonaSelection,
)

__all__ = [
    "AgentTool",
    "register_external_tool",
    "tool_registry",
]
# AI插件公开API（供第三方插件注册自定义Agent工具）

_AI_PLUGIN_PRIORITY = 2
"""AI插件生命周期优先级（数字越小越先执行）"""

__plugin_meta__ = PluginMetadata(
    name="流萤AI",
    description="AI对话核心 + 主动行为 + 工具调用 + 拟人化发送 + 完整记忆 + TTS + 贴纸",
    usage="""
    @bot [消息] - 与流萤AI对话（也可@机器人或私聊）
    流萤对话 - 开启/关闭AI对话
    流萤人格 [名称] - 切换AI人格
    流萤画像 - 查看你的用户画像
    流萤记忆 - 查看AI记忆摘要
    流萤清空 - 清空对话历史（管理员）
    流萤说 [文本] - TTS语音合成
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
            impression=0.0,
        ),
        commands=[
            # Command(
            #     command="流萤 [消息]",
            #     description="与流萤AI对话",
            # ),
            Command(
                command="bot对话",
                description="开启/关闭AI对话",
            ),
            Command(
                command="bot人格 [名称]",
                description="切换AI人格",
            ),
            Command(
                command="我的画像",
                description="查看用户画像",
            ),
            Command(
                command="bot记忆",
                description="查看AI记忆摘要",
            ),
            Command(
                command="清空对话历史",
                description="清空对话历史",
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
            Command(
                command="流萤AI体检",
                description="AI功能健康体检（管理员）",
            ),
        ],
        superuser_help="""
        超级用户命令:
        - 清空对话历史: 清空对话历史
        - bot人格 [名称]: 切换AI人格
        - 流萤AI状态: 查看AI子功能开关
        - 流萤AI开关 [功能] [on/off]: 全局AI子功能开关
        - 流萤AI群开关 [群号] [功能] [on/off]: 群组级AI子功能开关
        - 流萤AI用户开关 [用户ID] [功能] [on/off]: 用户级AI子功能开关
        - 流萤AI重置: 重置所有运行时覆盖

        注意: ban/unban/黑名单/管理员授权请使用流萤本体命令:
        - ban/unban/ban列表: 使用 admin.ban 插件
        - 管理员授权: 使用 admin.bot_perm 插件
        - 插件整体开关: 使用 admin.plugin_switch 插件
        """,
    ).to_dict(),
)

@PriorityLifecycle.on_startup(priority=_AI_PLUGIN_PRIORITY)
async def _init_ai_plugin() -> None:
    """AI插件初始化

    初始化内置知识库（独立 SQLite，与 liuying_db 解耦），
    注册定时任务和matcher。

    通过 PriorityLifecycle 注册，优先级=2，确保在依赖系统
    （数据库/LLM/缓存）就绪后、业务插件之前加载。
    """
    if not get_config("ENABLE_AI", True):
        logger.info("AI插件已禁用", command="AI")
        return

    await knowledge_base.init()
    logger.info(
        f"AI插件初始化完成，人格: {get_config('DEFAULT_PERSONA', 'liuying')}",
        command="AI",
    )

    # 内置Agent工具在 agent.tools 导入时自动注册
    logger.debug("Agent内置工具已自动注册", command="AI")

    # 知识库现基于流萤本体 PluginInfo + 实时元信息，
    # 无需扫描入库，直接通过 knowledge_store 查询即可。

    # 初始化运行时开关（从配置加载全局状态）
    try:
        # 延迟导入以避免循环依赖：__init__ 导入 runtime_switch，
        # runtime_switch 可能通过 core 层间接引用 AI 插件配置
        from .core.runtime import runtime_switch

        runtime_switch.initialize()
        logger.debug("运行时开关已初始化", command="AI")
    except Exception as e:
        logger.warning(
            f"运行时开关初始化失败: {e}", command="AI", e=e
        )

    try:
        # 延迟导入以避免循环依赖：chat_matchers 导入 AI 插件模块，
        # 而 __init__ 在初始化阶段调用 setup_matchers
        from .handlers.chat_matchers import setup_matchers

        setup_matchers()
    except ImportError:
        logger.debug("AI matcher尚未实现，跳过", command="AI")

    # 注册AI管理员命令
    try:
        # 延迟导入以避免循环依赖：admin_commands 导入 AI 插件模块，
        # 而 __init__ 在初始化阶段调用 setup_admin_matchers
        from .handlers.admin_commands import setup_admin_matchers

        setup_admin_matchers()
        logger.debug("AI管理员命令已注册", command="AI")
    except Exception as e:
        logger.warning(
            f"AI管理员命令注册失败: {e}", command="AI", e=e
        )

    try:
        # 延迟导入以避免循环依赖：jobs 模块导入 AI 插件核心模块，
        # 而 __init__ 在初始化阶段调用 setup_jobs
        from .jobs import setup_jobs

        await setup_jobs()
    except ImportError:
        logger.debug("AI定时任务尚未实现，跳过", command="AI")

    # WebUI 已分离为独立插件 AI_webui（liuying/plugins/AI_webui），
    # 通过 WEBUI_ENABLED 配置项（AI_WEBUI 模块）控制挂载，无需在此初始化。

    try:
        # 延迟导入以避免循环依赖：skill_runtime 导入 agent 工具模块，
        # 而 AI 插件 __init__ 在初始化阶段调用 register_all
        from .agent.skill_runtime import skill_loader

        skill_loader.register_all()
        logger.debug("AI技能包已加载", command="AI")
    except Exception as e:
        logger.debug(
            f"AI技能包加载失败: {e}", command="AI", e=e
        )


@PriorityLifecycle.on_shutdown(priority=_AI_PLUGIN_PRIORITY)
async def _shutdown_ai_plugin() -> None:
    """AI插件关闭清理

    通过 PriorityLifecycle 注册，优先级=2，
    按数字升序执行，先于业务插件关闭。
    """
    try:
        # 延迟导入以避免循环依赖：core.llm 模块可能在初始化时
        # 间接引用 AI 插件配置，而 __init__ 在关闭阶段调用 prune_old
        from .core.llm import token_ledger

        await token_ledger.prune_old(days=1)
    except Exception as e:
        logger.debug(
            f"Token账本清理失败: {e}", command="AI", e=e
        )
    logger.info("AI插件已关闭", command="AI")


# # 保留 driver 引用，便于 WebUI 等模块通过 AI 插件获取 driver 实例
# driver = get_driver()
