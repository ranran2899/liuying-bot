from datetime import datetime

from fastapi import APIRouter
import nonebot
from nonebot import on_message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot_plugin_alconna import At, Hyper, Image, Text, UniMsg
from nonebot_plugin_uninfo import Uninfo
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from liuying.models._group.group_member_info import GroupInfoUser
from liuying.utils.depends import UserName

from ....config import AVA_URL
from .model import Message, MessageItem

driver = nonebot.get_driver()

ws_conn: WebSocket | None = None

# 群成员名缓存，限制最大群数避免内存泄漏
ID2NAME: dict[str, dict[str, str]] = {}
ID2NAME_MAX_GROUPS = 100

ID_LIST: list = []

ws_router = APIRouter()


matcher = on_message(block=False, priority=1, rule=lambda: bool(ws_conn))


@driver.on_shutdown
async def _():
    if ws_conn and ws_conn.client_state == WebSocketState.CONNECTED:
        await ws_conn.close()


@ws_router.websocket("/chat")
async def _(websocket: WebSocket):
    """聊天 WebSocket 端点

    仅允许单个客户端连接，新连接覆盖旧连接。
    """
    global ws_conn
    await websocket.accept()
    # 若已有连接，先关闭旧连接
    if ws_conn and ws_conn.client_state == WebSocketState.CONNECTED:
        await ws_conn.close()
    ws_conn = websocket
    try:
        while websocket.client_state == WebSocketState.CONNECTED:
            await websocket.receive()
    except WebSocketDisconnect:
        if ws_conn is websocket:
            ws_conn = None


async def message_handle(
    message: UniMsg,
    group_id: str | None,
):
    """处理消息段，转换为前端可渲染的消息项列表

    参数:
        message: UniMsg 消息对象
        group_id: 群 ID，私聊为 None

    返回:
        list[MessageItem]: 消息项列表
    """
    time = str(datetime.now().replace(microsecond=0))
    messages = []
    for m in message:
        if isinstance(m, Text | str):
            messages.append(MessageItem(type="text", msg=str(m), time=time))
        elif isinstance(m, Image):
            if m.url:
                messages.append(MessageItem(type="img", msg=m.url, time=time))
        elif isinstance(m, At):
            if group_id:
                if m.target == "0":
                    uname = "全体成员"
                else:
                    uname = await _resolve_at_name(group_id, m.target)
                messages.append(MessageItem(type="at", msg=f"@{uname}", time=time))
        elif isinstance(m, Hyper):
            messages.append(MessageItem(type="text", msg="[分享消息]", time=time))
    return messages


async def _resolve_at_name(group_id: str, target: str) -> str:
    """解析 @ 目标的昵称，带缓存

    参数:
        group_id: 群 ID
        target: 被 @ 的用户 ID

    返回:
        str: 用户昵称，未找到时返回原始 ID
    """
    global ID2NAME
    # 清理过期缓存
    if len(ID2NAME) > ID2NAME_MAX_GROUPS:
        for key in list(ID2NAME.keys())[:20]:
            del ID2NAME[key]
    if group_id not in ID2NAME:
        ID2NAME[group_id] = {}
    if target in ID2NAME[group_id]:
        return ID2NAME[group_id][target]
    group_user = await GroupInfoUser.filter(
        user_id=target, group_id=group_id
    ).first()
    if group_user:
        ID2NAME[group_id][target] = group_user.user_name
        return group_user.user_name
    return target


@matcher.handle()
async def _(
    message: UniMsg, event: MessageEvent, session: Uninfo, uname: str = UserName()
):
    """消息处理器，转发消息到 WebSocket 客户端"""
    global ws_conn, ID2NAME, ID_LIST
    if ws_conn and ws_conn.client_state == WebSocketState.CONNECTED:
        msg_id = event.message_id
        if msg_id in ID_LIST:
            return
        ID_LIST.append(msg_id)
        if len(ID_LIST) > 50:
            ID_LIST = ID_LIST[40:]
        gid = session.group.id if session.group else None
        messages = await message_handle(message, gid)
        data = Message(
            object_id=gid or session.user.id,
            user_id=session.user.id,
            group_id=gid,
            message=messages,
            name=uname,
            ava_url=AVA_URL.format(session.user.id),
        )
        await ws_conn.send_json(data.to_dict())
