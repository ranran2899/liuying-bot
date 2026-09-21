"""OneBot V11 统一会话抓取"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import (
    FriendAddNoticeEvent,
    FriendRecallNoticeEvent,
    FriendRequestEvent,
    GroupAdminNoticeEvent,
    GroupBanNoticeEvent,
    GroupDecreaseNoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    GroupRequestEvent,
    GroupUploadNoticeEvent,
    HonorNotifyEvent,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from nonebot.exception import ActionFailed

from ...constraint import SupportAdapter, SupportScope
from ...fetch import BasicInfo
from ...fetch import InfoFetcher as BaseInfoFetcher
from ...model import Member, MuteInfo, Role, Scene, SceneType, User
from ...util import safe_call

ROLES = {
    "owner": ("OWNER", 100),
    "admin": ("ADMINISTRATOR", 10),
    "member": ("MEMBER", 1),
}


class InfoFetcher(BaseInfoFetcher):
    """OneBot V11 会话信息抓取器"""

    def get_session_id(self, event: Event) -> str:
        if isinstance(event, PokeNotifyEvent):
            return f"{event.get_session_id()}_{event.target_id}"
        if isinstance(
            event,
            (
                GroupDecreaseNoticeEvent,
                GroupIncreaseNoticeEvent,
                GroupRecallNoticeEvent,
                GroupBanNoticeEvent,
            ),
        ):
            return f"{event.get_session_id()}_{event.operator_id}"
        return event.get_session_id()

    def extract_user(self, data: dict) -> User:
        return User(
            id=data["user_id"],
            name=data["name"],
            nick=data["nickname"],
            avatar=f"http://q1.qlogo.cn/g?b=qq&nk={data['user_id']}&s=640",
            gender=data.get("gender", "unknown"),
        )

    def extract_scene(self, data: dict) -> Scene:
        if "group_id" not in data:
            return Scene(
                id=data["user_id"],
                type=SceneType.PRIVATE,
                name=data["name"],
                avatar=f"http://q1.qlogo.cn/g?b=qq&nk={data['user_id']}&s=640",
            )
        return Scene(
            id=data["group_id"],
            type=SceneType.GROUP,
            name=data["group_name"],
            avatar=f"https://p.qlogo.cn/gh/{data['group_id']}/{data['group_id']}/",
        )

    def extract_member(self, data: dict, user: User | None) -> Member | None:
        if "group_id" not in data:
            return None
        roles = [Role(*ROLES[_role], name=_role)] if (_role := data.get("role")) else []
        joined_at = (
            datetime.fromtimestamp(data["join_time"]) if data["join_time"] else None
        )
        mute = (
            MuteInfo(muted=True, duration=timedelta(seconds=data["mute_duration"]))
            if "mute_duration" in data
            else None
        )
        if user:
            return Member(
                user=user,
                nick=data["card"],
                roles=roles,
                joined_at=joined_at,
                mute=mute,
            )
        return Member(
            User(
                id=data["user_id"],
                name=data["name"],
                nick=data.get("nickname"),
                avatar=f"https://q2.qlogo.cn/headimg_dl?dst_uin={data['user_id']}&spec=640",
            ),
            nick=data["card"],
            roles=roles,
            joined_at=joined_at,
            mute=mute,
        )

    async def query_user(self, bot: Bot, user_id: str) -> User | None:
        if user_id == bot.self_id:
            info = await bot.get_login_info()
        else:
            info = await bot.get_stranger_info(user_id=int(user_id))
        data = {
            "user_id": str(info["user_id"]),
            "name": info["nickname"],
            "nickname": info["nickname"],
            "gender": info.get("sex"),
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
            if user := (await self.query_user(bot, scene_id)):
                data = {
                    "user_id": user.id,
                    "name": user.name,
                    "avatar": user.avatar,
                }
                return self.extract_scene(data)
        elif scene_type == SceneType.GROUP:
            group = await bot.get_group_info(group_id=int(scene_id))
            data = {
                "group_id": str(group["group_id"]),
                "group_name": group["group_name"],
            }
            return self.extract_scene(data)
        return None

    async def query_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        if scene_type != SceneType.GROUP:
            return None
        member = await bot.get_group_member_info(
            group_id=int(parent_scene_id), user_id=int(user_id)
        )
        data = {
            "group_id": parent_scene_id,
            "user_id": str(member["user_id"]),
            "name": member["nickname"],
            "card": member["card"],
            "role": member["role"],
            "join_time": member.get("join_time"),
            "gender": member["sex"],
        }
        return self.extract_member(data, None)

    async def query_users(self, bot: Bot) -> AsyncGenerator[User]:
        friends = await bot.get_friend_list()
        for friend in friends:
            data = {
                "user_id": str(friend["user_id"]),
                "name": friend["nickname"],
                "nickname": friend["remark"],
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
                    "group_id": str(group["group_id"]),
                    "group_name": group["group_name"],
                }
                yield self.extract_scene(data)

    async def query_members(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str
    ) -> AsyncGenerator[Member]:
        if scene_type != SceneType.GROUP:
            return
        members = await bot.get_group_member_list(group_id=int(parent_scene_id))
        for member in members:
            data = {
                "group_id": parent_scene_id,
                "user_id": str(member["user_id"]),
                "name": member["nickname"],
                "card": member["card"],
                "role": member["role"],
                "join_time": member.get("join_time"),
                "gender": member["sex"],
            }
            yield self.extract_member(data, None)

    def supply_self(self, bot: Bot) -> BasicInfo:
        return {
            "self_id": str(bot.self_id),
            "adapter": SupportAdapter.onebot11,
            "scope": SupportScope.qq_client,
        }


fetcher = InfoFetcher(SupportAdapter.onebot11)


@fetcher.supply
async def _(bot: Bot, event: PrivateMessageEvent) -> dict:
    return {
        "user_id": str(event.user_id),
        "name": event.sender.nickname,
        "nickname": event.sender.card,
        "gender": event.sender.sex or "unknown",
    }


@fetcher.supply
async def _(
    bot: Bot, event: FriendAddNoticeEvent | FriendRecallNoticeEvent | FriendRequestEvent
) -> dict:
    friend_info: dict = {}
    async for friend in fetcher.query_users(bot):
        if friend.id == str(event.user_id):
            friend_info = {
                "nickname": friend.name,
                "remark": friend.nick,
            }
            break
    else:
        try:
            res = await bot.get_stranger_info(user_id=event.user_id)
            friend_info = dict(res)
        except ActionFailed:
            friend_info = {}
    return {
        "user_id": str(event.user_id),
        "name": friend_info.get("nickname"),
        "nickname": friend_info.get("remark"),
        "gender": friend_info.get("sex", "unknown"),
    }


@fetcher.supply
async def _(bot: Bot, event: GroupMessageEvent) -> dict:
    group_info, member_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id, no_cache=True
            ),
            {},
        ),
    )
    return {
        "group_id": str(event.group_id),
        "group_name": group_info.get("group_name"),
        "user_id": str(event.user_id),
        "name": event.sender.nickname,
        "nickname": event.sender.card,
        "card": member_info.get("card"),
        "role": event.sender.role,
        "join_time": member_info.get("join_time"),
        "gender": member_info.get("sex", "unknown"),
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: GroupUploadNoticeEvent
    | GroupAdminNoticeEvent
    | GroupRequestEvent
    | HonorNotifyEvent,
) -> dict:
    group_info, member_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id, no_cache=True
            ),
            {},
        ),
    )
    return {
        "group_id": str(event.group_id),
        "group_name": group_info.get("group_name"),
        "user_id": str(event.user_id),
        "name": member_info.get("nickname"),
        "nickname": member_info.get("card"),
        "card": member_info.get("card"),
        "role": member_info.get("role"),
        "join_time": member_info.get("join_time"),
        "gender": member_info.get("sex", "unknown"),
    }


@fetcher.supply
async def _(bot: Bot, event: PokeNotifyEvent) -> dict:
    if not event.group_id:
        friend_info: dict = {}
        async for friend in fetcher.query_users(bot):
            if friend.id == str(event.user_id):
                friend_info = {
                    "nickname": friend.name,
                    "remark": friend.nick,
                }
                break
        else:
            try:
                res = await bot.get_stranger_info(user_id=event.user_id)
                friend_info = dict(res)
            except ActionFailed:
                friend_info = {}
        user_data = {
            "user_id": str(event.user_id),
            "name": friend_info.get("nickname"),
            "nickname": friend_info.get("remark"),
            "gender": friend_info.get("sex", "unknown"),
        }
        return {**user_data, "operator": user_data}
    group_info, operator_info, member_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id, no_cache=True
            ),
            {},
        ),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.target_id, no_cache=True
            ),
            {},
        ),
    )
    return {
        "group_id": str(event.group_id),
        "group_name": group_info.get("group_name"),
        "user_id": str(event.target_id),
        "name": member_info.get("nickname"),
        "nickname": member_info.get("card"),
        "card": member_info.get("card"),
        "role": member_info.get("role"),
        "join_time": member_info.get("join_time"),
        "gender": member_info.get("sex", "unknown"),
        "operator": {
            "group_id": str(event.group_id),
            "user_id": str(event.user_id),
            "name": operator_info.get("nickname"),
            "nickname": operator_info.get("card"),
            "card": operator_info.get("card"),
            "role": operator_info.get("role"),
            "join_time": operator_info.get("join_time"),
            "gender": operator_info.get("sex", "unknown"),
        },
    }


@fetcher.supply
async def _(
    bot: Bot,
    event: GroupDecreaseNoticeEvent | GroupIncreaseNoticeEvent | GroupRecallNoticeEvent,
) -> dict:
    group_info, member_info, operator_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id, no_cache=True
            ),
            {},
        ),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.operator_id, no_cache=True
            ),
            {},
        ),
    )
    return {
        "group_id": str(event.group_id),
        "group_name": group_info.get("group_name"),
        "user_id": str(event.user_id),
        "name": member_info.get("nickname"),
        "nickname": member_info.get("card"),
        "card": member_info.get("card"),
        "role": member_info.get("role"),
        "join_time": member_info.get("join_time"),
        "gender": member_info.get("sex", "unknown"),
        "operator": {
            "group_id": str(event.group_id),
            "user_id": str(event.operator_id),
            "name": operator_info.get("nickname"),
            "nickname": operator_info.get("card"),
            "card": operator_info.get("card"),
            "role": operator_info.get("role"),
            "join_time": operator_info.get("join_time"),
            "gender": operator_info.get("sex", "unknown"),
        },
    }


@fetcher.supply
async def _(bot: Bot, event: GroupBanNoticeEvent) -> dict:
    group_info, member_info, operator_info = await asyncio.gather(
        safe_call(bot.get_group_info(group_id=event.group_id), {}),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id, no_cache=True
            ),
            {},
        ),
        safe_call(
            bot.get_group_member_info(
                group_id=event.group_id, user_id=event.operator_id, no_cache=True
            ),
            {},
        ),
    )
    return {
        "group_id": str(event.group_id),
        "group_name": group_info.get("group_name"),
        "user_id": str(event.user_id),
        "name": member_info.get("nickname"),
        "nickname": member_info.get("card"),
        "card": member_info.get("card"),
        "role": member_info.get("role"),
        "join_time": member_info.get("join_time"),
        "gender": member_info.get("sex", "unknown"),
        "mute_duration": event.duration,
        "operator": {
            "group_id": str(event.group_id),
            "user_id": str(event.operator_id),
            "name": operator_info.get("nickname"),
            "nickname": operator_info.get("card"),
            "card": operator_info.get("card"),
            "role": operator_info.get("role"),
            "join_time": operator_info.get("join_time"),
            "gender": operator_info.get("sex", "unknown"),
        },
    }
