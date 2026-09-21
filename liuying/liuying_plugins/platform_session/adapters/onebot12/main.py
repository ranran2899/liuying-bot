"""OneBot V12 统一会话抓取"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta

from nonebot.adapters import Event
from nonebot.adapters.onebot.v12 import Bot
from nonebot.adapters.onebot.v12.event import (
    ChannelCreateEvent,
    ChannelDeleteEvent,
    ChannelMemberDecreaseEvent,
    ChannelMemberIncreaseEvent,
    ChannelMessageDeleteEvent,
    ChannelMessageEvent,
    FriendDecreaseEvent,
    FriendIncreaseEvent,
    GroupMemberDecreaseEvent,
    GroupMemberIncreaseEvent,
    GroupMessageDeleteEvent,
    GroupMessageEvent,
    GuildMemberDecreaseEvent,
    GuildMemberIncreaseEvent,
    PrivateMessageDeleteEvent,
    PrivateMessageEvent,
)
from nonebot.exception import ActionFailed

from ...constraint import SupportAdapter, SupportScope
from ...fetch import BasicInfo
from ...fetch import InfoFetcher as BaseInfoFetcher
from ...model import Member, MuteInfo, Scene, SceneType, User
from ...util import safe_call


class InfoFetcher(BaseInfoFetcher):
    """OneBot V12 会话信息抓取器"""

    def get_session_id(self, event: Event) -> str:
        if isinstance(event, (GuildMemberDecreaseEvent, GuildMemberIncreaseEvent)):
            return f"{event.get_session_id()}_{event.operator_id}"
        return event.get_session_id()

    def extract_user(self, data: dict) -> User:
        return User(
            id=data["user_id"],
            name=data["name"],
            nick=data["nickname"],
        )

    def extract_scene(self, data: dict) -> Scene:
        if "group_id" in data:
            return Scene(
                id=data["group_id"],
                type=SceneType.GROUP,
                name=data.get("group_name"),
            )
        if "guild_id" in data:
            if "channel_id" in data:
                return Scene(
                    id=data["channel_id"],
                    type=SceneType.CHANNEL_TEXT,
                    name=data["channel_name"],
                    parent=Scene(
                        id=data["guild_id"],
                        type=SceneType.GUILD,
                        name=data.get("guild_name"),
                    ),
                )
            return Scene(
                id=data["guild_id"],
                type=SceneType.GUILD,
                name=data.get("guild_name"),
            )
        return Scene(
            id=data["user_id"],
            type=SceneType.PRIVATE,
        )

    def extract_member(self, data: dict, user: User | None) -> Member | None:
        if "group_id" not in data or "guild_id" not in data:
            return None
        mute = (
            MuteInfo(muted=True, duration=timedelta(seconds=data["mute_duration"]))
            if "mute_duration" in data
            else None
        )
        if user:
            return Member(user=user, nick=data["displayname"], mute=mute)
        return Member(
            User(
                id=data["user_id"],
                name=data["name"],
                nick=data.get("nickname"),
            ),
            nick=data["displayname"],
            mute=mute,
        )

    async def query_user(self, bot: Bot, user_id: str) -> User | None:
        if user_id == str(bot.self_id):
            info = await bot.get_self_info()
        else:
            info = await bot.get_user_info(user_id=user_id)
        data = {
            "user_id": info["user_id"],
            "name": info["user_name"],
            "nickname": info.get("user_remark", info["user_displayname"]),
        }
        return self.extract_user(data)

    async def query_scene(
        self,
        bot: Bot,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        if scene_type == SceneType.PRIVATE:
            if user := await self.query_user(bot, scene_id):
                data = {
                    "user_id": user.id,
                    "name": user.name,
                    "nickname": user.nick,
                }
                return self.extract_scene(data)
        elif scene_type == SceneType.GROUP:
            group_info = await bot.get_group_info(group_id=scene_id)
            data = {
                "group_id": group_info["group_id"],
                "group_name": group_info["group_name"],
            }
            return self.extract_scene(data)
        elif scene_type == SceneType.GUILD:
            guild_info = await bot.get_guild_info(guild_id=scene_id)
            data = {
                "guild_id": guild_info["guild_id"],
                "guild_name": guild_info["guild_name"],
            }
            return self.extract_scene(data)
        return None

    async def query_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        if scene_type == SceneType.GROUP:
            member_info = await bot.get_group_member_info(
                group_id=parent_scene_id, user_id=user_id
            )
            data = {
                "group_id": parent_scene_id,
                "user_id": member_info["user_id"],
                "name": member_info["user_name"],
                "displayname": member_info["user_displayname"],
            }
            return self.extract_member(data, None)
        if scene_type == SceneType.GUILD:
            member_info = await bot.get_guild_member_info(
                guild_id=parent_scene_id, user_id=user_id
            )
            data = {
                "guild_id": parent_scene_id,
                "user_id": member_info["user_id"],
                "name": member_info["user_name"],
                "displayname": member_info["user_displayname"],
            }
            return self.extract_member(data, None)
        return None

    async def query_users(self, bot: Bot) -> AsyncGenerator[User]:
        friends = await bot.get_friend_list()
        for friend in friends:
            data = {
                "user_id": friend["user_id"],
                "name": friend["user_name"],
                "nickname": friend["user_remark"],
            }
            yield self.extract_user(data)

    async def query_scenes(
        self,
        bot: Bot,
        scene_type: SceneType | None = None,
        *,
        parent_scene_id: str | None = None
    ) -> AsyncGenerator[Scene]:
        if scene_type is None or scene_type == SceneType.PRIVATE:
            async for user in self.query_users(bot):
                data = {
                    "user_id": user.id,
                    "name": user.name,
                    "avatar": user.avatar,
                }
                yield self.extract_scene(data)
        if scene_type is None or scene_type == SceneType.GROUP:
            groups = await bot.get_group_list()
            for group in groups:
                data = {
                    "group_id": group["group_id"],
                    "group_name": group["group_name"],
                }
                yield self.extract_scene(data)
        if scene_type is None or scene_type >= SceneType.GUILD:
            guilds = await bot.get_guild_list()
            for guild in guilds:
                if parent_scene_id is not None and guild["guild_id"] != parent_scene_id:
                    continue
                data = {
                    "guild_id": guild["guild_id"],
                    "guild_name": guild["guild_name"],
                }
                if scene_type is None or scene_type == SceneType.GUILD:
                    yield self.extract_scene(data)
                if scene_type == SceneType.GUILD:
                    continue
                channels = await bot.get_channel_list(guild_id=guild["guild_id"])
                for channel in channels:
                    data = {
                        "guild_id": guild["guild_id"],
                        "guild_name": guild["guild_name"],
                        "channel_id": channel["channel_id"],
                        "channel_name": channel["channel_name"],
                    }
                    yield self.extract_scene(data)

    async def query_members(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str
    ) -> AsyncGenerator[Member]:
        if scene_type == SceneType.GROUP:
            group_members = await bot.get_group_member_list(group_id=parent_scene_id)
            for member in group_members:
                data = {
                    "group_id": parent_scene_id,
                    "user_id": member["user_id"],
                    "name": member["user_name"],
                    "displayname": member["user_displayname"],
                }
                yield self.extract_member(data, None)
        elif scene_type == SceneType.GUILD:
            guild_members = await bot.get_guild_member_list(guild_id=parent_scene_id)
            for member in guild_members:
                data = {
                    "guild_id": parent_scene_id,
                    "user_id": member["user_id"],
                    "name": member["user_name"],
                    "displayname": member["user_displayname"],
                }
                yield self.extract_member(data, None)

    def supply_self(self, bot: Bot) -> BasicInfo:
        return {
            "self_id": str(bot.self_id),
            "adapter": SupportAdapter.onebot12,
            "scope": SupportScope.ensure_ob12(bot.platform),
        }


fetcher = InfoFetcher(SupportAdapter.onebot12)


@fetcher.supply
async def _(
    bot: Bot,
    event: PrivateMessageDeleteEvent
    | PrivateMessageEvent
    | FriendDecreaseEvent
    | FriendIncreaseEvent,
) -> dict:
    try:
        user_info = await bot.get_user_info(user_id=event.user_id)
    except ActionFailed:
        user_info = {}
    return {
        "user_id": event.user_id,
        "name": user_info.get("user_name"),
        "nickname": user_info.get("user_remark"),
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: GroupMemberDecreaseEvent
    | GroupMemberIncreaseEvent
    | GroupMessageDeleteEvent
    | GroupMessageEvent,
) -> dict:
    group_info, user_info, member_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(bot.get_user_info(user_id=event.user_id), {}),
        safe_call(
            bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id),
            {},
        ),
    )
    return {
        "group_id": event.group_id,
        "group_name": group_info.get("group_name"),
        "user_id": event.user_id,
        "name": user_info.get("user_name"),
        "nickname": user_info.get("user_remark"),
        "displayname": member_info.get("user_displayname"),
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: ChannelMemberDecreaseEvent
    | ChannelMemberIncreaseEvent
    | ChannelMessageDeleteEvent
    | ChannelMessageEvent,
) -> dict:
    guild_info, channel_info, user_info, member_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.guild_id), {}),
        safe_call(
            bot.get_channel_info(guild_id=event.guild_id, channel_id=event.channel_id),
            {},
        ),
        safe_call(
            bot.get_guild_member_info(guild_id=event.guild_id, user_id=event.user_id),
            {},
        ),
        safe_call(
            bot.get_channel_member_info(
                guild_id=event.guild_id,
                channel_id=event.channel_id,
                user_id=event.user_id,
            ),
            {},
        ),
    )
    return {
        "guild_id": event.guild_id,
        "guild_name": guild_info.get("guild_name"),
        "channel_id": event.channel_id,
        "channel_name": channel_info.get("channel_name"),
        "user_id": event.user_id,
        "name": user_info.get("user_name"),
        "nickname": user_info.get("user_displayname"),
        "displayname": member_info.get("user_displayname"),
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: ChannelCreateEvent | ChannelDeleteEvent,
) -> dict:
    guild_info, channel_info, user_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.guild_id), {}),
        safe_call(
            bot.get_channel_info(guild_id=event.guild_id, channel_id=event.channel_id),
            {},
        ),
        safe_call(
            bot.get_guild_member_info(
                guild_id=event.guild_id, user_id=event.operator_id
            ),
            {},
        ),
    )
    return {
        "guild_id": event.guild_id,
        "guild_name": guild_info.get("guild_name"),
        "channel_id": event.channel_id,
        "channel_name": channel_info.get("channel_name"),
        "user_id": event.operator_id,
        "name": user_info.get("user_name"),
        "nickname": user_info.get("user_displayname"),
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: GuildMemberDecreaseEvent | GuildMemberIncreaseEvent,
) -> dict:
    guild_info, user_info, operator_info = await asyncio.gather(
        safe_call(bot.get_guild_info(guild_id=event.guild_id), {}),
        safe_call(
            bot.get_guild_member_info(guild_id=event.guild_id, user_id=event.user_id),
            {},
        ),
        safe_call(
            bot.get_guild_member_info(
                guild_id=event.guild_id, user_id=event.operator_id
            ),
            {},
        ),
    )
    return {
        "guild_id": event.guild_id,
        "guild_name": guild_info.get("guild_name"),
        "user_id": event.user_id,
        "name": user_info.get("user_name"),
        "nickname": user_info.get("user_displayname"),
        "operator": {
            "guild_id": event.guild_id,
            "guild_name": guild_info.get("guild_name"),
            "user_id": event.operator_id,
            "name": operator_info.get("user_name"),
            "nickname": operator_info.get("user_displayname"),
        },
    }
