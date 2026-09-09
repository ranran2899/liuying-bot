"""统一头像快捷获取工具"""

import httpx

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger


class AvatarUtils:
    """头像快捷获取工具类"""

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
        if url := cls.get_user_avatar_url(user_id, platform, appid):
            return await AsyncHttpx.get_content(url)
        return None

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
                        command="AvatarUtils",
                        target=gid,
                        platform=platform,
                    )
        return None
