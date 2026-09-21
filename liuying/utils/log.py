from datetime import timedelta
from typing import Any, overload

from loguru import logger as logger_
import nonebot
from nonebot.log import default_filter, default_format
from nonebot_plugin_uninfo import Session

from liuying.configs.path_config import LOG_PATH

driver = nonebot.get_driver()

log_level = driver.config.log_level or "INFO"

logger_.add(
    LOG_PATH / "{time:YYYY-MM-DD}.log",
    level=log_level,
    rotation="00:00",
    format=default_format,
    filter=default_filter,
    retention=timedelta(days=30),
)

logger_.add(
    LOG_PATH / "error_{time:YYYY-MM-DD}.log",
    level="ERROR",
    rotation="00:00",
    format=default_format,
    filter=default_filter,
    retention=timedelta(days=30),
)


class logger:
    """经过优化的多上下文日志记录器（基于 loguru 封装）。

    在 loguru 基础上支持自动解析会话上下文（适配器、平台、群聊、用户）、
    命令标识与异常信息，并以带颜色的结构化模板输出。

    上下文参数说明（适用于 info/warning/error/debug/trace）：
        - ``command``：触发日志的命令或功能名，输出为 CMD[xxx]
        - ``session``：用户标识或 nonebot_plugin_uninfo 的 Session 对象；
            传入 Session 时自动提取用户、适配器、群聊与平台信息
        - ``group_id``：群聊 ID，仅在 session 未提供群信息时手动传入
        - ``adapter``：适配器名称，仅在 session 未提供时手动传入
        - ``target``：任意目标对象，输出为 [Target](xxx)
        - ``platform``：平台标识，仅在 session 未提供时手动传入
        - ``e``：相关异常对象，自动追加类型与消息到日志末尾

    用法示例：
        >>> logger.info("处理完成", command="签到", session=session)
        >>> logger.error("数据库写入失败", command="economy", e=exc)
    """

    TEMPLATE_ADAPTER = "Adapter[<m>{}</m>]"
    TEMPLATE_USER = "用户[<u><e>{}</e></u>]"
    TEMPLATE_GROUP = "群聊[<u><e>{}</e></u>]"
    TEMPLATE_COMMAND = "CMD[<u><c>{}</c></u>]"
    TEMPLATE_PLATFORM = "平台[<u><m>{}</m></u>]"
    TEMPLATE_TARGET = "[Target]([<u><e>{}</e></u>])"
    SUCCESS_TEMPLATE = "[<u><c>{}</c></u>]: {} | 参数[{}] 返回: [<y>{}</y>]"

    @classmethod
    def __parser_template(
        cls,
        info: str,
        command: str | None = None,
        user_id: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
    ) -> str:
        """构建并拼接日志信息片段。

        参数:
            info: 日志正文内容。
            command: 命令或功能名，可为空。
            user_id: 用户标识，可为空。
            group_id: 群聊 ID，可为空。
            adapter: 适配器名称，可为空。
            target: 任意目标对象，可为空。
            platform: 平台标识，可为空。

        返回值:
            按固定顺序拼接后的单行日志字符串。
        """
        parts = []
        if adapter:
            parts.append(cls.TEMPLATE_ADAPTER.format(adapter))
        if platform:
            parts.append(cls.TEMPLATE_PLATFORM.format(platform))
        if group_id:
            parts.append(cls.TEMPLATE_GROUP.format(group_id))
        if user_id:
            parts.append(cls.TEMPLATE_USER.format(user_id))
        if command:
            parts.append(cls.TEMPLATE_COMMAND.format(command))
        if target:
            parts.append(cls.TEMPLATE_TARGET.format(target))
        parts.append(info)
        return " ".join(parts)

    @classmethod
    def _log(
        cls,
        level: str,
        info: str,
        command: str | None = None,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ):
        """所有日志级别共用的核心处理逻辑。

        解析 session 上下文、拼接模板后调用 loguru 输出；
        带颜色渲染失败时自动降级为纯文本。

        参数:
            level: loguru 日志级别名（info/warning/error/debug/trace）。
            info: 日志正文内容。
            command: 命令或功能名，可为空。
            session: 用户标识或 Session 对象，用于自动提取上下文。
            group_id: 群聊 ID，可为空。
            adapter: 适配器名称，可为空。
            target: 任意目标对象，可为空。
            platform: 平台标识，可为空。
            e: 需要附加记录的异常对象，可为空。
        """
        user_id: str | None = str(session) if isinstance(session, int | str) else None

        if isinstance(session, Session):
            user_id = session.user.id
            adapter = session.adapter
            if session.group:
                group_id = session.group.id
            platform = session.basic.get("scope")

        template = cls.__parser_template(
            info, command, user_id, group_id, adapter, target, platform
        )

        if e:
            template += f" || 错误 <r>{type(e).__name__}: {e}</r>"

        try:
            log_func = getattr(logger_.opt(colors=True), level)
            log_func(template)
        except Exception:
            log_func_fallback = getattr(logger_, level)
            log_func_fallback(template)

    @overload
    @classmethod
    def info(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
    ): ...
    @overload
    @classmethod
    def info(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: Session | None = None,
        target: Any = None,
        platform: str | None = None,
    ): ...

    @classmethod
    def info(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
    ):
        """记录 INFO 级别日志。

        参数:
            info: 日志正文内容。
            command: 触发日志的命令或功能名，输出为 CMD[xxx]，可为空。
            session: 用户标识或 nonebot_plugin_uninfo 的 Session 对象；
                传入 Session 时自动提取用户、适配器、群聊与平台信息，可为空。
            group_id: 群聊 ID，仅在 session 未提供群信息时手动传入，可为空。
            adapter: 适配器名称，仅在 session 未提供时手动传入，可为空。
            target: 任意目标对象，输出为 [Target](xxx)，可为空。
            platform: 平台标识，仅在 session 未提供时手动传入，可为空。
        """
        cls._log(
            "info",
            info=info,
            command=command,
            session=session,
            group_id=group_id,
            adapter=adapter,
            target=target,
            platform=platform,
        )

    @classmethod
    def success(
        cls,
        info: str,
        command: str,
        param: dict[str, Any] | None = None,
        result: str = "",
    ):
        """记录命令执行成功的结构化日志。

        与通用级别方法不同，本方法不解析 session 上下文，
        而是固定输出命令名、描述、参数键值对与返回结果。

        参数:
            info: 命令执行描述。
            command: 命令名称。
            param: 命令参数字典，逐项以 key:value 形式输出，可为空。
            result: 命令返回结果的摘要文本，默认为空。
        """
        param_str = (
            ",".join([f"<m>{k}</m>:<g>{v}</g>" for k, v in param.items()])
            if param
            else ""
        )
        logger_.opt(colors=True).success(
            cls.SUCCESS_TEMPLATE.format(command, info, param_str, result)
        )

    @overload
    @classmethod
    def warning(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...
    @overload
    @classmethod
    def warning(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: Session | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...

    @classmethod
    def warning(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ):
        """记录 WARNING 级别日志。

        参数:
            info: 日志正文内容。
            command: 触发日志的命令或功能名，输出为 CMD[xxx]，可为空。
            session: 用户标识或 Session 对象，传入 Session 时自动提取
                用户、适配器、群聊与平台信息，可为空。
            group_id: 群聊 ID，仅在 session 未提供群信息时手动传入，可为空。
            adapter: 适配器名称，仅在 session 未提供时手动传入，可为空。
            target: 任意目标对象，输出为 [Target](xxx)，可为空。
            platform: 平台标识，仅在 session 未提供时手动传入，可为空。
            e: 相关异常对象，自动追加类型与消息到日志末尾，可为空。
        """
        cls._log(
            "warning",
            info=info,
            command=command,
            session=session,
            group_id=group_id,
            adapter=adapter,
            target=target,
            platform=platform,
            e=e,
        )

    @overload
    @classmethod
    def error(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...
    @overload
    @classmethod
    def error(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: Session | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...

    @classmethod
    def error(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ):
        """记录 ERROR 级别日志（同时写入独立错误日志文件）。

        参数:
            info: 日志正文内容。
            command: 触发日志的命令或功能名，输出为 CMD[xxx]，可为空。
            session: 用户标识或 Session 对象，传入 Session 时自动提取
                用户、适配器、群聊与平台信息，可为空。
            group_id: 群聊 ID，仅在 session 未提供群信息时手动传入，可为空。
            adapter: 适配器名称，仅在 session 未提供时手动传入，可为空。
            target: 任意目标对象，输出为 [Target](xxx)，可为空。
            platform: 平台标识，仅在 session 未提供时手动传入，可为空。
            e: 相关异常对象，自动追加类型与消息到日志末尾，可为空。
        """
        cls._log(
            "error",
            info=info,
            command=command,
            session=session,
            group_id=group_id,
            adapter=adapter,
            target=target,
            platform=platform,
            e=e,
        )

    @overload
    @classmethod
    def debug(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...
    @overload
    @classmethod
    def debug(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: Session | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...

    @classmethod
    def debug(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ):
        """记录 DEBUG 级别日志。

        参数:
            info: 日志正文内容。
            command: 触发日志的命令或功能名，输出为 CMD[xxx]，可为空。
            session: 用户标识或 Session 对象，传入 Session 时自动提取
                用户、适配器、群聊与平台信息，可为空。
            group_id: 群聊 ID，仅在 session 未提供群信息时手动传入，可为空。
            adapter: 适配器名称，仅在 session 未提供时手动传入，可为空。
            target: 任意目标对象，输出为 [Target](xxx)，可为空。
            platform: 平台标识，仅在 session 未提供时手动传入，可为空。
            e: 相关异常对象，自动追加类型与消息到日志末尾，可为空。
        """
        cls._log(
            "debug",
            info=info,
            command=command,
            session=session,
            group_id=group_id,
            adapter=adapter,
            target=target,
            platform=platform,
            e=e,
        )

    @overload
    @classmethod
    def trace(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...
    @overload
    @classmethod
    def trace(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: Session | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ): ...

    @classmethod
    def trace(
        cls,
        info: str,
        command: str | None = None,
        *,
        session: int | str | Session | None = None,
        group_id: int | str | None = None,
        adapter: str | None = None,
        target: Any = None,
        platform: str | None = None,
        e: Exception | None = None,
    ):
        """记录 TRACE 级别日志。

        参数:
            info: 日志正文内容。
            command: 触发日志的命令或功能名，输出为 CMD[xxx]，可为空。
            session: 用户标识或 Session 对象，传入 Session 时自动提取
                用户、适配器、群聊与平台信息，可为空。
            group_id: 群聊 ID，仅在 session 未提供群信息时手动传入，可为空。
            adapter: 适配器名称，仅在 session 未提供时手动传入，可为空。
            target: 任意目标对象，输出为 [Target](xxx)，可为空。
            platform: 平台标识，仅在 session 未提供时手动传入，可为空。
            e: 相关异常对象，自动追加类型与消息到日志末尾，可为空。
        """
        cls._log(
            "trace",
            info=info,
            command=command,
            session=session,
            group_id=group_id,
            adapter=adapter,
            target=target,
            platform=platform,
            e=e,
        )
