"""猛鬼公寓 · 游戏服务器（liuying-bot 插件）。

把《猛鬼公寓》(Godot) 的联机服务端整体嵌入 liuying-bot：复用机器人的 FastAPI
驱动、配置系统、数据库与日志，在同一进程、同一端口上多挂一个 WebSocket 路径
``/game`` 对外提供游戏服务，同时提供群内查询指令。

模块划分（新增玩法只需新建子模块并 ``@on_packet("x.y")``，无需改网关）：

* ``core``    协议 / 会话 / 包路由注册表 / WebSocket 网关
* ``models``  账号、令牌、战绩的 ORM 模型（走机器人自带数据库）
* ``auth``    注册、登录、令牌免密重连、个人资料（PBKDF2 加盐）
* ``lobby``   地图大厅、人满自动分线、位置同步与聊天
* ``match``   对局房间、准备、关卡种子下发、战绩结算

各子模块的模块级文档字符串中列有其完整的收发包协议。
"""

from nonebot import on_command
from nonebot.adapters import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from liuying.configs.utils.models import Command, PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils

from . import auth as auth  # 导入即注册包路由
from . import core as core
from . import lobby as lobby
from . import match as match
from .core import hub
from .models import GameAccount

__plugin_meta__ = PluginMetadata(
    name="猛鬼公寓联机服务器",
    description="《猛鬼公寓》Godot 游戏联机服务端：账号登录、大厅自动分线、组队开局",
    usage="""
    猛鬼公寓联机服务器
    指令:
        猛鬼公寓状态          查看在线人数与各大厅分线情况
        猛鬼公寓排行          查看逃脱次数排行榜
        猛鬼公寓踢人 [uid]    [superuser] 断开指定玩家连接
    说明:
        客户端连接地址 ws://<机器人公网地址>:<端口>/game
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="1.1",
        plugin_type=PluginType.NORMAL,
        menu_type="游戏",
        commands=[
            Command(command="猛鬼公寓状态"),
            Command(command="猛鬼公寓排行"),
            Command(command="猛鬼公寓踢人 [uid]"),
        ],
        configs=[
            RegisterConfig(
                key="WS_PATH",
                value="/game",
                help="游戏 WebSocket 接入路径（改动后需重启机器人）",
                default_value="/game",
                type=str,
            ),
            RegisterConfig(
                key="LOBBY_CAPACITY",
                value=30,
                help="单条线路最大同框人数，人满自动开新线",
                default_value=30,
                type=int,
            ),
            RegisterConfig(
                key="LOBBY_MAX_LINES",
                value=20,
                help="单张大厅地图最多可开的线路数",
                default_value=20,
                type=int,
            ),
            RegisterConfig(
                key="LOBBY_TICK_RATE",
                value=10,
                help="大厅位置同步广播频率（Hz）",
                default_value=10,
                type=int,
            ),
            RegisterConfig(
                key="HEARTBEAT_TIMEOUT",
                value=30.0,
                help="连接心跳超时秒数",
                default_value=30.0,
                type=float,
            ),
            RegisterConfig(
                key="TOKEN_TTL_DAYS",
                value=7,
                help="登录令牌有效期（天）",
                default_value=7,
                type=int,
            ),
            RegisterConfig(
                key="MATCH_CAPACITY",
                value=5,
                help="单局对局最大人数",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="MATCH_MAX_SECONDS",
                value=3600.0,
                help="单局最长时长（秒），超时房间会被回收",
                default_value=3600.0,
                type=float,
            ),
            RegisterConfig(
                key="MAX_PACKET_BYTES",
                value=8192,
                help="单个数据包最大字节数，超出直接断开",
                default_value=8192,
                type=int,
            ),
            RegisterConfig(
                key="PACKET_RATE",
                value=60,
                help="单连接每秒最大收包数，超出直接断开",
                default_value=60,
                type=int,
            ),
        ],
    ).to_dict(),
)

_status = on_command(
    "猛鬼公寓状态", aliases={"公寓状态", "猛鬼公寓在线"}, priority=5, block=True
)
_rank = on_command("猛鬼公寓排行", aliases={"公寓排行"}, priority=5, block=True)
_kick = on_command("猛鬼公寓踢人", permission=SUPERUSER, priority=5, block=True)


@_status.handle()
async def _() -> None:
    """群内查询服务器状态。"""
    sessions = hub.all()
    lines = [
        f"【猛鬼公寓】接入 {core.config.game_ws_path}",
        f"连接数 {len(sessions)}　已登录 {hub.online_count} 人",
    ]
    for lb in lobby.manager.lobbies.values():
        parts = [f"{i}线 {lb.lines[i].count}/{lb.capacity}" for i in sorted(lb.lines)]
        lines.append(f"· {lb.name}：{'、'.join(parts) if parts else '空'}")
    if match.matches:
        playing = sum(1 for m in match.matches.values() if m.started)
        lines.append(f"对局 {len(match.matches)} 个（进行中 {playing} 个）")
    await MessageUtils.build_message("\n".join(lines)).finish(reply_to=True)


@_rank.handle()
async def _() -> None:
    """群内查询逃脱排行榜。"""
    top = await GameAccount.leaderboard(10)
    if not top:
        await MessageUtils.build_message("还没有人留下战绩。").finish(reply_to=True)
    rows = ["【猛鬼公寓 · 逃脱排行】"]
    for i, acc in enumerate(top, 1):
        best = f"{acc.best_time:.1f}s" if acc.best_time >= 0 else "—"
        rows.append(f"{i}. {acc.nickname}　逃脱 {acc.escapes} 次　最快 {best}")
    await MessageUtils.build_message("\n".join(rows)).finish(reply_to=True)


@_kick.handle()
async def _(args: Message = CommandArg()) -> None:
    """管理员踢人下线。

    参数:
        args: 指令参数，玩家 uid。
    """
    arg = args.extract_plain_text().strip()
    if not arg.isdigit():
        await MessageUtils.build_message("请提供要踢下线的玩家 uid。").finish(
            reply_to=True
        )
    if (session := hub.by_uid(int(arg))) is None:
        await MessageUtils.build_message(f"uid {arg} 当前不在线。").finish(
            reply_to=True
        )
    await session.close("管理员操作")
    await MessageUtils.build_message(f"已断开 uid {arg} 的连接。").finish(reply_to=True)
