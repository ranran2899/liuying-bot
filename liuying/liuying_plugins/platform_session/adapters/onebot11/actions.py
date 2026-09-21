"""OneBot V11 统一动作执行"""

from datetime import timedelta

from nonebot.adapters.onebot.v11 import Bot

from ...action import ActionExecutor as BaseActionExecutor
from ...constraint import SupportAdapter
from ...model import Member, Scene, Session


class ActionExecutor(BaseActionExecutor):
    """OneBot V11 动作执行器"""

    async def recall(
        self, bot: Bot, target: Scene | Session, message_id: str
    ) -> bool:
        await bot.delete_msg(message_id=int(message_id))
        return True

    async def mute(
        self, bot: Bot, member: Member, scene: Scene, duration: timedelta
    ) -> bool:
        if not scene.is_group:
            raise NotImplementedError
        await bot.set_group_ban(
            group_id=int(scene.id),
            user_id=int(member.id),
            duration=max(1, int(duration.total_seconds())),
        )
        return True

    async def unmute(self, bot: Bot, member: Member, scene: Scene) -> bool:
        if not scene.is_group:
            raise NotImplementedError
        await bot.set_group_ban(
            group_id=int(scene.id), user_id=int(member.id), duration=0
        )
        return True

    async def kick(self, bot: Bot, member: Member, scene: Scene) -> bool:
        if not scene.is_group:
            raise NotImplementedError
        await bot.set_group_kick(group_id=int(scene.id), user_id=int(member.id))
        return True


executor = ActionExecutor(SupportAdapter.onebot11)
