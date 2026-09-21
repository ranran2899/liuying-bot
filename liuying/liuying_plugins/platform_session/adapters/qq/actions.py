"""QQ 官方适配器统一动作执行"""

from datetime import timedelta

from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.models import SetMemberMuteState

from ...action import ActionExecutor as BaseActionExecutor
from ...action import resolve_scene
from ...constraint import SupportAdapter
from ...model import Member, Scene, Session


class ActionExecutor(BaseActionExecutor):
    """QQ 官方适配器动作执行器，官方接口不支持踢出成员"""

    async def recall(
        self, bot: Bot, target: Scene | Session, message_id: str
    ) -> bool:
        scene = resolve_scene(target)
        if scene.is_private:
            await bot.delete_c2c_message(
                openid=scene.id, message_id=message_id
            )
        elif scene.is_group:
            await bot.delete_group_message(
                group_openid=scene.id, message_id=message_id
            )
        elif scene.is_channel:
            await bot.delete_message(
                channel_id=scene.id, message_id=message_id
            )
        else:
            raise NotImplementedError
        return True

    async def mute(
        self, bot: Bot, member: Member, scene: Scene, duration: timedelta
    ) -> bool:
        if scene.is_group:
            await bot.set_group_members_mute(
                group_id=scene.id,
                members=[
                    SetMemberMuteState(
                        op="add",
                        member_openid=member.id,
                        mute_expire_at=duration,
                    )
                ],
            )
            return True
        guild_id = scene.parent.id if scene.is_channel and scene.parent else None
        if scene.is_guild:
            guild_id = scene.id
        if guild_id:
            await bot.patch_guild_member_mute(
                guild_id=guild_id,
                user_id=member.id,
                mute_seconds=duration,
            )
            return True
        raise NotImplementedError

    async def unmute(self, bot: Bot, member: Member, scene: Scene) -> bool:
        if scene.is_group:
            await bot.set_group_members_mute(
                group_id=scene.id,
                members=[SetMemberMuteState(op="del", member_openid=member.id)],
            )
            return True
        guild_id = scene.parent.id if scene.is_channel and scene.parent else None
        if scene.is_guild:
            guild_id = scene.id
        if guild_id:
            await bot.patch_guild_member_mute(
                guild_id=guild_id,
                user_id=member.id,
                mute_seconds=timedelta(0),
            )
            return True
        raise NotImplementedError


executor = ActionExecutor(SupportAdapter.qq)
