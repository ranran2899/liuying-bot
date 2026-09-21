"""会话信息抓取器基类"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from nonebot.adapters import Bot, Event

from liuying.services.cache import CacheDict

from .config import get_cache_conf
from .model import BasicInfo, Member, Scene, SceneType, Session, User


class InfoFetcher(ABC):
    """会话信息抓取器，由各适配器子类实现具体取值逻辑

    使用流萤本体缓存系统的 CacheDict 容器存放会话/用户/场景/群员，
    键中带上 bot_id 与场景类型，条目按配置的过期时间自动失效。
    """

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter
        self.endpoint: dict[type[Event], Callable[[Bot, Event], Awaitable[dict]]] = {}
        self.wildcard: Callable[[Bot, Event], Awaitable[dict]] | None = None
        self.session_cache = CacheDict("PLATFORM_SESSION")
        self._user_cache = CacheDict("PLATFORM_SESSION_USER")
        self._scene_cache = CacheDict("PLATFORM_SESSION_SCENE")
        self._member_cache = CacheDict("PLATFORM_SESSION_MEMBER")

    def clean(self) -> None:
        """清空全部缓存"""
        self.session_cache.clear()
        self._user_cache.clear()
        self._scene_cache.clear()
        self._member_cache.clear()

    def supply[TE: Event](
        self, func: Callable[[Bot, TE], Awaitable[dict]]
    ) -> Callable[[Bot, TE], Awaitable[dict]]:
        """按事件类型注册数据提供函数，支持联合类型"""
        event_type = get_type_hints(func)["event"]
        if get_origin(event_type) in (Union, UnionType):
            for t in get_args(event_type):
                self.endpoint[t] = func
        else:
            self.endpoint[event_type] = func
        return func

    def supply_wildcard[TE: Event](
        self, func: Callable[[Bot, TE], Awaitable[dict]]
    ) -> Callable[[Bot, TE], Awaitable[dict]]:
        """注册兜底数据提供函数，未命中具体事件类型时使用"""
        self.wildcard = func
        return func

    @abstractmethod
    def extract_user(self, data: dict[str, Any]) -> User:
        """从原始数据中提取用户信息"""
        raise NotImplementedError

    @abstractmethod
    def extract_scene(self, data: dict[str, Any]) -> Scene:
        """从原始数据中提取场景信息"""
        raise NotImplementedError

    @abstractmethod
    def extract_member(self, data: dict[str, Any], user: User | None) -> Member | None:
        """从原始数据中提取群员信息"""
        raise NotImplementedError

    @abstractmethod
    def supply_self(self, bot: Bot) -> BasicInfo:
        """提取机器人基础信息"""
        raise NotImplementedError

    def get_session_id(self, event: Event) -> str:
        """获取会话id，默认使用事件自带的会话id"""
        return event.get_session_id()

    def parse(self, data: dict) -> Session:
        """将提供函数返回的原始数据解析为统一会话"""
        user = self.extract_user(data)
        return Session(
            self_id=data["self_id"],
            adapter=data["adapter"],
            scope=data["scope"],
            user=user,
            scene=self.extract_scene(data),
            member=self.extract_member(data, user),
            operator=self.extract_member(data["operator"], None)
            if "operator" in data
            else None,
        )

    async def fetch(self, bot: Bot, event: Event) -> Session:
        """抓取当前事件的统一会话，优先命中缓存"""
        try:
            sess_id = self.get_session_id(event)
        except ValueError:
            sess_id = None
        cache_key = f"{bot.self_id}:{sess_id}" if sess_id else None
        if cache_key and (cached := self.session_cache.get(cache_key)):
            return cached
        enabled, expire = get_cache_conf()
        func = next(
            (self.endpoint[t] for t in type(event).__mro__[:-1] if t in self.endpoint),
            None,
        )
        base = self.supply_self(bot)
        if func:
            data = await func(bot, event)
        elif self.wildcard:
            data = await self.wildcard(bot, event)
        else:
            raise NotImplementedError(f"事件 {type(event)} 暂不支持会话信息抓取")
        sess = self.parse({**base, **data})
        if enabled and cache_key:
            scene_key = (
                f"{bot.self_id}:{sess.scene.type.value}:{sess.scene.id}:"
                f"{sess.scene.parent.id if sess.scene.parent else ''}"
            )
            self.session_cache.set(cache_key, sess, expire)
            self._user_cache.set(f"{bot.self_id}:{sess.user.id}", sess.user, expire)
            self._scene_cache.set(scene_key, sess.scene, expire)
            if sess.member:
                member_key = (
                    f"{bot.self_id}:{sess.scene.type.value}:"
                    f"{sess.scene.parent.id if sess.scene.parent else sess.scene.id}:"
                    f"{sess.member.id}"
                )
                self._member_cache.set(member_key, sess.member, expire)
        return sess

    @abstractmethod
    async def query_user(self, bot: Bot, user_id: str) -> User | None:
        """主动查询用户信息"""
        raise NotImplementedError

    async def fetch_user(self, bot: Bot, user_id: str) -> User | None:
        """查询用户信息，优先命中缓存"""
        cache_key = f"{bot.self_id}:{user_id}"
        if cached := self._user_cache.get(cache_key):
            return cached
        enabled, expire = get_cache_conf()
        user = await self.query_user(bot, user_id)
        if user and enabled:
            self._user_cache.set(cache_key, user, expire)
        return user

    @abstractmethod
    async def query_scene(
        self,
        bot: Bot,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        """主动查询场景信息"""
        raise NotImplementedError

    async def fetch_scene(
        self,
        bot: Bot,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        """查询场景信息，优先命中缓存"""
        cache_key = (
            f"{bot.self_id}:{scene_type.value}:{scene_id}:{parent_scene_id or ''}"
        )
        if cached := self._scene_cache.get(cache_key):
            return cached
        enabled, expire = get_cache_conf()
        scene = await self.query_scene(
            bot, scene_type, scene_id, parent_scene_id=parent_scene_id
        )
        if scene and enabled:
            self._scene_cache.set(cache_key, scene, expire)
        return scene

    @abstractmethod
    async def query_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        """主动查询群员信息"""
        raise NotImplementedError

    async def fetch_member(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str, user_id: str
    ) -> Member | None:
        """查询群员信息，优先命中缓存"""
        cache_key = f"{bot.self_id}:{scene_type.value}:{parent_scene_id}:{user_id}"
        if cached := self._member_cache.get(cache_key):
            return cached
        enabled, expire = get_cache_conf()
        member = await self.query_member(bot, scene_type, parent_scene_id, user_id)
        if member and enabled:
            self._member_cache.set(cache_key, member, expire)
        return member

    @abstractmethod
    def query_users(self, bot: Bot) -> AsyncGenerator[User]:
        """迭代查询全部用户信息"""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    def query_scenes(
        self,
        bot: Bot,
        scene_type: SceneType | None = None,
        *,
        parent_scene_id: str | None = None
    ) -> AsyncGenerator[Scene]:
        """迭代查询全部场景信息"""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    def query_members(
        self, bot: Bot, scene_type: SceneType, parent_scene_id: str
    ) -> AsyncGenerator[Member]:
        """迭代查询全部群员信息"""
        raise NotImplementedError
        yield  # pragma: no cover
