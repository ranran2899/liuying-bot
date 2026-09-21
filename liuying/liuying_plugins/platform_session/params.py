"""依赖注入参数"""

from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Annotated

from nonebot.adapters import Bot, Event
from nonebot.params import Depends

from .action import Action, ActionExecutor, ActionNotSupported
from .adapters import INFO_FETCHER_MAPPING, alter_get_fetcher, get_executor
from .fetch import InfoFetcher
from .model import Member, Scene, SceneType, Session, User


async def get_session(bot: Bot, event: Event) -> Session | None:
    """从当前事件抓取统一会话，适配器不支持时返回 None"""
    adapter = bot.adapter.get_name()
    fetcher = INFO_FETCHER_MAPPING.get(adapter)
    if not fetcher:
        fetcher = alter_get_fetcher(adapter)
    if fetcher:
        try:
            return await fetcher.fetch(bot, event)
        except NotImplementedError:
            pass
    return None


def UniSession() -> Session:
    """统一会话注入器"""
    return Depends(get_session)


Uninfo = Annotated[Session | None, UniSession()]
"""统一会话类型注解，直接用于处理函数参数"""


class Interface:
    """主动查询接口，封装用户/场景/群员的抓取与迭代，并统一分发管理动作"""

    def __init__(
        self, bot: Bot, fetcher: InfoFetcher, executor: ActionExecutor | None = None
    ) -> None:
        self.bot = bot
        self.fetcher = fetcher
        self.executor = executor

    def basic_info(self) -> dict:
        """获取机器人基础信息"""
        return dict(self.fetcher.supply_self(self.bot))

    def capabilities(self) -> frozenset[Action]:
        """获取当前适配器支持的动作集合"""
        if not self.executor:
            return frozenset()
        return self.executor.capabilities()

    def supports(self, action: Action | str) -> bool:
        """判断当前适配器是否支持指定动作"""
        if not self.executor:
            return False
        return self.executor.supports(action)

    def _require(self, action: Action) -> ActionExecutor:
        """获取支持指定动作的执行器，不支持时抛 ActionNotSupported"""
        if not self.executor or not self.executor.supports(action):
            raise ActionNotSupported(self.bot.adapter.get_name(), action)
        return self.executor

    async def recall(
        self, target: Scene | Session, message_id: str
    ) -> bool:
        """撤回指定会话或场景中的消息"""
        return await self._require(Action.RECALL).recall(self.bot, target, message_id)

    async def mute(
        self, member: Member, scene: Scene, duration: timedelta
    ) -> bool:
        """禁言指定成员"""
        return await self._require(Action.MUTE).mute(
            self.bot, member, scene, duration
        )

    async def unmute(self, member: Member, scene: Scene) -> bool:
        """取消指定成员禁言"""
        return await self._require(Action.UNMUTE).unmute(self.bot, member, scene)

    async def kick(self, member: Member, scene: Scene) -> bool:
        """将指定成员移出场景"""
        return await self._require(Action.KICK).kick(self.bot, member, scene)

    async def get_user(self, user_id: str) -> User | None:
        """根据用户id获取用户信息，不支持时遍历全部用户查找"""
        try:
            return await self.fetcher.fetch_user(self.bot, user_id)
        except NotImplementedError:
            pass
        async for user in self.iter_users():
            if user.id == user_id:
                return user
        return None

    async def get_scene(
        self,
        scene_type: SceneType,
        scene_id: str,
        *,
        parent_scene_id: str | None = None
    ) -> Scene | None:
        """根据场景类型和场景id获取场景信息，不支持时遍历全部场景查找"""
        try:
            return await self.fetcher.fetch_scene(
                self.bot, scene_type, scene_id, parent_scene_id=parent_scene_id
            )
        except NotImplementedError:
            pass
        async for scene in self.iter_scenes(
            scene_type, parent_scene_id=parent_scene_id
        ):
            if scene.type == scene_type and scene.id == scene_id:
                return scene
        return None

    async def get_member(
        self, scene_type: SceneType, scene_id: str, user_id: str
    ) -> Member | None:
        """根据场景类型、场景id和用户id获取成员信息，不支持时遍历成员查找"""
        try:
            return await self.fetcher.fetch_member(
                self.bot, scene_type, scene_id, user_id
            )
        except NotImplementedError:
            pass
        async for member in self.iter_members(scene_type, scene_id):
            if member.user.id == user_id:
                return member
        return None

    async def get_users(self) -> list[User]:
        """获取全部用户信息"""
        return [user async for user in self.iter_users()]

    async def get_scenes(
        self, scene_type: SceneType | None = None, *, parent_scene_id: str | None = None
    ) -> list[Scene]:
        """获取全部场景信息

        参数:
            scene_type: 场景类型，为 None 时返回全部
            parent_scene_id: 父场景id
        """
        return [
            scene
            async for scene in self.iter_scenes(
                scene_type, parent_scene_id=parent_scene_id
            )
        ]

    async def get_members(self, scene_type: SceneType, scene_id: str) -> list[Member]:
        """获取指定场景下的全部成员信息"""
        return [member async for member in self.iter_members(scene_type, scene_id)]

    async def iter_users(self) -> AsyncGenerator[User]:
        """迭代查询全部用户信息"""
        try:
            async for user in self.fetcher.query_users(self.bot):
                yield user
        except NotImplementedError:
            return

    async def iter_scenes(
        self, scene_type: SceneType | None = None, *, parent_scene_id: str | None = None
    ) -> AsyncGenerator[Scene]:
        """迭代查询全部场景信息"""
        try:
            async for scene in self.fetcher.query_scenes(
                self.bot, scene_type, parent_scene_id=parent_scene_id
            ):
                yield scene
        except NotImplementedError:
            return

    async def iter_members(
        self, scene_type: SceneType, scene_id: str
    ) -> AsyncGenerator[Member]:
        """迭代查询指定场景的全部成员信息"""
        try:
            async for member in self.fetcher.query_members(
                self.bot, scene_type, scene_id
            ):
                yield member
        except NotImplementedError:
            return


def get_interface(bot: Bot) -> Interface | None:
    """获取当前 Bot 的主动查询接口，适配器不支持时返回 None"""
    adapter = bot.adapter.get_name()
    fetcher = INFO_FETCHER_MAPPING.get(adapter)
    if fetcher:
        return Interface(bot, fetcher, get_executor(adapter))
    return None


def QueryInterface() -> Interface:
    """主动查询接口注入器"""
    return Depends(get_interface)


QryItrface = Annotated[Interface | None, QueryInterface()]
"""主动查询接口类型注解，直接用于处理函数参数"""
