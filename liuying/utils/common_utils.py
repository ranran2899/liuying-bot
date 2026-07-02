import re
from typing import overload

from nonebot.adapters import Bot
from nonebot_plugin_uninfo import Session, Uninfo

from liuying.configs.config import BotConfig
from liuying.models.ban_console import BanConsole
from liuying.models._bot import BotConsole
from liuying.models._group import GroupConsole
from liuying.models.task_info import TaskInfo
from liuying.utils.log import logger


class CommonUtils:
    """通用工具类"""

    @classmethod
    async def task_is_block(
        cls, session: Uninfo | Bot, module: str, group_id: str | None = None
    ) -> bool:
        """判断被动技能是否被屏蔽

        参数:
            session: 会话信息对象
            module: 被动技能模块名
            group_id: 群组id

        返回:
            bool: True表示被屏蔽(不可发送), False表示可发送
        """
        if not group_id and isinstance(session, Session):
            group_id = session.group.id if session.group else None

        if task := await TaskInfo.safe_get_or_none(module=module):
            if not task.status:
                return True

        if not await BotConsole.get_bot_status(session.self_id):
            return True

        if module in await BotConsole.get_tasks(session.self_id, False):
            return True

        if group_id:
            if await GroupConsole.is_block_task(group_id, module):
                return True
            if g := await GroupConsole.get_group(group_id=group_id):
                if g.level < 0:
                    return True
                if not g.proactive_allowed:
                    logger.debug(
                        f"群 {group_id} 已关闭主动消息, "
                        f"被动技能 {module} 被屏蔽",
                        "被动技能",
                    )
                    return True
            if await BanConsole.is_ban(None, group_id):
                return True

        return False

    @staticmethod
    def format(name: str) -> str:
        """格式化模块名称"""
        return f"<{name},"

    @overload
    @classmethod
    def convert_module_format(cls, data: str) -> list[str]: ...

    @overload
    @classmethod
    def convert_module_format(cls, data: list[str]) -> str: ...

    @classmethod
    def convert_module_format(cls, data: str | list[str]) -> str | list[str]:
        """在 `<aaa,<bbb,<ccc,` 和 `["aaa", "bbb", "ccc"]` 之间进行相互转换

        参数:
            data: 输入数据，可能是格式化字符串或字符串列表

        返回:
            str | list[str]: 根据输入类型返回转换后的数据
        """
        if isinstance(data, str):
            return [item.strip(",") for item in data.split("<") if item]
        return "".join(cls.format(item) for item in data)


class SqlUtils:
    """SQL工具类"""

    @classmethod
    def random(cls, query, limit: int = 1) -> str:
        """添加随机排序到查询中

        参数:
            query: SQLAlchemy查询对象
            limit: 限制数量

        返回:
            str: 包含随机排序的SQL字符串
        """
        db_class_name = BotConfig.get_sql_type()
        match db_class_name:
            case name if "postgres" in name or "sqlite" in name:
                return f"{query.compile()!s} ORDER BY RANDOM() LIMIT {limit};"
            case name if "mysql" in name:
                return f"{query.compile()!s} ORDER BY RAND() LIMIT {limit};"
            case _:
                logger.warning(
                    f"Unsupported database type: {db_class_name}", query.__module__
                )
                return str(query.compile())

    @classmethod
    def add_column(
        cls,
        table_name: str,
        column_name: str,
        column_type: str,
        default: str | None = None,
        not_null: bool = False,
    ) -> str:
        """生成添加列的SQL语句

        参数:
            table_name: 表名
            column_name: 列名
            column_type: 列类型
            default: 默认值
            not_null: 是否非空

        返回:
            str: SQL语句
        """
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        if default:
            sql += f" DEFAULT {default}"
        if not_null:
            sql += " NOT NULL"
        return sql


def format_usage_for_markdown(text: str) -> str:
    """智能地将Python多行字符串转换为适合Markdown渲染的格式

    - 在列表、标题等块级元素前自动插入换行
    - 将段落内的单个换行符替换为Markdown的硬换行
    - 保留两个或更多的连续换行符

    参数:
        text: 输入的多行字符串

    返回:
        str: 格式化后的Markdown字符串
    """
    if not text:
        return ""
    text = re.sub(r"([^\n])\n(\s*[-*] |\s*#+\s|\s*>)", r"\1\n\n\2", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", "  \n", text)
    return text
