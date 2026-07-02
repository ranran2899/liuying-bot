"""用户工具，保留向后兼容
    - UserCurr: 用户货币工具类
    - UserExp: 用户经验工具类
    - UserFavor: 用户好感度工具类
    - UserGold: 用户金币工具类
    - UserMedia: 用户媒体工具类
    - UserSign: 用户签到工具类
    - UserUid: 用户唯一标识工具类
"""

from .curr import UserCurrUtils as UserCurr
from .exp import UserExp
from .favor import UserFavor
from .gold import UserGold
from .media import UserMedia
from .sign import UserSign
from .uuid import UserUid

__all__ = [
    "UserCurr",
    "UserExp",
    "UserFavor",
    "UserGold",
    "UserMedia",
    "UserSign",
    "UserUid",
]
