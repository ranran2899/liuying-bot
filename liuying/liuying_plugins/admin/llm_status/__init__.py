"""LLM 状态管理插件 - 查看 LLM 配置与 Token 消耗"""

from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.models._llm.token_quota import UserToken
from liuying.utils.apscheduler import task_manager
from liuying.utils.enum import PluginType
from liuying.utils.LLM import llm_manager
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from .status_builder import build_status_text

user_token_quota = Config.get_config("llm_status", "USER_TOKEN_QUOTA_MAX")

__plugin_meta__ = PluginMetadata(
    name="LLM状态管理",
    description="查看 LLM 配置状态与 Token 消耗",
    usage="""
    查看 LLM 配置状态与 Token 消耗
    指令:
        LLM状态
        立即重置token额度
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=6,
        commands=[
            Command(command="LLM状态"),
            Command(command="立即重置token额度"),
        ],
        configs=[
            RegisterConfig(
                # module="llm_status",
                key="USER_TOKEN_QUOTA_MAX",
                value=100000,
                help="每天 0 点重置所有用户 token 额度",
                default_value=100000,
                type=int,
            ),
            RegisterConfig(
                module="LLM",
                key="DEFAULT_MODEL_NAME",
                value="GLM/glm-4-flash-250414",
                help="LLM服务全局默认使用的模型名称 (格式: ProviderName/ModelName)",
                default_value="GLM/glm-4-flash-250414",
                type=str,
            ),
            RegisterConfig(
                module="LLM",
                key="GEMINI_SAFETY_THRESHOLD",
                value="BLOCK_NONE",
                help=(
                    "Gemini 安全过滤阈值\n"
                    " - BLOCK_LOW_AND_ABOVE: 阻止低级别及以上\n"
                    " - BLOCK_NONE: 无限制"
                ),
                default_value="BLOCK_NONE",
                type=str,
            ),
            RegisterConfig(
                module="LLM",
                key="PROVIDERS",
                value=[
                    {
                        "name": "GLM",
                        "api_key": "",
                        "api_base": "https://open.bigmodel.cn",
                        "api_type": "zhipu",
                        "extra_headers": None,
                        "capabilities": None,
                        "models": [
                            {"model_name": "glm-4-flash-250414", "extra_headers": None},
                        ],
                    },
                    {
                        "name": "BaiduSearch",
                        "api_key": "",
                        "api_base": "https://qianfan.baidubce.com",
                        "api_type": "web_search",
                        "extra_headers": None,
                        "capabilities": ["web_search"],
                        "models": [
                            {"model_name": "web-search", "extra_headers": None},
                        ],
                    },
                ],
                help=(
                    "配置多个AI服务提供商及其模型信息\n"
                    " - name: 提供商名称\n"
                    " - api_key: API密钥\n"
                    " - api_base: API基础URL\n"
                    " - api_type: API类型\n"
                    "   (openai/zhipu/gemini/ark/openrouter/web_search)\n"
                    " - extra_headers: 额外请求头(可选)\n"
                    ' - capabilities: 显式声明的能力列表(可选), 如 ["web_search"]\n'
                    " - models: 模型列表\n"
                    "   - model_name: 名称\n"
                    "   - extra_headers: 模型级额外请求头(可选)"
                ),
                default_value=[],
                type=list,
            ),
            RegisterConfig(
                module="LLM",
                key="CLIENT_SETTINGS",
                value={
                    "timeout": 300,
                    "max_retries": 3,
                    "retry_delay": 1.0,
                    "structured_retries": 2,
                    "proxy": "",
                },
                help=(
                    "LLM客户端高级设置\n"
                    " - timeout: 请求超时时间(秒)\n"
                    " - max_retries: 最大重试次数\n"
                    " - retry_delay: 重试延迟时间(秒)\n"
                    " - structured_retries: 结构化重试次数\n"
                    " - proxy: 代理地址(如 http://127.0.0.1:7890)"
                ),
                default_value={},
                type=dict,
            ),
            RegisterConfig(
                module="LLM",
                key="DEBUG_LOG",
                value={
                    "show_tools": False,
                    "show_schema": False,
                    "show_safety": False,
                },
                help=(
                    "LLM日志详情开关\n"
                    " - show_tools: 是否显示工具调用\n"
                    " - show_schema: 是否显示模型输出的JSON模式\n"
                    " - show_safety: 是否显示安全警告"
                ),
                default_value={},
                type=dict,
            ),
        ],
    ).to_dict(),
)

llm_status_cmd = on_alconna(
    Alconna("LLM状态"),
    rule=admin_check(6),
    priority=5,
    block=True,
)

reset_token_quota_cmd = on_alconna(
    Alconna("立即重置token额度"),
    rule=admin_check(6),
    priority=5,
    block=True,
)


@PriorityLifecycle.on_startup(priority=2)
def _reload_llm_config() -> None:
    """在全局配置初始化完成后刷新 LLM 配置"""
    llm_manager.reload_config()

@task_manager.cron_task("reset_user_token_quota", hour=0, minute=0, second=0)
async def _reset_user_token_quota() -> None:
    """每天 0 点重置所有用户 token 额度"""
    await UserToken.reset_all(user_token_quota)
    logger.info("已重置所有用户 token 额度", command="LLM状态")


@llm_status_cmd.handle()
async def handle_llm_status(bot: Bot, session: Uninfo) -> None:
    """处理 LLM 状态命令

    参数:
        bot: 机器人实例
        session: 会话信息
    """
    logger.info("查看LLM状态", command="LLM状态", session=session)
    await MessageUtils.build_message(
        await build_status_text()
    ).finish(reply_to=True)


@reset_token_quota_cmd.handle()
async def handle_reset_token_quota(bot: Bot, session: Uninfo) -> None:
    """处理立即重置 token 额度命令

    参数:
        bot: 机器人实例
        session: 会话信息
    """
    logger.info("手动重置用户 token 额度", command="LLM状态", session=session)
    updated_count = await UserToken.reset_all(user_token_quota)
    await MessageUtils.build_message(
        f"已立即重置 {updated_count} 位用户的 token 额度为 {user_token_quota}"
    ).finish(reply_to=True)
