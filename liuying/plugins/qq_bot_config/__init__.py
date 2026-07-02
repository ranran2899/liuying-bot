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

from ._data_source import QQBotConfigManager, ReconnectMonitor

__plugin_meta__ = PluginMetadata(
    name="QQ机器人配置管理",
    description="管理QQ机器人适配器配置,支持添加、查询、修改和删除配置",
    usage="""
    指令格式:
        qq配置添加 <机器人ID> <Token> <Secret> [选项]
        qq配置查询 [机器人ID]
        qq配置修改 <机器人ID> [选项]
        qq配置删除 <机器人ID>
        qq配置导出 (仅私聊可用)
        qq配置意图 <机器人ID> [选项]
        qq配置状态 (仅管理员可使用)

    选项说明:
        --name <名称>           : 机器人名称
        --sandbox              : 使用沙箱环境
        --no-ws                : 不使用WebSocket
        --remark <备注>        : 备注信息

    意图配置选项:
        --set <字段> <on|off>  : 设置意图字段
        --reset                : 重置为默认意图
        --list                 : 列出可用意图字段

    示例:
        qq配置添加 100000000 token123 secret456
        qq配置添加 100000000 token123 secret456 --name "测试机器人" --sandbox
        qq配置查询
        qq配置查询 100000000
        qq配置修改 100000000 --name "新名称"
        qq配置删除 100000000
        qq配置导出
        qq配置意图 100000000
        qq配置意图 100000000 --set guilds on
        qq配置意图 100000000 --reset
        qq配置意图 100000000 --list
        qq配置状态
    """.strip(),
    extra=PluginExtraData(
        admin_level=0,
        plugin_type=PluginType.NORMAL,
        superuser_help="""
        所有用户均可使用此插件管理自己的QQ机器人配置。
        每个用户最多可配置5个机器人。
        配置数据采用加密存储,确保安全性。
        添加配置后自动连接到QQ适配器,无需重启。
        连续3次重连失败将自动删除配置。
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
            RegisterConfig(
                key="MAX_RECONNECT_FAILURES",
                value=3,
                help="连续重连失败次数上限,超过后自动删除配置",
                default_value=3,
                type=int,
            ),
        ],
    ).to_dict(),
)


@PriorityLifecycle.on_startup(priority=10)
async def _() -> None:
    """启动时从数据库加载配置到适配器并启动重连监控"""
    try:
        success, fail = await QQBotConfigManager.load_configs_to_adapter()
        if success > 0 or fail > 0:
            logger.info(
                f"QQ适配器配置加载: 成功 {success}, 失败 {fail}",
                "QQBotConfig",
            )
        ReconnectMonitor.start()
    except Exception as e:
        logger.error(f"加载QQ适配器配置失败: {e}", "QQBotConfig", e=e)


_add_matcher = on_alconna(
    Alconna(
        "qq配置添加",
        Args["bot_id", str]["token", str]["secret", str],
        Option("--name", Args["bot_name", str], help_text="机器人名称"),
        Option("--sandbox", dest="is_sandbox", help_text="使用沙箱环境"),
        Option("--no-ws", dest="no_websocket", help_text="不使用WebSocket"),
        Option("--remark", Args["remark", str], help_text="备注信息"),
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
        Option("--token", Args["token", str], help_text="更新Token"),
        Option("--secret", Args["secret", str], help_text="更新Secret"),
        Option("--name", Args["bot_name", str], help_text="更新机器人名称"),
        Option("--status", Args["status", bool], help_text="更新状态"),
        Option("--remark", Args["remark", str], help_text="更新备注"),
        Option("--sandbox", dest="is_sandbox", help_text="使用沙箱环境"),
        Option(
            "--no-sandbox", dest="no_sandbox", help_text="使用正式环境"
        ),
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


def _format_single_config(config: dict, online: bool) -> str:
    """格式化单个配置信息

    参数:
        config: 配置字典
        online: 是否在线

    返回:
        str: 格式化后的配置信息字符串
    """
    online_text = "在线" if online else "离线"
    lines = [
        f"机器人ID: {config['bot_id']}",
        f"名称: {config.get('bot_name') or '未设置'}",
        f"连接状态: {online_text}",
        f"Token: {config['token'][:10]}...",
        f"Secret: {config['secret'][:10]}...",
        f"WebSocket: {'启用' if config['use_websocket'] else '禁用'}",
        f"沙箱环境: {'是' if config['is_sandbox'] else '否'}",
        f"配置状态: {'启用' if config['status'] else '禁用'}",
    ]
    if config.get("remark"):
        lines.append(f"备注: {config['remark']}")
    lines.append(f"创建时间: {config['create_time']}")
    if config.get("update_time"):
        lines.append(f"更新时间: {config['update_time']}")
    return "\n".join(lines)


def _format_config_list(configs: list[dict], online_ids: set[str]) -> str:
    """格式化配置列表信息

    参数:
        configs: 配置字典列表
        online_ids: 在线机器人ID集合

    返回:
        str: 格式化后的配置列表字符串
    """
    parts = [f"共有 {len(configs)} 个QQ机器人配置:\n"]
    for i, c in enumerate(configs, 1):
        online_icon = "O" if c["bot_id"] in online_ids else "X"
        env = "沙箱" if c["is_sandbox"] else "正式"
        name = c.get("bot_name") or "未命名"
        parts.append(f"{i}. [{online_icon}] {c['bot_id']} ({name}) [{env}]")
    return "\n".join(parts)


def _format_intent_list(
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


@_add_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    token: str,
    secret: str,
    bot_name: Match[str],
    remark: Match[str],
) -> None:
    """添加QQ机器人配置"""
    _, msg = await QQBotConfigManager.add_config(
        user_id=session.user.id,
        bot_id=bot_id,
        token=token,
        secret=secret,
        intent=QQBotConfigManager.get_default_intent(),
        bot_name=bot_name.result if bot_name.available else None,
        use_websocket=not arparma.find("no_websocket"),
        is_sandbox=arparma.find("is_sandbox"),
        remark=remark.result if remark.available else None,
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_query_matcher.handle()
async def _(session: Uninfo, bot_id: Match[str]) -> None:
    """查询QQ机器人配置"""
    user_id = session.user.id
    online_ids = QQBotConfigManager.get_online_bot_ids()

    if bot_id.available:
        config = await QQBotConfigManager.get_config(user_id, bot_id.result)
        if not config:
            await MessageUtils.build_message(
                f"未找到机器人配置: {bot_id.result}"
            ).finish(reply_to=True)
        await MessageUtils.build_message(
            _format_single_config(config, bot_id.result in online_ids)
        ).finish(reply_to=True)
    else:
        configs = await QQBotConfigManager.get_user_configs(user_id)
        if not configs:
            await MessageUtils.build_message(
                "暂无QQ机器人配置\n使用 'qq配置添加' 命令添加配置"
            ).finish(reply_to=True)
        await MessageUtils.build_message(
            _format_config_list(configs, online_ids)
        ).finish(reply_to=True)


@_update_matcher.handle()
async def _(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    token: Match[str],
    secret: Match[str],
    bot_name: Match[str],
    status: Match[bool],
    remark: Match[str],
) -> None:
    """修改QQ机器人配置"""
    update_fields: dict = {}

    for name, match in [
        ("token", token),
        ("secret", secret),
        ("bot_name", bot_name),
        ("remark", remark),
    ]:
        if match.available:
            update_fields[name] = match.result
    if status.available:
        update_fields["status"] = status.result

    if arparma.find("is_sandbox"):
        update_fields["is_sandbox"] = True
    if arparma.find("no_sandbox"):
        update_fields["is_sandbox"] = False
    if arparma.find("use_websocket"):
        update_fields["use_websocket"] = True
    if arparma.find("no_websocket"):
        update_fields["use_websocket"] = False

    if not update_fields:
        await MessageUtils.build_message(
            "请指定要修改的字段\n"
            "可用选项: --token, --secret, --name, --status, --remark, "
            "--sandbox/--no-sandbox, --ws/--no-ws"
        ).finish(reply_to=True)

    _, msg = await QQBotConfigManager.update_config(
        user_id=session.user.id,
        bot_id=bot_id,
        **update_fields,
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_delete_matcher.handle()
async def _(session: Uninfo, bot_id: str) -> None:
    """删除QQ机器人配置"""
    _, msg = await QQBotConfigManager.delete_config(session.user.id, bot_id)
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
        for f, desc in descriptions.items():
            lines.append(f"  {f}: {desc}")
        await MessageUtils.build_message(
            "\n".join(lines)
        ).finish(reply_to=True)

    if arparma.find("reset"):
        _, msg = await QQBotConfigManager.reset_intent(user_id, bot_id)
        await MessageUtils.build_message(msg).finish(reply_to=True)

    if field.available and value.available:
        _, msg = await QQBotConfigManager.update_intent(
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
        f"机器人 {bot_id} {_format_intent_list(intent, descriptions)}"
    ).finish(reply_to=True)


@_status_matcher.handle()
async def _() -> None:
    """查询QQ适配器状态"""
    status = QQBotConfigManager.get_adapter_status()

    msg_parts = ["QQ适配器状态:\n"]

    connected = status["connected_bots"]
    if connected:
        msg_parts.append(f"已连接机器人 ({len(connected)}个):")
        for bot in connected:
            msg_parts.append(f"  - {bot['id']} ({bot['adapter']})")
    else:
        msg_parts.append("已连接机器人: 无")

    configured = status["configured_bots"]
    if configured:
        msg_parts.append(f"\n已配置机器人 ({len(configured)}个):")
        for bot in configured:
            mode = "WS" if bot["use_websocket"] else "Webhook"
            msg_parts.append(f"  - {bot['id']} [{mode}]")
    else:
        msg_parts.append("\n已配置机器人: 无")

    await MessageUtils.build_message(
        "\n".join(msg_parts)
    ).finish(reply_to=True)
