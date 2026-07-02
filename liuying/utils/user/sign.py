"""用户签到工具模块"""

from datetime import datetime

from liuying.models._user.user_intro import UserIntroInfo
from liuying.models._user.user_sign import UserSignInfo


class UserSign:
    """用户签到工具类"""

    @classmethod
    async def check_user_sign_status(cls, user_id: str) -> int:
        """
        检查用户是否已签到
        
        参数:
            user_id: 用户ID
            
        返回:
            int: 0表示未签到，1表示已签到
        """
        return await UserSignInfo.check_user_sign_status(user_id)

    @classmethod
    async def get_all_signed_in_users(cls) -> list[UserSignInfo]:
        """
        获取所有已签到的用户列表
        
        返回:
            list: 所有已签到(is_signed_in=1)的用户列表
        """
        return await UserSignInfo.get_all_signed_in_users()

    @classmethod
    async def reset_all_signed_in_users(cls) -> int:
        """
        重置所有已签到用户的状态为未签到

        返回:
            int: 重置的用户数量
        """
        return await UserSignInfo.reset_all_signed_in_users()

    @classmethod
    async def set_user_sign_status(cls, user_id: str, status: int) -> bool:
        """
        设置用户签到状态
        
        参数:
            user_id: 用户ID
            status: 签到状态，0表示未签到，1表示已签到
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_user_sign_status(user_id, status)

    @classmethod
    async def set_total_days(cls, user_id: str, days: int) -> bool:
        """
        设置用户累计签到天数
        
        参数:
            user_id: 用户ID
            days: 要设置的累计签到天数，必须为非负数
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_total_days(user_id, days)

    @classmethod
    async def set_consecutive_days(cls, user_id: str, days: int) -> bool:
        """
        设置用户连续签到天数
        
        参数:
            user_id: 用户ID
            days: 要设置的连续签到天数，必须为非负数
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_consecutive_days(user_id, days)

    @classmethod
    async def get_total_days(cls, user_id: str) -> int:
        """
        获取用户累计签到天数
        
        参数:
            user_id: 用户ID
            
        返回:
            int: 用户的累计签到天数，如果用户不存在则返回0
        """
        return await UserSignInfo.get_total_days(user_id)

    @classmethod
    async def get_consecutive_days(cls, user_id: str) -> int:
        """
        获取用户连续签到天数
        
        参数:
            user_id: 用户ID
            
        返回:
            int: 用户的连续签到天数，如果用户不存在则返回0
        """
        return await UserSignInfo.get_consecutive_days(user_id)

    @classmethod
    async def get_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户签到日期
        
        参数:
            user_id: 用户ID
            
        返回:
            datetime | None: 用户的签到日期，如果用户不存在或未签到则返回None
        """
        return await UserSignInfo.get_sign_in_date(user_id)

    @classmethod
    async def get_last_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户上一次签到日期
        
        参数:
            user_id: 用户ID
            
        返回:
            datetime | None: 用户的上一次签到日期，如果用户不存在或没有上一次签到记录则返回None
        """
        return await UserSignInfo.get_last_sign_in_date(user_id)

    @classmethod
    async def set_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户签到日期
        
        参数:
            user_id: 用户ID
            date: 要设置的签到日期
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_sign_in_date(user_id, date)

    @classmethod
    async def set_last_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户上一次签到日期
        
        参数:
            user_id: 用户ID
            date: 要设置的上一次签到日期
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_last_sign_in_date(user_id, date)

    @classmethod
    async def get_first_sign_in_date(cls, user_id: str) -> datetime | None:
        """
        获取用户首次签到日期
        
        参数:
            user_id: 用户ID
            
        返回:
            datetime | None: 用户的首次签到日期，如果用户不存在则返回None
        """
        return await UserSignInfo.get_first_sign_in_date(user_id)

    @classmethod
    async def set_first_sign_in_date(cls, user_id: str, date: datetime) -> bool:
        """
        设置用户首次签到日期
        
        参数:
            user_id: 用户ID
            date: 要设置的首次签到日期
            
        返回:
            bool: 设置成功返回True，失败返回False
        """
        return await UserSignInfo.set_first_sign_in_date(user_id, date)

    @classmethod
    async def sign(cls, user_id: str) -> bool:
        """
        签到
        
        参数:
            user_id: 用户ID
            
        返回:
            bool: 更新成功返回True，失败返回False
        """
        return await UserSignInfo.sign(user_id)

    @classmethod
    async def get_user_location(cls, user_id: str) -> str:
        """
        获取用户位置
        
        参数:
            user_id: 用户ID
            
        返回:
            str: 用户位置，如果用户不存在则返回默认值'北京'
        """
        return await UserIntroInfo.get_location(user_id)
