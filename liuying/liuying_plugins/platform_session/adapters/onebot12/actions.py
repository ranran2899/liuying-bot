"""OneBot V12 统一动作执行"""

from nonebot.adapters.onebot.v12 import Bot

from ...action import ActionExecutor as BaseActionExecutor
from ...constraint import SupportAdapter
from ...model import Scene, Session


class ActionExecutor(BaseActionExecutor):
    """OneBot V12 动作执行器

    OneBot V12 标准协议未定义禁言、踢出等成员管理动作，
    仅有 NoneBot 已声明的 38 个标准 API，管理类操作不在其中，
    因此这里只实现标准的消息撤回，其余动作保持不支持。
    """

    async def recall(
        self, bot: Bot, target: Scene | Session, message_id: str
    ) -> bool:
        await bot.delete_message(message_id=message_id)
        return True


executor = ActionExecutor(SupportAdapter.onebot12)
