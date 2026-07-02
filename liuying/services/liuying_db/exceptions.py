"""数据库异常模块"""

from liuying.utils.exception import HookPriorityException


class DbUrlIsNone(HookPriorityException):
    """数据库链接地址为空

    属性:
        db_name: 数据库名称
        config_key: 配置键名
    """

    __slots__ = ("config_key", "db_name")

    def __init__(
        self,
        message: str = "数据库链接地址为空",
        db_name: str | None = None,
        config_key: str | None = None,
    ):
        self.db_name = db_name
        self.config_key = config_key
        details = [
            s
            for s in (
                f"数据库: {db_name}" if db_name else "",
                f"配置键: {config_key}" if config_key else "",
            )
            if s
        ]
        if details:
            message = f"{message} ({', '.join(details)})"
        super().__init__(message)


class DbConnectError(Exception):
    """数据库连接错误

    属性:
        db_name: 数据库名称
        db_url: 数据库连接地址（已脱敏）
        original_error: 原始异常
    """

    __slots__ = ("db_name", "db_url", "original_error")

    def __init__(
        self,
        message: str = "数据库连接错误",
        db_name: str | None = None,
        db_url: str | None = None,
        original_error: Exception | None = None,
    ):
        self.db_name = db_name
        self.db_url = self._mask_url(db_url) if db_url else None
        self.original_error = original_error

        details = [
            s
            for s in (
                f"数据库: {db_name}" if db_name else "",
                f"地址: {self.db_url}" if self.db_url else "",
            )
            if s
        ]
        if details:
            message = f"{message} ({', '.join(details)})"
        if original_error:
            message = f"{message} - 原因: {original_error}"
        super().__init__(message)

    @staticmethod
    def _mask_url(url: str) -> str:
        """脱敏数据库连接地址

        参数:
            url: 原始连接地址

        返回:
            str: 脱敏后的连接地址
        """
        match url.split("://", 1):
            case [protocol, rest] if "@" in rest:
                auth, host_part = rest.split("@", 1)
                user = auth.split(":", 1)[0]
                return f"{protocol}://{user}:***@{host_part}"
            case [protocol, rest]:
                return f"{protocol}://***@{rest}"
            case _:
                return "***"
