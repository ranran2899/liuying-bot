

from datetime import datetime
import random
import string

from liuying.models._user.user_info import UserInfo


class UserUid:
    """用户UID工具类"""

    @classmethod
    async def get_user_uid(cls, user_id: str) -> str:
        """
        获取用户UID，如果UID为空则自动创建新的UID
        
        参数:
            user_id: 用户ID
        
        返回:
            str: 用户UID
        """
        return await UserInfo.get_user_uid(user_id)

    @classmethod
    async def set_uid_token(cls, uid: str, token: str) -> str:
        """
        设置UID令牌
        
        参数:
            uid: 用户唯一标识
            token: 设置的令牌字符串
        
        返回:
            str: UID当前令牌字符串
        """
        return await UserInfo.set_uid_token(uid, token)

    @classmethod
    async def get_uid_token(cls, uid: str) -> str:
        """
        获取UID的令牌，如果令牌为空则自动创建10位随机数字字母的字符串令牌
        
        参数:
            uid: 用户唯一标识
        
        返回:
            str: UID对应的令牌字符串
        """
        # 获取当前令牌
        token = await UserInfo.get_uid_token(uid)
        # 如果令牌为空，则生成10位随机数字字母字符串
        if not token:
            token = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            # 保存新生成的令牌
            token = await UserInfo.set_uid_token(uid, token)

        return token

    @classmethod
    async def check_uid_exists(cls, uid: str) -> bool:
        """
        检查UID是否存在

        参数:
            uid: 用户唯一标识

        返回:
            bool: UID存在返回True，不存在返回False
        """
        return await UserInfo.filter(uid=uid).exists()

    @classmethod
    async def get_user_id_by_uid(cls, uid: str) -> str | None:
        """
        通过UID查找用户ID

        参数:
            uid: 用户唯一标识

        返回:
            str | None: 用户ID，如果UID不存在则返回None
        """
        user = await UserInfo.filter(uid=uid).first()
        if user:
            return user.user_id
        return None

    @classmethod
    async def check_uid_token_exists(cls, uid: str) -> bool:
        """
        验证UID的令牌是否存在
        
        参数:
            uid: 用户唯一标识
        
        返回:
            bool: 令牌存在返回True，不存在返回False
        """
        user = await UserInfo.filter(uid=uid).first()
        return bool(user and user.uid_token)

    @classmethod
    async def verify_uid_token(cls, uid: str, token: str) -> bool:
        """
        验证UID的令牌是否正确
        
        参数:
            uid: 用户唯一标识
            token: 待验证的令牌字符串
        
        返回:
            bool: 令牌正确返回True，错误或不存在返回False
        """
        user = await UserInfo.filter(uid=uid).first()
        return bool(user and user.uid_token and user.uid_token == token)

    @classmethod
    async def get_user_register_time(cls, user_id: str) -> datetime:
        """
        获取用户的注册时间
        
        参数:
            user_id: 用户ID
        
        返回:
            datetime: 用户的注册时间，如果未找到则返回None
        """
        # 根据UID查询用户信息
        user = await UserInfo.filter(user_id=user_id).first()
        # 如果找到用户，返回注册时间
        if user:
            return user.create_time
        # 未找到用户返回None
        return None



