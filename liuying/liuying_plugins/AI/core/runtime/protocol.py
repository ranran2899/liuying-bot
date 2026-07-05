"""协议能力探测

通过 get_version_info 自动识别协议端（NapCat / Lagrange / LLOneBot / go-cqhttp），
按 flavor 分派扩展API；首次失败时按 (self_id, api) 缓存 unsupported，后续直接跳过。
所有API均 never-raise，返回 bool。
"""

from enum import StrEnum
import time
from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.log import logger

__all__ = ["Flavor", "ProtocolHelper"]


class Flavor(StrEnum):
    """协议端flavor枚举

    Attributes:
        NAPCAT: NapCat协议端
        LAGRANGE: Lagrange协议端
        LLONEBOT: LLOneBot协议端
        GOCQ: go-cqhttp协议端
        UNKNOWN: 未知协议端
        NONE: 协议扩展已禁用
    """

    NAPCAT = "napcat"
    LAGRANGE = "lagrange"
    LLONEBOT = "llonebot"
    GOCQ = "gocq"
    UNKNOWN = "unknown"
    NONE = "none"


_KNOWN_FLAVORS: frozenset[Flavor] = frozenset(
    {Flavor.NAPCAT, Flavor.LAGRANGE, Flavor.LLONEBOT, Flavor.GOCQ}
)
"""已支持的协议端flavor集合"""


_flavor_cache = CacheDict("AI_PROTOCOL_FLAVOR")
"""self_id -> flavor 缓存（永不过期）"""


_unsupported = CacheDict("AI_PROTOCOL_UNSUPPORTED", expire=3600)
"""self_id:api -> 标记时间戳（1小时TTL，过期自动重试）"""


class ProtocolHelper:
    """协议能力探测与扩展API调用工具类

    通过 get_version_info 自动识别协议端（NapCat / Lagrange / LLOneBot / go-cqhttp），
    按 flavor 分派扩展API；首次失败时按 (self_id, api) 缓存 unsupported，后续直接跳过。
    所有API均 never-raise，返回 bool。
    """

    @staticmethod
    def _self_id(bot: Any) -> str:
        """获取bot self_id

        参数:
            bot: Bot对象

        返回:
            str: self_id字符串
        """
        return str(getattr(bot, "self_id", "") or "")

    @staticmethod
    def _config_mode(config_value: Any) -> str:
        """解析配置的协议扩展模式

        参数:
            config_value: 配置原始值

        返回:
            str: 模式串（auto/none/具体flavor）
        """
        return str(config_value or "auto").strip().lower()

    @staticmethod
    def _is_unsupported(bot: Any, api: str) -> bool:
        """检测API是否被标记为unsupported（带TTL）

        参数:
            bot: Bot对象
            api: API名

        返回:
            bool: 是否unsupported
        """
        key = f"{ProtocolHelper._self_id(bot)}:{api}"
        return key in _unsupported

    @staticmethod
    def _mark_unsupported(bot: Any, api: str) -> None:
        """标记API为unsupported

        参数:
            bot: Bot对象
            api: API名
        """
        _unsupported.set(
            f"{ProtocolHelper._self_id(bot)}:{api}", time.time()
        )

    @staticmethod
    async def _try_api(
        bot: Any,
        api: str,
        *,
        logger_: Any = None,
        **kwargs: Any,
    ) -> bool:
        """尝试调用API，失败则标记unsupported

        参数:
            bot: Bot对象
            api: API名
            logger_: 日志器
            **kwargs: API调用参数

        返回:
            bool: 是否调用成功
        """
        if ProtocolHelper._is_unsupported(bot, api):
            return False
        try:
            await bot.call_api(api, **kwargs)
            return True
        except Exception as exc:
            ProtocolHelper._mark_unsupported(bot, api)
            if logger_ is not None:
                logger.debug(
                    f"协议扩展 {api} 调用失败，标记为不支持: {exc}",
                    command="AI",
                    e=exc,
                )
            return False

    @staticmethod
    async def detect_flavor(
        bot: Any,
        config_value: Any = "auto",
    ) -> Flavor:
        """识别协议端flavor

        优先使用配置强制指定，否则通过 get_version_info 自动识别。

        参数:
            bot: Bot对象
            config_value: 协议扩展配置值（auto/none/具体flavor）

        返回:
            Flavor: flavor枚举值
        """
        mode = ProtocolHelper._config_mode(config_value)
        match mode:
            case Flavor.NONE:
                return Flavor.NONE
            case _ if mode in _KNOWN_FLAVORS:
                return Flavor(mode)

        sid = ProtocolHelper._self_id(bot)
        cached = _flavor_cache.get(sid)
        if cached is not None:
            return Flavor(cached)

        flavor = Flavor.UNKNOWN
        try:
            info = await bot.call_api("get_version_info")
            app = str((info or {}).get("app_name", "") or "").lower()
            if "napcat" in app:
                flavor = Flavor.NAPCAT
            elif "lagrange" in app:
                flavor = Flavor.LAGRANGE
            elif "llonebot" in app:
                flavor = Flavor.LLONEBOT
            elif "go-cqhttp" in app or "gocq" in app:
                flavor = Flavor.GOCQ
        except Exception as exc:
            logger.debug(
                f"get_version_info 失败，按 unknown 处理: {exc}",
                command="AI",
                e=exc,
            )

        _flavor_cache.set(sid, flavor)
        return flavor

    @staticmethod
    async def emoji_react(
        bot: Any,
        *,
        message_id: int,
        face_id: int,
        group_id: str = "",
        config_value: Any = "auto",
    ) -> bool:
        """给消息贴表情（按flavor分派不同API）

        参数:
            bot: Bot对象
            message_id: 消息ID
            face_id: 表情ID
            group_id: 群组ID
            config_value: 协议扩展配置值

        返回:
            bool: 是否调用成功
        """
        if ProtocolHelper._config_mode(config_value) == Flavor.NONE:
            return False
        flavor = await ProtocolHelper.detect_flavor(bot, config_value)
        match flavor:
            case Flavor.NONE | Flavor.GOCQ:
                return False
            case Flavor.LAGRANGE:
                if not group_id:
                    return False
                return await ProtocolHelper._try_api(
                    bot,
                    "set_group_reaction",
                    group_id=int(group_id),
                    message_id=int(message_id),
                    code=str(int(face_id)),
                    is_add=True,
                )
            case _:
                return await ProtocolHelper._try_api(
                    bot,
                    "set_msg_emoji_like",
                    message_id=int(message_id),
                    emoji_id=int(face_id),
                    set=True,
                )

    @staticmethod
    async def poke(
        bot: Any,
        *,
        user_id: int | str,
        group_id: str = "",
        config_value: Any = "auto",
    ) -> bool:
        """戳一戳（带级联回退）

        参数:
            bot: Bot对象
            user_id: 用户ID
            group_id: 群组ID
            config_value: 协议扩展配置值

        返回:
            bool: 是否调用成功
        """
        if ProtocolHelper._config_mode(config_value) == Flavor.NONE:
            return False
        uid = int(user_id)
        if group_id:
            gid = int(group_id)
            if await ProtocolHelper._try_api(
                bot, "group_poke", group_id=gid, user_id=uid
            ):
                return True
            return await ProtocolHelper._try_api(
                bot, "send_poke", group_id=gid, user_id=uid
            )

        if await ProtocolHelper._try_api(bot, "friend_poke", user_id=uid):
            return True
        return await ProtocolHelper._try_api(bot, "send_poke", user_id=uid)

    @staticmethod
    async def set_typing(
        bot: Any,
        *,
        user_id: int | str,
        config_value: Any = "auto",
    ) -> bool:
        """设置输入状态（仅NapCat/LLOneBot系）

        参数:
            bot: Bot对象
            user_id: 用户ID
            config_value: 协议扩展配置值

        返回:
            bool: 是否调用成功
        """
        mode = ProtocolHelper._config_mode(config_value)
        if mode == Flavor.NONE:
            return False
        flavor = await ProtocolHelper.detect_flavor(bot, mode)
        if flavor not in {
            Flavor.NAPCAT,
            Flavor.LLONEBOT,
            Flavor.UNKNOWN,
        }:
            return False
        uid = int(user_id)
        return await ProtocolHelper._try_api(
            bot, "set_input_status", user_id=uid, event_type=1
        )
