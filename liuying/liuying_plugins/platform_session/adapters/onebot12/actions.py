"""OneBot V12 统一动作执行"""

from datetime import timedelta

from nonebot.adapters.onebot.v12 import Bot

from ...action import ActionExecutor as BaseActionExecutor
from ...constraint import SupportAdapter
from ...model import Member, Scene, Session


class ActionExecutor(BaseActionExecutor):
    """OneBot V12 动作执行器"""

    async def recall(
        self, bot: Bot, target: Scene | Session, message_id: str
    ) -> bool:
        await bot.delete_message(message_id=message_id)
        return True

    async def mute(
        self, bot: Bot, member: Member, scene: Scene, duration: timedelta
    ) -> bool:
        seconds = max(1, int(duration.total_seconds()))
        if scene.is_group:
            await bot.mute_group_member(
                group_id=scene.id, user_id=member.id, duration=seconds
            )
            return True
        if scene.is_channel and scene.parent:
            await bot.mute_channel_member(
                guild_id=scene.parent.id,
                channel_id=scene.id,
                user_id=member.id,
                duration=seconds,
            )
            return True
        raise NotImplementedError

    async def unmute(self, bot: Bot, member: Member, scene: Scene) -> bool:
        if scene.is_group:
            await bot.undo_group_member_mute(
                group_id=scene.id, user_id=member.id
            )
            return True
        if scene.is_channel and scene.parent:
            await bot.undo_channel_member_mute(
                guild_id=scene.parent.id,
                channel_id=scene.id,
                user_id=member.id,
            )
            return True
        raise NotImplementedError

    async def kick(self, bot: Bot, member: Member, scene: Scene) -> bool:
        if scene.is_group:
            await bot.remove_group_member(
                group_id=scene.id, user_id=member.id
            )
            return True
        if scene.is_channel and scene.parent:
            await bot.remove_channel_member(
                guild_id=scene.parent.id,
                channel_id=scene.id,
                user_id=member.id,
            )
            return True
        raise NotImplementedError


executor = ActionExecutor(SupportAdapter.onebot12)
