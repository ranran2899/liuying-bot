"""QQ 官方适配器统一会话抓取"""

import asyncio
from collections.abc import AsyncGenerator

from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    ChannelEvent,
    DirectMessageCreateEvent,
    DirectMessageDeleteEvent,
    Event,
    GroupMessageCreateEvent,
    GuildEvent,
    GuildMemberEvent,
    GuildMessageEvent,
    InteractionCreateEvent,
    MessageDeleteEvent,
)
from nonebot.exception import ActionFailed

from ...constraint import SupportAdapter, SupportScope
from ...fetch import BasicInfo
from ...fetch import InfoFetcher as BaseInfoFetcher
from ...model import Member, Role, Scene, SceneType, User
from ...util import safe_call

ROLES = {
    "4": ("OWNER", 640, "创建者"),
    "2": ("ADMINISTRATOR", 10, "管理员"),
    "5": ("CHANNEL_ADMINISTRATOR", 8, "子频道管理员"),
    "1": ("MEMBER", 1, "成员"),
}

GROUP_ROLES = {
    "owner": ("OWNER", 640, "群主"),
    "admin": ("ADMINISTRATOR", 10, "管理员"),
    "member": ("MEMBER", 1, "成员"),
}

CHANNEL_TYPE = {
    -1: SceneType.PRIVATE,
    0: SceneType.CHANNEL_TEXT,
    2: SceneType.CHANNEL_VOICE,
    4: SceneType.CHANNEL_CATEGORY,
}


class InfoFetcher(BaseInfoFetcher):
    """QQ 官方适配器会话信息抓取器"""

    def get_session_id(self, event: Event) -> str:
        if isinstance(event, MessageDeleteEvent):
            return f"{event.get_session_id()}_{event.op_user.id}"
        if isinstance(event, GuildEvent):
            return f"guild_{event.id}_{event.op_user_id}"
        if isinstance(event, GuildMemberEvent):
            return f"{event.get_session_id()}_{event.op_user_id}"
        if isinstance(event, ChannelEvent):
            return f"channel_{event.guild_id}_{event.id}_{event.op_user_id}"
        return event.get_session_id()

    def extract_user(self, data: dict) -> User:
        return User(
            id=data["user_id"],
            name=data["name"],
            avatar=data["avatar"],
        )

    def extract_scene(self, data: dict) -> Scene:
        if "group_id" in data:
            return Scene(
                id=data["group_id"],
                type=SceneType.GROUP,
            )
        if "guild_id" in data:
            if "channel_id" in data:
                return Scene(
                    id=data["channel_id"],
                    name=data.get("channel_name"),
                    type=CHANNEL_TYPE.get(
                        data.get("channel_type", 0), SceneType.CHANNEL_TEXT
                    ),
                    parent=Scene(
                        id=data["guild_id"],
                        name=data.get("guild_name"),
                        type=SceneType.GUILD,
                        avatar=data.get("guild_avatar"),
                    ),
                )
            return Scene(
                id=data["guild_id"],
                name=data.get("guild_name"),
                type=SceneType.GUILD,
                avatar=data.get("guild_avatar"),
            )
        return Scene(
            id=data["user_id"],
            type=SceneType.PRIVATE,
            name=data["name"],
            avatar=data["avatar"],
        )

    def extract_member(self, data: dict, user: User | None) -> Member | None:
        if "group_id" in data:
            role = data.get("role")
            roles = [Role(*GROUP_ROLES[role])] if role in GROUP_ROLES else []
            if user:
                return Member(user, nick=data["nickname"], roles=roles)
            return Member(
                User(
                    id=data["user_id"],
                    name=data["name"],
                    avatar=data.get("avatar"),
                ),
                nick=data["nickname"],
                roles=roles,
            )
        if "guild_id" in data:
            if user:
                return Member(
                    user,
                    nick=data["nickname"],
                    roles=data.get("roles", []),
                    joined_at=data.get("joined_at"),
                )
            return Member(
                User(
                    id=data["user_id"],
                    name=data["name"],
                    avatar=data.get("avatar"),
                ),
                nick=data["nickname"],
                roles=data.get("roles", []),
                joined_at=data.get("joined_at"),
            )
        return None

    async def query_user(self, bot: Bot, user_id: str) -> User | None:
        if user_id == bot.self_id:
            info = await bot.me()
            return User(
                id=info.id,
                name=info.username,
                avatar=info.avatar,
            )
        return User(
            id=user_id,
            name="",
            avatar=f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{user_id}/640",
        )

    async def query_scene(
        self,
        bot: Bot,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        if scene_type == SceneType.GUILD:
            guild = await bot.get_guild(guild_id=scene_id)
            return Scene(
                id=guild.id, type=SceneType.GUILD, name=guild.name, avatar=guild.icon
            )
        if scene_type >= SceneType.CHANNEL_TEXT:
            channel = await bot.get_channel(channel_id=scene_id)
            guild = await bot.get_guild(guild_id=channel.guild_id)
            return Scene(
                id=channel.id,
                type=CHANNEL_TYPE.get(channel.type, SceneType.CHANNEL_TEXT),
                name=channel.name,
                parent=Scene(
                    id=guild.id,
                    type=SceneType.GUILD,
                    name=guild.name,
                    avatar=guild.icon,
                ),
            )
        return None

    async def query_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        if scene_type >= SceneType.GUILD:
            member = await bot.get_member(guild_id=parent_scene_id, user_id=user_id)
            return Member(
                User(
                    id=member.user.id if member.user else user_id,
                    name=(member.user.username if member.user else "") or "",
                    avatar=member.user.avatar if member.user else None,
                ),
                nick=member.nick,
                roles=await _handle_roles(
                    bot, parent_scene_id, None, member.roles or []
                ),
                joined_at=member.joined_at,
            )
        if scene_type == SceneType.GROUP:
            return Member(
                User(
                    id=user_id,
                    name="",
                    avatar=f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{user_id}/640",
                ),
                nick="",
            )
        return None

    def query_users(self, bot: Bot) -> AsyncGenerator[User]:
        raise NotImplementedError

    async def query_scenes(
        self,
        bot: Bot,
        scene_type: SceneType | None = None,
        *,
        parent_scene_id: str | None = None
    ) -> AsyncGenerator[Scene]:
        if scene_type is not None and scene_type < SceneType.GUILD:
            return
        guilds = await bot.guilds(limit=640)
        while guilds:
            for guild in guilds:
                if parent_scene_id is None or guild.id == parent_scene_id:
                    _guild = Scene(
                        id=guild.id,
                        type=SceneType.GUILD,
                        name=guild.name,
                        avatar=guild.icon,
                    )
                    if scene_type is None or scene_type == SceneType.GUILD:
                        yield _guild
                    if scene_type == SceneType.GUILD:
                        continue
                    channels = await bot.get_channels(guild_id=guild.id)
                    for channel in channels:
                        yield Scene(
                            id=channel.id,
                            type=CHANNEL_TYPE.get(channel.type, SceneType.CHANNEL_TEXT),
                            name=channel.name,
                            parent=_guild,
                        )
            if len(guilds) < 640:
                break
            guilds = await bot.guilds(limit=640, after=guilds[-1].id)

    def query_members(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str
    ) -> AsyncGenerator[Member]:
        raise NotImplementedError

    def supply_self(self, bot: Bot) -> BasicInfo:
        return {
            "self_id": str(bot.self_id),
            "adapter": SupportAdapter.qq,
            "scope": SupportScope.qq_api,
        }


fetcher = InfoFetcher(SupportAdapter.qq)


async def _handle_roles(
    bot: Bot, guild_id: str, channel_id: str | None, roles: list[str]
) -> list[Role]:
    """将官方接口的角色id列表转换为统一角色信息"""
    if not roles:
        return [Role(*ROLES["1"])]
    res: list[tuple[str, int, str]] = []
    try:
        resp = await bot.get_guild_roles(guild_id=guild_id)
        roles_info = {r.id: r.name for r in resp.roles}
    except ActionFailed:
        roles_info = {}
    for role in roles:
        if role in ROLES:
            res.append(ROLES[role])
            continue
        if not channel_id:
            res.append(("MEMBER", 1, roles_info.get(role, "成员")))
            continue
        try:
            perm = await bot.get_channel_roles_permissions(
                channel_id=channel_id, role_id=role
            )
            if perm.permissions & 0b10 == 0b10:
                res.append(("MEMBER", perm.permissions, roles_info.get(role, "成员")))
            else:
                res.append(
                    (
                        "CHANNEL_ADMINISTRATOR",
                        perm.permissions,
                        roles_info.get(role, "子频道管理员"),
                    )
                )
        except ActionFailed:
            res.append(("MEMBER", 1, roles_info.get(role, "成员")))
    if not res:
        return [Role(*ROLES["1"])]
    return [Role(*r) for r in res]


@fetcher.supply
async def _(bot: Bot, event: InteractionCreateEvent) -> dict:
    if event.chat_type == 2:
        return {
            "user_id": event.user_openid,
            "name": "",
            "nickname": "",
            "avatar": f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{event.user_openid}/640",
        }
    if event.chat_type == 1:
        return {
            "user_id": event.group_member_openid,
            "name": "",
            "nickname": "",
            "avatar": f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{event.group_member_openid}/640",
            "group_id": event.group_openid,
        }
    base: dict = {
        "user_id": event.data.resolved.user_id,
        "name": "",
        "nickname": "",
        "avatar": None,
        "guild_id": event.guild_id,
        "channel_id": event.channel_id,
    }
    member, guild, channel = await asyncio.gather(
        safe_call(
            bot.get_member(
                guild_id=event.guild_id, user_id=event.data.resolved.user_id
            ),
            None,
        ),
        safe_call(bot.get_guild(guild_id=event.guild_id), None),
        safe_call(bot.get_channel(channel_id=event.channel_id), None),
    )
    if member:
        base["name"] = (member.user.username if member.user else "") or ""
        base["nickname"] = member.nick or ""
        base["roles"] = await _handle_roles(
            bot, event.guild_id, event.channel_id, member.roles or []
        )
        base["joined_at"] = member.joined_at
    if guild:
        base["guild_name"] = guild.name
        base["guild_avatar"] = guild.icon
    if channel:
        base["channel_name"] = channel.name
        base["channel_type"] = channel.type
    return base


@fetcher.supply
async def _(bot: Bot, event: C2CMessageCreateEvent) -> dict:
    return {
        "user_id": event.author.user_openid,
        "name": event.author.username,
        "nickname": "",
        "avatar": f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{event.author.user_openid}/640",
    }


@fetcher.supply
async def _(bot: Bot, event: GroupMessageCreateEvent) -> dict:
    return {
        "user_id": event.author.member_openid,
        "name": event.author.username,
        "nickname": "",
        "role": getattr(event.author, "member_role", None),
        "avatar": f"https://q.qlogo.cn/qqapp/{bot.bot_info.id}/{event.author.member_openid}/640",
        "group_id": event.group_openid,
    }


@fetcher.supply_wildcard
async def _(bot: Bot, event: Event) -> dict:
    if isinstance(event, GuildMessageEvent):
        base: dict = {
            "user_id": event.author.id,
            "name": event.author.username or "",
            "nickname": "",
            "avatar": event.author.avatar,
            "guild_id": event.guild_id,
            "channel_id": event.channel_id,
        }
        guild, channel = await asyncio.gather(
            safe_call(bot.get_guild(guild_id=event.guild_id), None),
            safe_call(bot.get_channel(channel_id=event.channel_id), None),
        )
        if guild:
            base["guild_name"] = guild.name
            base["guild_avatar"] = guild.icon
        if channel:
            base["channel_name"] = channel.name
            base["channel_type"] = (
                -1 if isinstance(event, DirectMessageCreateEvent) else channel.type
            )
        if event.member:
            base |= {
                "nickname": event.member.nick or "",
                "roles": await _handle_roles(
                    bot, event.guild_id, event.channel_id, event.member.roles or []
                ),
                "joined_at": event.member.joined_at,
            }
        return base
    if isinstance(event, MessageDeleteEvent):
        message_event = event.message
        base = {
            "user_id": message_event.author.id,
            "name": message_event.author.username or "",
            "nickname": "",
            "avatar": message_event.author.avatar,
            "guild_id": message_event.guild_id,
            "channel_id": message_event.channel_id,
        }
        guild, channel, operator = await asyncio.gather(
            safe_call(bot.get_guild(guild_id=message_event.guild_id), None),
            safe_call(bot.get_channel(channel_id=message_event.channel_id), None),
            safe_call(
                bot.get_member(
                    guild_id=message_event.guild_id, user_id=event.op_user.id
                ),
                None,
            ),
        )
        if guild:
            base["guild_name"] = guild.name
            base["guild_avatar"] = guild.icon
        if channel:
            base["channel_name"] = channel.name
            base["channel_type"] = (
                -1 if isinstance(event, DirectMessageDeleteEvent) else channel.type
            )
        base["operator"] = {
            "user_id": event.op_user.id,
            "name": event.op_user.username or "",
            "nickname": "",
            "avatar": event.op_user.avatar,
        }
        if operator:
            base["operator"] |= {
                "nickname": operator.nick or "",
                "roles": await _handle_roles(
                    bot,
                    message_event.guild_id,
                    message_event.channel_id,
                    operator.roles or [],
                ),
                "joined_at": operator.joined_at,
            }
        if message_event.member:
            base |= {
                "nickname": message_event.member.nick or "",
                "roles": await _handle_roles(
                    bot,
                    message_event.guild_id,
                    message_event.channel_id,
                    message_event.member.roles or [],
                ),
                "joined_at": message_event.member.joined_at,
            }
        return base
    if isinstance(event, GuildEvent):
        me = bot.self_info
        base = {
            "user_id": me.id,
            "name": me.username or "",
            "nickname": "",
            "avatar": me.avatar,
            "guild_id": event.id,
            "guild_name": event.name,
            "guild_avatar": event.icon,
        }
        operator = await safe_call(
            bot.get_member(guild_id=event.id, user_id=event.op_user_id), None
        )
        if operator:
            base["operator"] = {
                "user_id": event.op_user_id,
                "name": (operator.user.username if operator.user else "") or "",
                "nickname": operator.nick or "",
                "avatar": operator.user.avatar if operator.user else None,
                "roles": await _handle_roles(bot, event.id, None, operator.roles or []),
                "joined_at": operator.joined_at,
            }
        return base
    if isinstance(event, GuildMemberEvent):
        base = {
            "user_id": event.user.id,
            "name": (event.user.username if event.user else "") or "",
            "nickname": event.nick or "",
            "avatar": event.user.avatar if event.user else None,
            "guild_id": event.guild_id,
            "roles": await _handle_roles(bot, event.guild_id, None, event.roles or []),
            "joined_at": event.joined_at,
        }
        guild, operator = await asyncio.gather(
            safe_call(bot.get_guild(guild_id=event.guild_id), None),
            safe_call(
                bot.get_member(guild_id=event.guild_id, user_id=event.op_user_id), None
            ),
        )
        if guild:
            base["guild_name"] = guild.name
            base["guild_avatar"] = guild.icon
        if operator:
            base["operator"] = {
                "user_id": event.op_user_id,
                "name": (operator.user.username if operator.user else "") or "",
                "nickname": operator.nick or "",
                "avatar": operator.user.avatar if operator.user else None,
                "roles": await _handle_roles(
                    bot, event.guild_id, None, operator.roles or []
                ),
                "joined_at": operator.joined_at,
            }
        return base
    if isinstance(event, ChannelEvent):
        me = bot.self_info
        base = {
            "user_id": me.id,
            "name": me.username or "",
            "nickname": "",
            "avatar": me.avatar,
            "guild_id": event.guild_id,
            "channel_id": event.id,
            "channel_name": event.name,
            "channel_type": event.type,
        }
        guild, operator = await asyncio.gather(
            safe_call(bot.get_guild(guild_id=event.guild_id), None),
            safe_call(
                bot.get_member(guild_id=event.guild_id, user_id=event.op_user_id), None
            ),
        )
        if guild:
            base["guild_name"] = guild.name
            base["guild_avatar"] = guild.icon
        if operator:
            base["operator"] = {
                "user_id": event.op_user_id,
                "name": (operator.user.username if operator.user else "") or "",
                "nickname": operator.nick or "",
                "avatar": operator.user.avatar if operator.user else None,
                "roles": await _handle_roles(
                    bot, event.guild_id, event.id, operator.roles or []
                ),
                "joined_at": operator.joined_at,
            }
        return base
    raise NotImplementedError
