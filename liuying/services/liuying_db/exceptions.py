"""数据库异常模块"""

from liuying.utils.exception import HookPriorityException


class DbUrlIsNone(HookPriorityException):
    """数据库链接地址为空"""


class DbConnectError(Exception):
    """数据库连接错误"""
