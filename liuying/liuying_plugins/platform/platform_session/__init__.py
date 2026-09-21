"""统一平台会话插件

多平台的会话信息(用户、群组、频道)统一获取，
在处理函数参数中注入 Uninfo 即可拿到跨平台一致的会话对象。
"""

from nonebot.plugin import PluginMetadata

from liuying.configs.utils.models import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType

from .config import get_cache_conf as get_cache_conf
from .constraint import SupportAdapter as SupportAdapter
from .constraint import SupportScope as SupportScope
from .loader import BaseLoader as BaseLoader
from .model import Member as Member
from .model import MuteInfo as MuteInfo
from .model import Role as Role
from .model import Scene as Scene
from .model import SceneType as SceneType
from .model import Session as Session
from .model import User as User
from .params import Interface as Interface
from .params import QryItrface as QryItrface
from .params import QueryInterface as QueryInterface
from .params import Uninfo as Uninfo
from .params import UniSession as UniSession
from .params import get_interface as get_interface
from .params import get_session as get_session
from .permission import ADMIN as ADMIN
from .permission import GROUP as GROUP
from .permission import GUILD as GUILD
from .permission import MEMBER as MEMBER
from .permission import OWNER as OWNER
from .permission import PRIVATE as PRIVATE
from .permission import ROLE_IN as ROLE_IN
from .permission import ROLE_LEVEL as ROLE_LEVEL
from .permission import ROLE_NOT_IN as ROLE_NOT_IN
from .permission import SCENE_IN as SCENE_IN
from .permission import SCENE_NOT_IN as SCENE_NOT_IN
from .permission import USER_IN as USER_IN
from .permission import USER_NOT_IN as USER_NOT_IN

__plugin_meta__ = PluginMetadata(
    name="统一平台会话",
    description="多平台的会话信息(用户、群组、频道)统一获取",
    usage="在处理函数参数中注入 Uninfo 即可获取统一会话对象",
    type="library",
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        plugin_type=PluginType.HIDDEN,
        configs=[
            RegisterConfig(
                module="platform_session",
                key="CACHE",
                value=True,
                default_value=True,
                help="是否启用会话信息缓存",
                type=bool,
            ),
            RegisterConfig(
                module="platform_session",
                key="CACHE_EXPIRE",
                value=300,
                default_value=300,
                help="会话信息缓存过期时间(秒)",
                type=int,
            ),
        ],
    ).to_dict(),
)
