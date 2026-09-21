"""Minecraft 适配器统一会话抓取"""

from collections.abc import AsyncGenerator

from nonebot.adapters.minecraft import Bot
from nonebot.adapters.minecraft.event import Event, MessageEvent, NoticeEvent

from ...constraint import SupportAdapter, SupportScope
from ...fetch import BasicInfo
from ...fetch import InfoFetcher as BaseInfoFetcher
from ...model import Member, Scene, SceneType, User


class InfoFetcher(BaseInfoFetcher):
    """Minecraft 会话信息抓取器"""

    def extract_user(self, data: dict) -> User:
        return User(
            id=data["user_id"],
            name=data["name"],
        )

    def extract_scene(self, data: dict) -> Scene:
        return Scene(
            id=data["user_id"],
            type=SceneType.PRIVATE,
            name=data["name"],
        )

    def extract_member(self, data: dict, user: User | None) -> Member | None:
        return None

    async def query_user(self, bot: Bot, user_id: str) -> User | None:
        return User(user_id, user_id)

    async def query_scene(
        self,
        bot: Bot,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        return Scene(id=scene_id, type=SceneType.PRIVATE, name=scene_id)

    async def query_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        raise NotImplementedError

    def query_users(self, bot: Bot) -> AsyncGenerator[User]:
        raise NotImplementedError

    async def query_scenes(
        self,
        bot: Bot,
        scene_type: SceneType | None = None,
        *,
        parent_scene_id: str | None = None
    ) -> AsyncGenerator[Scene]:
        raise NotImplementedError

    async def query_members(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str
    ) -> AsyncGenerator[Member]:
        raise NotImplementedError

    def supply_self(self, bot: Bot) -> BasicInfo:
        return {
            "self_id": str(bot.self_id),
            "adapter": SupportAdapter.minecraft,
            "scope": SupportScope.minecraft,
        }


fetcher = InfoFetcher(SupportAdapter.minecraft)


@fetcher.supply_wildcard
async def _(bot: Bot, event: Event) -> dict:
    if isinstance(event, (MessageEvent, NoticeEvent)):
        return {
            "user_id": str(event.player.uuid or event.player.nickname),
            "name": event.player.nickname,
        }
    raise NotImplementedError
