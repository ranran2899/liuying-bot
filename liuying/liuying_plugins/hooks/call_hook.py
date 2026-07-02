from typing import Any

from nonebot.adapters import Bot, Message

from liuying.utils.log import logger
from liuying.utils.manager.message_manager import MessageManager

LOG_COMMAND = "MessageHook"


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
    if exception or api != "send_msg":
        return

    if not result:
        return

    user_id = data.get("user_id")
    message_id = result.get("message_id")

    if not (user_id and message_id):
        return

    try:
        MessageManager.add(str(user_id), str(message_id))
        logger.debug(
            f"收集消息id，user_id: {user_id}, msg_id: {message_id}", LOG_COMMAND
        )
    except Exception as e:
        logger.warning(
            f"收集消息id发生错误...data: {data}, result: {result}", LOG_COMMAND, e=e
        )
