import asyncio
from collections.abc import Awaitable, Callable
import random
from typing import cast

import httpx
import nonebot
from nonebot.adapters import Bot
from nonebot.utils import is_coroutine_callable
from nonebot_plugin_alconna import SupportScope
from nonebot_plugin_alconna.uniseg import Receipt, Target, UniMessage
from nonebot_plugin_uninfo import SceneType, Uninfo, get_interface
from nonebot_plugin_uninfo.model import Member
from pydantic import BaseModel

from liuying.configs.config import BotConfig
from liuying.models._bot import BotFriend
from liuying.models._group import GroupConsole
from liuying.utils.exception import NotFindSuperuser
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

driver = nonebot.get_driver()


class UserData(BaseModel):
    name: str
    """昵称"""
    card: str | None = None
    """名片/备注"""
    user_id: str
    """用户id"""
    group_id: str | None = None
    """群组id"""
    channel_id: str | None = None
    """频道id"""
    role: str | None = None
    """角色"""
    avatar_url: str | None = None
    """头像url"""
    join_time: int | None = None
    """加入时间"""


def _normalize_platform(scope: str) -> str:
    """将 scope 统一为平台标识"""
    platform = scope.lower()
    return "qq" if platform.startswith("qq") else platform


class PlatformUtils:
    @classmethod
    def is_qbot(cls, session: Uninfo | Bot) -> bool:
        """判断bot是否为qq官bot

        参数:
            session: Uninfo | Bot

        返回:
            bool: 是否为官bot
        """
        if isinstance(session, Bot):
            return bool(BotConfig.get_qbot_uid(session.self_id))
        return (
            bool(BotConfig.get_qbot_uid(session.self_id))
            or session.scope == SupportScope.qq_api
        )

    @classmethod
    def is_qq_guild(cls, session: Uninfo) -> bool:
        """判断qq官方适配器当前是否为频道场景

        参数:
            session: Uninfo

        返回:
            bool: 是否为频道场景
        """
        return session.scope == SupportScope.qq_api and (
            session.scene.is_guild or session.scene.is_channel
        )

    @classmethod
    async def ban_user(cls, bot: Bot, user_id: str, group_id: str, duration: int):
        """禁言

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id
            duration: 禁言时长(分钟)
        """
        if cls.get_platform(bot) == "qq":
            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=duration * 60,
            )

    @classmethod
    async def send_superuser(
        cls,
        bot: Bot | None,
        message: UniMessage | str,
        superuser_id: str | None = None,
    ) -> list[tuple[str, Receipt]]:
        """发送消息给超级用户

        参数:
            bot: Bot，没有传入时使用get_bot随机获取
            message: 消息
            superuser_id: 指定超级用户id.

        异常:
            NotFindSuperuser: 未找到超级用户id

        返回:
            list[tuple[str, Receipt]]: 发送结果列表
        """
        if not bot:
            bot = nonebot.get_bot()
        match superuser_id:
            case str() as sid:
                superuser_ids = [sid]
            case _:
                if not (
                    superuser_ids := BotConfig.get_superuser(cls.get_platform(bot))
                ):
                    raise NotFindSuperuser()
        if isinstance(message, str):
            message = MessageUtils.build_message(message)
        result = []
        for sid in superuser_ids:
            try:
                result.append((sid, await cls.send_message(bot, sid, None, message)))
            except Exception as e:
                logger.error(
                    "发送消息给超级用户失败",
                    command="PlatformUtils:send_superuser",
                    target=sid,
                    e=e,
                )
        return result

    @classmethod
    async def get_group_member_list(cls, bot: Bot, group_id: str) -> list[UserData]:
        """获取群组/频道成员列表

        参数:
            bot: Bot
            group_id: 群组/频道id

        返回:
            list[UserData]: 用户数据列表
        """
        if not (interface := get_interface(bot)):
            return []
        members: list[Member] = await interface.get_members(SceneType.GROUP, group_id)
        return [
            UserData(
                name=member.user.name or "",
                card=member.nick,
                user_id=member.user.id,
                group_id=group_id,
                role=member.role.id if member.role else "",
                avatar_url=member.user.avatar,
                join_time=(
                    int(member.joined_at.timestamp()) if member.joined_at else None
                ),
            )
            for member in members
        ]

    @classmethod
    async def get_user(
        cls,
        bot: Bot,
        user_id: str,
        group_id: str | None = None,
        channel_id: str | None = None,
    ) -> UserData | None:
        """获取用户信息

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id.
            channel_id: 频道id.

        返回:
            UserData | None: 用户数据
        """
        if not (interface := get_interface(bot)):
            return None
        member = None
        match (channel_id, group_id):
            case (str(), _):
                member = await interface.get_member(
                    SceneType.CHANNEL_TEXT, channel_id, user_id
                )
            case (None, str()):
                member = await interface.get_member(SceneType.GROUP, group_id, user_id)
            case _:
                user = await interface.get_user(user_id)
        if member:
            user = member.user
        if not user:
            return None
        return UserData(
            name=user.name or "",
            card=member.nick if member else None,
            user_id=user.id,
            group_id=group_id,
            channel_id=channel_id,
            role=member.role.id if member and member.role else None,
            join_time=(
                int(member.joined_at.timestamp())
                if member and member.joined_at
                else None
            ),
        )

    @classmethod
    def _build_qq_avatar_url(cls, user_id: str, appid: str | None = None) -> str:
        """构建QQ头像URL"""
        if user_id.isdigit():
            return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        return f"https://q.qlogo.cn/qqapp/{appid}/{user_id}/640"

    @classmethod
    async def get_user_avatar(
        cls, user_id: str, platform: str, appid: str | None = None
    ) -> bytes | None:
        """快捷获取用户头像

        参数:
            user_id: 用户id
            platform: 平台
            appid: 应用id

        返回:
            bytes | None: 头像数据
        """
        if platform != "qq":
            return None
        return await AsyncHttpx.get_content(cls._build_qq_avatar_url(user_id, appid))

    @classmethod
    def get_user_avatar_url(
        cls, user_id: str, platform: str, appid: str | None = None
    ) -> str | None:
        """快捷获取用户头像url

        参数:
            user_id: 用户id
            platform: 平台
            appid: 应用id

        返回:
            str | None: 头像url
        """
        if platform != "qq":
            return None
        return cls._build_qq_avatar_url(user_id, appid)

    @classmethod
    async def get_group_avatar(cls, gid: str, platform: str) -> bytes | None:
        """快捷获取群头像

        参数:
            gid: 群组id
            platform: 平台

        返回:
            bytes | None: 群头像数据
        """
        if platform != "qq":
            return None
        url = f"http://p.qlogo.cn/gh/{gid}/{gid}/640/"
        async with httpx.AsyncClient() as client:
            for _ in range(3):
                try:
                    return (await client.get(url)).content
                except Exception:
                    logger.error(
                        "获取群头像错误",
                        command="Util",
                        target=gid,
                        platform=platform,
                    )
        return None

    @classmethod
    async def send_message(
        cls,
        bot: Bot,
        user_id: str | None,
        group_id: str | None,
        message: str | UniMessage,
    ) -> Receipt | None:
        """发送消息

        参数:
            bot: Bot
            user_id: 用户id
            group_id: 群组id或频道id
            message: 消息文本

        返回:
            Receipt | None: 是否发送成功
        """
        if not (target := cls.get_target(user_id=user_id, group_id=group_id)):
            return None
        send_message = (
            MessageUtils.build_message(message)
            if isinstance(message, str)
            else message
        )
        return await send_message.send(target=target, bot=bot)

    @classmethod
    async def update_group(cls, bot: Bot) -> int:
        """更新群组信息

        参数:
            bot: Bot

        返回:
            int: 更新个数
        """
        group_list, platform = await cls.get_group_list(bot)
        if not group_list:
            return 0
        db_groups = {
            (g.group_id, g.channel_id): g
            for g in await GroupConsole.filter().all()
        }
        create_list, update_list = [], []
        for group in group_list:
            group.platform = platform
            if db_group := db_groups.get((group.group_id, group.channel_id)):
                db_group.group_name = group.group_name
                db_group.max_member_count = group.max_member_count
                db_group.member_count = group.member_count
                update_list.append(db_group)
            else:
                create_list.append(group)
                logger.debug(
                    "群聊信息更新成功",
                    command="更新群信息",
                    target=f"{group.group_id}:{group.channel_id}",
                )
        if create_list:
            await GroupConsole.filter().bulk_create(create_list)
        if update_list:
            await GroupConsole.filter().bulk_update(
                update_list, ["group_name", "max_member_count", "member_count"]
            )
        return len(create_list)

    @classmethod
    def get_platform(cls, t: Bot | Uninfo) -> str:
        """获取平台

        参数:
            t: Bot | Uninfo

        返回:
            str: 平台标识
        """
        if isinstance(t, Bot):
            if interface := get_interface(t):
                return _normalize_platform(interface.basic_info()["scope"])
            return "unknown"
        return _normalize_platform(t.basic["scope"])

    @classmethod
    def is_forward_merge_supported(cls, t: Bot | Uninfo) -> bool:
        """是否支持转发消息

        参数:
            t: bot | Uninfo

        返回:
            bool: 是否支持转发消息
        """
        if not isinstance(t, Bot):
            return t.basic["scope"] == SupportScope.qq_client
        if interface := get_interface(t):
            return interface.basic_info()["scope"] == SupportScope.qq_client
        return False

    @classmethod
    async def get_group_list(
        cls, bot: Bot, only_group: bool = False
    ) -> tuple[list[GroupConsole], str]:
        """获取群组列表

        参数:
            bot: Bot
            only_group: 是否只获取群组（不获取channel）

        返回:
            tuple[list[GroupConsole], str]: 群组列表, 平台
        """
        if not (interface := get_interface(bot)):
            return [], ""
        platform = cls.get_platform(bot)
        result_list = []
        for scene in await interface.get_scenes(SceneType.GROUP):
            result_list.append(
                GroupConsole(group_id=scene.id, group_name=scene.name)
            )
            if not only_group and platform != "qq":
                if channel_list := await interface.get_scenes(parent_scene_id=scene.id):
                    result_list.extend(
                        GroupConsole(
                            group_id=scene.id,
                            group_name=channel.name,
                            channel_id=channel.id,
                        )
                        for channel in channel_list
                    )
        return result_list, platform

    @classmethod
    async def update_friend(cls, bot: Bot) -> int:
        """更新好友信息

        参数:
            bot: Bot

        返回:
            int: 更新个数
        """
        count = 0
        friend_list, platform = await cls.get_friend_list(bot)
        for friend in friend_list:
            _, created = await BotFriend.update_or_create(
                bot_id=bot.self_id,
                user_id=friend.user_id,
                defaults={"user_name": friend.user_name, "platform": platform},
            )
            if created:
                count += 1
        return count

    @classmethod
    async def get_friend_list(
        cls, bot: Bot
    ) -> tuple[list[BotFriend], str]:
        """获取好友列表

        参数:
            bot: Bot

        返回:
            tuple[list[BotFriend], str]: 好友列表, 平台
        """
        if not (interface := get_interface(bot)):
            return [], ""
        user_list = await interface.get_users()
        return [
            BotFriend(bot_id=bot.self_id, user_id=u.id, user_name=u.name)
            for u in user_list
        ], cls.get_platform(bot)

    @classmethod
    def get_target(
        cls,
        *,
        user_id: str | None = None,
        group_id: str | None = None,
        channel_id: str | None = None,
    ) -> Target | None:
        """获取发送Target

        参数:
            user_id: 用户id
            group_id: 群组id
            channel_id: 频道id

        返回:
            Target | None: 对应平台Target
        """
        match (group_id, channel_id, user_id):
            case (str(), str(), _):
                return Target(channel_id, parent_id=group_id, channel=True)
            case (str(), None, _):
                return Target(group_id)
            case (None, None, str()):
                return Target(user_id, private=True)
            case _:
                return None


class BroadcastEngine:
    def __init__(
        self,
        message: str | UniMessage,
        bot: Bot | list[Bot] | None = None,
        bot_id: str | set[str] | None = None,
        ignore_group: list[str] | None = None,
        check_func: Callable[[Bot, str], Awaitable] | None = None,
        log_cmd: str | None = None,
        platform: str | None = None,
    ):
        """广播引擎

        参数:
            message: 广播消息内容
            bot: 指定bot对象.
            bot_id: 指定bot id.
            ignore_group: 忽略群聊列表.
            check_func: 发送前对群聊检测方法，判断是否发送.
            log_cmd: 日志标记.
            platform: 指定平台.

        异常:
            ValueError: 没有可用的Bot对象
        """
        self.message = MessageUtils.build_message(message)
        self.ignore_group = ignore_group or []
        self.check_func = check_func
        self.log_cmd = log_cmd
        self.platform = platform
        self.bot_list: list[Bot] = []
        self.count = 0
        if bot:
            self.bot_list = [bot] if isinstance(bot, Bot) else bot
        if isinstance(bot_id, str):
            bot_id = {bot_id}
        if bot_id:
            for bid in bot_id:
                try:
                    self.bot_list.append(nonebot.get_bot(bid))
                except KeyError:
                    logger.warning(
                        f"Bot:{bid} 对象未连接或不存在", command=log_cmd
                    )
        if not self.bot_list:
            try:
                bot = nonebot.get_bot()
                self.bot_list.append(bot)
                logger.warning(
                    f"广播任务未传入Bot对象，使用默认Bot {bot.self_id}",
                    command=log_cmd,
                )
            except Exception as e:
                raise ValueError("当前没有可用的Bot对象...", log_cmd) from e

    async def call_check(self, bot: Bot, group_id: str) -> bool:
        """运行发送检测函数

        参数:
            bot: Bot
            group_id: 群组id

        返回:
            bool: 是否发送
        """
        if not self.check_func:
            return True
        is_run = (
            await self.check_func(bot, group_id)
            if is_coroutine_callable(self.check_func)
            else self.check_func(bot, group_id)
        )
        return cast(bool, is_run)

    async def __send_message(self, bot: Bot, group: GroupConsole):
        """群组发送消息

        参数:
            bot: Bot
            group: GroupConsole
        """
        key = f"{group.group_id}:{group.channel_id}"
        if not await self.call_check(bot, group.group_id):
            logger.debug(
                "广播方法检测运行方法为 False, 已跳过该群组...",
                command=self.log_cmd,
                group_id=group.group_id,
            )
            return
        if not await GroupConsole.is_proactive_allowed(group.group_id):
            logger.debug(
                "群聊已关闭主动消息, 跳过该群组...",
                command=self.log_cmd,
                group_id=group.group_id,
            )
            return
        if target := PlatformUtils.get_target(
            group_id=group.group_id,
            channel_id=group.channel_id,
        ):
            self.ignore_group.append(key)
            await MessageUtils.build_message(self.message).send(target, bot)
            logger.debug("广播消息发送成功...", command=self.log_cmd, target=key)
        else:
            logger.warning(
                "广播消息获取Target失败...", command=self.log_cmd, target=key
            )

    async def broadcast(self) -> int:
        """广播消息

        返回:
            int: 成功发送次数
        """
        for bot in self.bot_list:
            if self.platform and self.platform != PlatformUtils.get_platform(bot):
                continue
            group_list, _ = await PlatformUtils.get_group_list(bot)
            if not group_list:
                continue
            for group in group_list:
                if (
                    group.group_id in self.ignore_group
                    or group.channel_id in self.ignore_group
                ):
                    continue
                try:
                    await self.__send_message(bot, group)
                    await asyncio.sleep(random.randint(1, 3))
                    self.count += 1
                except Exception as e:
                    logger.warning(
                        "广播消息发送失败",
                        command=self.log_cmd,
                        target=group.group_id,
                        e=e,
                    )
        return self.count


async def broadcast_group(
    message: str | UniMessage,
    bot: Bot | list[Bot] | None = None,
    bot_id: str | set[str] | None = None,
    ignore_group: list[str] | None = None,
    check_func: Callable[[Bot, str], Awaitable] | None = None,
    log_cmd: str | None = None,
    platform: str | None = None,
) -> int:
    """获取所有Bot或指定Bot对象广播群聊

    参数:
        message: 广播消息内容
        bot: 指定bot对象.
        bot_id: 指定bot id.
        ignore_group: 忽略群聊列表.
        check_func: 发送前对群聊检测方法，判断是否发送.
        log_cmd: 日志标记.
        platform: 指定平台

    返回:
        int: 成功发送次数
    """
    if not message.strip():
        raise ValueError("群聊广播消息不能为空...")
    return await BroadcastEngine(
        message=message,
        bot=bot,
        bot_id=bot_id,
        ignore_group=ignore_group,
        check_func=check_func,
        log_cmd=log_cmd,
        platform=platform,
    ).broadcast()
