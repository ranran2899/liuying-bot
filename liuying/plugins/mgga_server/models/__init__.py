"""游戏服务器的数据持久化模型。

原实现使用插件自带的 sqlite3 连接与手写 SQL，存在连接泄漏、无法复用机器人
连接池、难以扩展等问题。此处统一改为项目的 ORM 层（``liuying_db``），并按表
拆分为独立的子模块：

* :mod:`account` —— :class:`GameAccount` 玩家账号与累计战绩（权威数据）。
* :mod:`token`   —— :class:`GameToken` 免密登录令牌。
* :mod:`record`  —— :class:`GameRecord` 单局战绩明细，便于后续做排行榜与数据分析。

密码使用 ``PBKDF2-HMAC-SHA256`` 加盐存储，计算放到线程池，避免阻塞事件循环。
"""

from .account import (
    NAME_MAX_LEN,
    NAME_MIN_LEN,
    PASSWORD_MAX_LEN,
    PASSWORD_MIN_LEN,
    GameAccount,
)
from .record import GameRecord
from .token import GameToken

__all__ = [
    "NAME_MAX_LEN",
    "NAME_MIN_LEN",
    "PASSWORD_MAX_LEN",
    "PASSWORD_MIN_LEN",
    "GameAccount",
    "GameRecord",
    "GameToken",
]
