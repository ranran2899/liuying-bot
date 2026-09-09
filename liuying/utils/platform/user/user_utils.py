from nonebot.adapters import Bot
from nonebot_plugin_uninfo import SceneType, get_interface
from nonebot_plugin_uninfo.model import Member, User

from liuying.models._bot import BotFriend
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.platform.helper import PlatformUtils
from liuying.utils.platform.models import UserData, build_user_data


class UserUtils:
    """用户工具类"""

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
            build_user_data(user, member, group_id=group_id, channel_id=channel_id)
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
    async def get_friend_list(cls, bot: Bot) -> tuple[list[BotFriend], str]:
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
        ], PlatformUtils.get_platform(bot)
