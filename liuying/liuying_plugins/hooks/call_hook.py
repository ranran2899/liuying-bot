from typing import Any

from nonebot.adapters import Bot, Message

from liuying.utils.log import logger
from liuying.utils.manager.message_manager import MessageManager

LOG_COMMAND = "MessageHook"

QQ_MSG_APIS = {"post_c2c_messages", "post_group_messages"}
"""QQ官方适配器发送消息的API名"""


def replace_message(message: Message) -> str:
    """替换消息内容为字符串

    参数:
        message: 消息对象

    返回:
        str: 替换后的字符串
    """
    result_parts = []
    for msg in message:
        match msg:
            case str():
                result_parts.append(msg)
            case _ if msg.type == "at":
                result_parts.append(f"@{msg.data['qq']}")
            case _ if msg.type == "image":
                result_parts.append("[image]")
            case _ if msg.type == "record":
                result_parts.append("[record]")
            case _ if msg.type == "face":
                result_parts.append(f"[face:{msg.data['id']}]")
            case _ if msg.type == "reply":
                pass
            case _:
                result_parts.append(str(msg))
    return "".join(result_parts)


@Bot.on_called_api
async def handle_api_result(
    bot: Bot, exception: Exception | None, api: str, data: dict[str, Any], result: Any
):
    """处理API调用结果"""
    if exception or not result:
        return
    if api == "send_msg":
        user_id = data.get("user_id")
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not (user_id and message_id):
            return
        MessageManager.add(str(user_id), str(message_id))
        logger.debug(
            f"收集消息id，user_id: {user_id}, msg_id: {message_id}", LOG_COMMAND
        )
    elif api in QQ_MSG_APIS and (msg_id := result.id):
        if openid := data.get("openid") or data.get("group_openid"):
            MessageManager.add(openid, msg_id, openid)
            logger.debug(
                f"收集消息id，openid: {openid}, msg_id: {msg_id}", LOG_COMMAND
            )
