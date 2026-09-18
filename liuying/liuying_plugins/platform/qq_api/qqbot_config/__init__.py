"""QQ机器人配置管理插件"""

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    Match,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.message import MessageUtils
from liuying.utils.rules import ensure_private

from .adapter import QQAdapterManager
from .formatter import ConfigFormatter
from .manager import QQBotConfigManager
from .model import QQBotConfig
from .monitor import ReconnectMonitor

__plugin_meta__ = PluginMetadata(
    name="QQ机器人配置管理",
    description="管理QQ机器人适配器配置,支持添加、查询、修改和删除配置",
    usage="""
    指令格式:
        qq配置添加 <机器人ID> <Secret> [--no-ws]
        qq配置查询 [机器人ID]
        qq配置修改 <机器人ID> [--secret Secret] [--ws|--no-ws]
        qq配置删除 <机器人ID>
        qq配置导出 (仅私聊可用,导出QQ_BOTS环境变量格式)
        qq配置意图 <机器人ID> [--set 字段 on|off | --reset | --list]
        qq配置状态 (仅超级用户)
        清空全部QQ配置 (仅超级用户)

    示例:
        qq配置添加 100000000 secret456
        qq配置添加 100000000 secret456 --no-ws
        qq配置查询
        qq配置修改 100000000 --secret 新Secret
        qq配置删除 100000000
        qq配置意图 100000000 --set group_members off
    """.strip(),
    extra=PluginExtraData(
        admin_level=0,
        plugin_type=PluginType.NORMAL,
        superuser_help="""
        所有用户均可使用此插件管理自己的QQ机器人配置。
        新版QQ适配器鉴权仅需 AppID 与 AppSecret,每个用户最多可配置5个机器人。
        配置以QQ_BOTS环境变量格式存储,可通过 qq配置导出 直接导出使用。
        添加配置后自动连接到QQ适配器,无需重启。
        连续3次重连失败将自动删除配置。
        超级用户指令: 清空全部QQ配置 (删除所有用户的全部配置)
        """.strip(),
        configs=[
            RegisterConfig(
                key="MAX_BOT_COUNT",
                value=5,
                module="qqbot_config",
                help="每个用户最多可配置的机器人数量",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="BOT_LEVEL",
                value=7,
                module="qqbot_config",
                help="获得当前配置的机器人权限等级",
                default_value=7,
                type=int,
            ),
        ],
    ).to_dict(),
)


@PriorityLifecycle.on_startup(priority=10)
async def _() -> None:
    """启动时初始化业务关联、加载配置到适配器并启动重连监控"""
    QQBotConfigManager.setup()
    success, fail = await QQBotConfigManager.load_configs_to_adapter()
    if success > 0 or fail > 0:
        logger.info(
            f"QQ适配器配置加载: 成功 {success}, 失败 {fail}",
            "QQBotConfig",
        )
    ReconnectMonitor.start()


_add_matcher = on_alconna(
    Alconna(
        "qq配置添加",
        Args["bot_id", str]["secret", str],
        Option("--no-ws", dest="no_websocket", help_text="不使用WebSocket"),
    ),
    priority=5,
    block=True,
)

_query_matcher = on_alconna(
    Alconna("qq配置查询", Args["bot_id?", str]),
    priority=5,
    block=True,
)

_update_matcher = on_alconna(
    Alconna(
        "qq配置修改",
        Args["bot_id", str],
        Option("--secret", Args["secret", str], help_text="更新Secret"),
        Option("--ws", dest="use_websocket", help_text="使用WebSocket"),
        Option("--no-ws", dest="no_websocket", help_text="不使用WebSocket"),
    ),
    priority=5,
    block=True,
)

_delete_matcher = on_alconna(
    Alconna("qq配置删除", Args["bot_id", str]),
    priority=5,
    block=True,
)

_export_matcher = on_alconna(
    Alconna("qq配置导出"),
    rule=ensure_private,
    priority=5,
    block=True,
)

_intent_matcher = on_alconna(
    Alconna(
        "qq配置意图",
        Args["bot_id", str],
        Option(
            "--set",
            Args["field", str]["value", bool],
            help_text="设置意图字段",
        ),
        Option("--reset", help_text="重置为默认意图"),
        Option("--list", dest="list_fields", help_text="列出可用意图字段"),
    ),
    priority=5,
    block=True,
)

_status_matcher = on_alconna(
    Alconna("qq配置状态"),
    priority=5,
    permission=SUPERUSER,
    block=True,
)

_clear_matcher = on_alconna(
    Alconna("清空全部QQ配置"),
    priority=5,
    permission=SUPERUSER,
    block=True,
)


@_add_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    secret: str,
) -> None:
    """添加QQ机器人配置"""
    msg = await QQBotConfigManager.add_config(
        user_id=session.user.id,
        bot_id=bot_id,
        secret=secret,
        use_websocket=not arparma.find("no_websocket"),
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_query_matcher.handle()
async def _(session: Uninfo, bot_id: Match[str]) -> None:
    """查询QQ机器人配置"""
    user_id = session.user.id
    online_ids = QQAdapterManager.get_online_bot_ids()

    if bot_id.available:
        bot = await QQBotConfig.get_bot(user_id, bot_id.result)
        if bot is None:
            await MessageUtils.build_message(
                f"未找到机器人配置: {bot_id.result}"
            ).finish(reply_to=True)
        msg = ConfigFormatter.format_single(bot, bot_id.result in online_ids)
    else:
        bots = await QQBotConfig.get_user_bots(user_id)
        if not bots:
            await MessageUtils.build_message(
                "暂无QQ机器人配置\n使用 'qq配置添加' 命令添加配置"
            ).finish(reply_to=True)
        msg = ConfigFormatter.format_list(bots, online_ids)
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_update_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    secret: Match[str],
) -> None:
    """修改QQ机器人配置"""
    use_ws: bool | None = None
    if arparma.find("use_websocket"):
        use_ws = True
    elif arparma.find("no_websocket"):
        use_ws = False

    if secret.available or use_ws is not None:
        msg = await QQBotConfigManager.update_config(
            user_id=session.user.id,
            bot_id=bot_id,
            secret=secret.result if secret.available else None,
            use_websocket=use_ws,
        )
    else:
        msg = "请指定要修改的字段\n可用选项: --secret, --ws/--no-ws"
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_delete_matcher.handle()
async def _(session: Uninfo, bot_id: str) -> None:
    """删除QQ机器人配置"""
    msg = await QQBotConfigManager.delete_config(session.user.id, bot_id)
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_export_matcher.handle()
async def _(session: Uninfo) -> None:
    """导出QQ机器人配置(仅私聊可用)"""
    env_config = await QQBotConfigManager.export_to_env_format(
        session.user.id
    )
    if not env_config:
        await MessageUtils.build_message(
            "暂无可导出的QQ机器人配置"
        ).finish(reply_to=True)
    await MessageUtils.build_message(
        f"QQ_BOTS='{env_config}'"
    ).finish(reply_to=True)


@_intent_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    field: Match[str],
    value: Match[bool],
) -> None:
    """管理QQ机器人意图配置"""
    user_id = session.user.id

    if arparma.find("list_fields"):
        msg = ConfigFormatter.format_intent_fields(
            QQBotConfigManager.get_intent_fields()
        )
    elif arparma.find("reset"):
        msg = await QQBotConfigManager.reset_intent(user_id, bot_id)
    elif field.available and value.available:
        msg = await QQBotConfigManager.update_intent(
            user_id, bot_id, field.result, value.result
        )
    else:
        intent = await QQBotConfigManager.get_intent(user_id, bot_id)
        if intent is None:
            msg = f"未找到机器人配置: {bot_id}"
        else:
            descriptions = QQBotConfigManager.get_intent_fields()
            msg = (
                f"机器人 {bot_id} "
                f"{ConfigFormatter.format_intent(intent, descriptions)}"
            )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_status_matcher.handle()
async def _() -> None:
    """查询QQ适配器状态"""
    status = QQAdapterManager.get_adapter_status()
    await MessageUtils.build_message(
        ConfigFormatter.format_status(status)
    ).finish(reply_to=True)


@_clear_matcher.handle()
async def _() -> None:
    """清空全部用户的QQ机器人配置(仅超级用户)"""
    msg = await QQBotConfigManager.clear_all_configs()
    await MessageUtils.build_message(msg).finish(reply_to=True)
