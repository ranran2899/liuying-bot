"""用户媒体工具类"""

from liuying.models._user.user_media import UserMediaInfo as UserMediaModel

# 默认头像路径
DEFAULT_AVATAR = "https://gitee.com/shiranranran/tuku/raw/master/liuying/touxiang/001.png"


class UserMedia:
    """用户媒体工具类"""

    @classmethod
    async def get_nickname(cls, user_id: str) -> str:
        """
        获取用户昵称
        
        参数:
            user_id: 用户ID
            
        返回:
            str: 用户昵称，如果用户不存在则返回空字符串
        """
        # 调用UserMedia模型的get_nickname方法
        return await UserMediaModel.get_nickname(user_id)

    @classmethod
    async def set_nickname(cls, user_id: str, nickname: str) -> bool:
        """
        设置用户昵称
        
        参数:
            user_id: 用户ID
            nickname: 要设置的用户昵称
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        # 调用UserMedia模型的set_nickname方法
        return await UserMediaModel.set_nickname(user_id, nickname)

    @classmethod
    async def get_avatar(cls, user_id: str) -> str:
        """
        获取用户头像路径，如果为空则设置默认头像并返回
        
        参数:
            user_id: 用户ID
            
        返回:
            str: 用户头像路径（如未设置则返回默认头像路径）
        """
        # 首先检查用户ID是否是5-10位纯数字，如果是则优先使用QQ头像
        if user_id.isdigit() and 5 <= len(user_id) <= 10:
            qq_avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
            # 保存QQ头像URL到数据库并返回
            await UserMediaModel.set_avatar_path(user_id, qq_avatar_url)
            return qq_avatar_url

        # 如果不是纯数字或不在5-10位范围内，则使用原有逻辑
        avatar_path = await UserMediaModel.get_avatar_path(user_id)
        if not avatar_path:
            # 如果头像为空，设置默认头像并返回
            avatar_path = DEFAULT_AVATAR
            await UserMediaModel.set_avatar_path(user_id, avatar_path)
        return avatar_path

    @classmethod
    async def set_avatar(cls, user_id: str, avatar_path: str) -> bool:
        """
        设置用户头像路径
        
        参数:
            user_id: 用户ID
            avatar_path: 要设置的用户头像路径
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        # 调用UserMedia模型的set_avatar_path方法
        return await UserMediaModel.set_avatar_path(user_id, avatar_path)
