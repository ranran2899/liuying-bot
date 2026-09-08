import httpx
import nonebot
from nonebot.adapters import Bot
from nonebot_plugin_alconna import SupportScope
from nonebot_plugin_alconna.uniseg import Receipt, Target, UniMessage
from nonebot_plugin_uninfo import SceneType, Uninfo, get_interface
from nonebot_plugin_uninfo.model import Member, User

from liuying.configs.config import BotConfig
from liuying.models._bot import BotFriend
from liuying.models._group import GroupConsole
from liuying.utils.exception import NotFindSuperuser
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform.models import UserData


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
        return bool(BotConfig.get_qbot_uid(session.self_id)) or (
            session.scope == SupportScope.qq_api
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
            case str(sid):
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
    def _build_user_data(
        cls,
        user: User,
        member: Member | None,
        *,
        group_id: str | None = None,
        channel_id: str | None = None,
    ) -> UserData:
        """从 uniseg 的 user/member 构造统一的 UserData

        参数:
            user: 用户信息
            member: 成员信息（群/频道场景时存在）
            group_id: 群组id
            channel_id: 频道id

        返回:
            UserData: 统一的用户数据
        """
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
        return [cls._build_user_data(m.user, m, group_id=group_id) for m in members]

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
        user: User | None = None
        member: Member | None = None
        match (bool(channel_id), bool(group_id)):
            case (True, _):
                member = await interface.get_member(
                    SceneType.CHANNEL_TEXT, channel_id, user_id
                )
            case (_, True):
                member = await interface.get_member(SceneType.GROUP, group_id, user_id)
            case _:
                user = await interface.get_user(user_id)
        if member:
            user = member.user
        return (
            cls._build_user_data(
                user, member, group_id=group_id, channel_id=channel_id
            )
            if user
            else None
        )

    @classmethod
    def _build_qq_avatar_url(cls, user_id: str, appid: str | None = None) -> str:
        """构建QQ头像URL"""
        if user_id.isdigit():
            return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        return f"https://q.qlogo.cn/qqapp/{appid}/{user_id}/640"

    @classmethod
    def _resolve_qq_avatar_url(
        cls, user_id: str, platform: str, appid: str | None = None
    ) -> str | None:
        """按平台解析QQ头像URL，非QQ平台返回None"""
        if platform != "qq":
            return None
        return cls._build_qq_avatar_url(user_id, appid)

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
        if url := cls._resolve_qq_avatar_url(user_id, platform, appid):
            return await AsyncHttpx.get_content(url)
        return None

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
        return cls._resolve_qq_avatar_url(user_id, platform, appid)

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
        if isinstance(t, Uninfo):
            scope = t.basic["scope"]
        elif interface := get_interface(t):
            scope = interface.basic_info()["scope"]
        else:
            return False
        return scope == SupportScope.qq_client

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
            if (
                not only_group
                and platform != "qq"
                and (
                    channel_list := await interface.get_scenes(
                        parent_scene_id=scene.id
                    )
                )
            ):
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
