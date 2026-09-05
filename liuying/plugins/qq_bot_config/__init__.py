"""QQ机器人配置管理插件"""

from typing import Any

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

from ._adapter import QQAdapterManager
from ._data_source import QQBotConfigManager
from ._monitor import ReconnectMonitor
from .model import QQBotConfig

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
                help="每个用户最多可配置的机器人数量",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="BOT_LEVEL",
                value=7,
                help="获得当前配置的机器人权限等级",
                default_value=7,
                type=int,
            ),
        ],
    ).to_dict(),
)


class _ConfigFormatter:
    """QQ机器人配置信息格式化器"""

    @staticmethod
    def format_single(bot: dict[str, Any], online: bool) -> str:
        """格式化单个配置信息

        参数:
            bot: QQ_BOTS格式的单个机器人配置
            online: 是否在线

        返回:
            str: 格式化后的配置信息字符串
        """
        lines = [
            f"机器人ID: {bot['id']}",
            f"连接状态: {'在线' if online else '离线'}",
            f"Secret: {bot['secret'][:10]}...",
            f"WebSocket: {'启用' if bot['use_websocket'] else '禁用'}",
        ]
        enabled = [k for k, v in bot.get("intent", {}).items() if v]
        if enabled:
            lines.append(f"启用意图: {', '.join(enabled)}")
        return "\n".join(lines)

    @staticmethod
    def format_list(
        bots: list[dict[str, Any]], online_ids: set[str]
    ) -> str:
        """格式化配置列表信息

        参数:
            bots: QQ_BOTS格式的配置列表
            online_ids: 在线机器人ID集合

        返回:
            str: 格式化后的配置列表字符串
        """
        parts = [f"共有 {len(bots)} 个QQ机器人配置:\n"]
        for i, b in enumerate(bots, 1):
            online_icon = "O" if b["id"] in online_ids else "X"
            parts.append(f"{i}. [{online_icon}] {b['id']}")
        return "\n".join(parts)

    @staticmethod
    def format_intent(
        intent: dict[str, bool], descriptions: dict[str, str]
    ) -> str:
        """格式化意图配置列表

        参数:
            intent: 意图配置字典
            descriptions: 字段描述映射

        返回:
            str: 格式化后的意图配置字符串
        """
        lines = ["意图配置:"]
        for field, value in intent.items():
            desc = descriptions.get(field, "")
            status = "启用" if value else "禁用"
            lines.append(f"  {field} ({desc}): {status}")
        return "\n".join(lines)

    @staticmethod
    def format_status(status: dict) -> str:
        """格式化适配器状态信息

        参数:
            status: 适配器状态字典

        返回:
            str: 格式化后的状态字符串
        """
        parts = ["QQ适配器状态:\n"]

        connected = status["connected_bots"]
        if connected:
            parts.append(f"已连接机器人 ({len(connected)}个):")
            parts.extend(
                f"  - {bot['id']} ({bot['adapter']})" for bot in connected
            )
        else:
            parts.append("已连接机器人: 无")

        configured = status["configured_bots"]
        if configured:
            parts.append(f"\n已配置机器人 ({len(configured)}个):")
            parts.extend(
                f"  - {bot['id']} [{'WS' if bot['use_websocket'] else 'Webhook'}]"
                for bot in configured
            )
        else:
            parts.append("\n已配置机器人: 无")

        return "\n".join(parts)


@PriorityLifecycle.on_startup(priority=10)
async def _() -> None:
    """启动时从数据库加载配置到适配器并启动重连监控"""
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
        await MessageUtils.build_message(
            _ConfigFormatter.format_single(bot, bot_id.result in online_ids)
        ).finish(reply_to=True)
    else:
        bots = await QQBotConfig.get_user_bots(user_id)
        if not bots:
            await MessageUtils.build_message(
                "暂无QQ机器人配置\n使用 'qq配置添加' 命令添加配置"
            ).finish(reply_to=True)
        await MessageUtils.build_message(
            _ConfigFormatter.format_list(bots, online_ids)
        ).finish(reply_to=True)


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
        await MessageUtils.build_message(msg).finish(reply_to=True)

    await MessageUtils.build_message(
        "请指定要修改的字段\n可用选项: --secret, --ws/--no-ws"
    ).finish(reply_to=True)


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
        descriptions = QQBotConfigManager.get_intent_fields()
        lines = ["可用意图字段:"]
        lines.extend(f"  {f}: {desc}" for f, desc in descriptions.items())
        await MessageUtils.build_message("\n".join(lines)).finish(
            reply_to=True
        )

    if arparma.find("reset"):
        msg = await QQBotConfigManager.reset_intent(user_id, bot_id)
        await MessageUtils.build_message(msg).finish(reply_to=True)

    if field.available and value.available:
        msg = await QQBotConfigManager.update_intent(
            user_id, bot_id, field.result, value.result
        )
        await MessageUtils.build_message(msg).finish(reply_to=True)

    intent = await QQBotConfigManager.get_intent(user_id, bot_id)
    if intent is None:
        await MessageUtils.build_message(
            f"未找到机器人配置: {bot_id}"
        ).finish(reply_to=True)

    descriptions = QQBotConfigManager.get_intent_fields()
    await MessageUtils.build_message(
        f"机器人 {bot_id} {_ConfigFormatter.format_intent(intent, descriptions)}"
    ).finish(reply_to=True)


@_status_matcher.handle()
async def _() -> None:
    """查询QQ适配器状态"""
    status = QQAdapterManager.get_adapter_status()
    await MessageUtils.build_message(
        _ConfigFormatter.format_status(status)
    ).finish(reply_to=True)


@_clear_matcher.handle()
async def _() -> None:
    """清空全部用户的QQ机器人配置(仅超级用户)"""
    msg = await QQBotConfigManager.clear_all_configs()
    await MessageUtils.build_message(msg).finish(reply_to=True)
