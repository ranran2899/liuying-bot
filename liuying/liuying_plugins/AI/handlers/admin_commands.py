"""AI管理员命令逻辑

AI子功能运行时开关/功能体检等管理员命令的业务处理。

注意：本模块仅提供 AI 子功能管理，不重复实现流萤本体已有功能：
- ban/unban/黑名单查询: 使用 liuying.liuying_plugins.admin.ban
- 管理员等级设置: 使用 liuying.liuying_plugins.admin.bot_perm
- 插件整体开关: 使用 liuying.liuying_plugins.admin.plugin_switch
"""

from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..config import get_config
from ..core.memory import memory_manager
from ..core.runtime import (
    FEATURE_LIST,
    runtime_switch,
)
from ..models.conversation_record import ConversationRecord

__all__ = [
    "AdminCommands",
]


class AdminCommands:
    """AI管理员命令逻辑

    matcher 在插件 __init__ 统一注册，此处仅承接业务逻辑。
    """

    _ADMIN_LEVEL = 5
    """AI管理命令基础等级"""

    @staticmethod
    def _format_status_line(
        name: str, enabled: bool, source: str
    ) -> str:
        """格式化状态行

        参数:
            name: 功能名
            enabled: 是否启用
            source: 来源

        返回:
            str: 格式化文本
        """
        mark = "[ON] " if enabled else "[OFF]"
        source_tag = f" ({source})" if source != "global" else ""
        return f"{mark} {name}{source_tag}"

    @staticmethod
    def _parse_state(state: str) -> bool | None:
        """解析开关状态文本

        参数:
            state: 状态文本（on/off/开/关 等）

        返回:
            bool | None: 布尔值，无效时返回None
        """
        state = (state or "").strip().lower()
        if state in ("on", "true", "1", "开", "启用"):
            return True
        if state in ("off", "false", "0", "关", "禁用"):
            return False
        return None

    @staticmethod
    def _validate_switch_args(
        scope_id: str | None, feature: str, state: str
    ) -> str | None:
        """校验开关命令参数

        校验顺序：空作用域ID -> 状态合法性 -> 功能名合法性。

        参数:
            scope_id: 群号/用户ID，全局开关传None跳过空值校验
            feature: 功能名
            state: 状态文本

        返回:
            str | None: 错误提示文本，校验通过返回None
        """
        if scope_id is not None and not scope_id.strip():
            return "请提供群号/用户ID"
        if AdminCommands._parse_state(state) is None:
            return "状态值无效，请用 on/off"
        if (feature or "").strip().lower() not in FEATURE_LIST:
            return (
                f"未知功能: {feature}\n"
                f"可用: {', '.join(FEATURE_LIST)}"
            )
        return None

    @staticmethod
    async def handle_status(session: Uninfo) -> None:
        """查看功能开关状态"""
        if not get_config("ENABLE_AI", False):
            return

        group_id = (
            session.scene.id if session.scene.is_group else None
        )
        user_id = session.user.id
        statuses = runtime_switch.get_status(
            user_id=user_id, group_id=group_id
        )

        lines: list[str] = ["=== AI功能状态 ==="]
        for s in statuses:
            lines.append(
                AdminCommands._format_status_line(
                    s.name, s.enabled, s.source
                )
            )

        report = runtime_switch.health_check()
        lines.append("")
        lines.append(
            f"总计 {report['total_features']} 项，"
            f"启用 {report['enabled_count']} 项，"
            f"禁用 {report['disabled_count']} 项"
        )
        if report["disabled_features"]:
            lines.append(
                f"已禁用: {', '.join(report['disabled_features'])}"
            )
        lines.append(
            f"群组覆盖: {report['group_overrides_count']} 条，"
            f"用户覆盖: {report['user_overrides_count']} 条"
        )

        await MessageUtils.build_message(
            "\n".join(lines)
        ).finish()

    @staticmethod
    async def handle_switch(
        session: Uninfo, feature: str = "", state: str = ""
    ) -> None:
        """设置全局开关"""
        if not get_config("ENABLE_AI", False):
            return

        feature = (feature or "").strip().lower()
        if err := AdminCommands._validate_switch_args(
            None, feature, state
        ):
            await MessageUtils.build_message(err).finish()
            return
        enabled = AdminCommands._parse_state(state)
        ok = runtime_switch.set_global(feature, enabled)
        msg = (
            f"已设置全局开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def handle_group_switch(
        session: Uninfo,
        group_id: str = "",
        feature: str = "",
        state: str = "",
    ) -> None:
        """设置群组级开关"""
        if not get_config("ENABLE_AI", False):
            return

        group_id = (group_id or "").strip()
        feature = (feature or "").strip().lower()
        if err := AdminCommands._validate_switch_args(
            group_id, feature, state
        ):
            await MessageUtils.build_message(err).finish()
            return
        enabled = AdminCommands._parse_state(state)
        ok = runtime_switch.set_group(group_id, feature, enabled)
        msg = (
            f"已设置群 {group_id} 开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def handle_user_switch(
        session: Uninfo,
        user_id: str = "",
        feature: str = "",
        state: str = "",
    ) -> None:
        """设置用户级开关"""
        if not get_config("ENABLE_AI", False):
            return

        user_id = (user_id or "").strip()
        feature = (feature or "").strip().lower()
        if err := AdminCommands._validate_switch_args(
            user_id, feature, state
        ):
            await MessageUtils.build_message(err).finish()
            return
        enabled = AdminCommands._parse_state(state)
        ok = runtime_switch.set_user(user_id, feature, enabled)
        msg = (
            f"已设置用户 {user_id} 开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @staticmethod
    async def handle_reset(session: Uninfo) -> None:
        """重置所有运行时覆盖"""
        if not get_config("ENABLE_AI", False):
            return

        runtime_switch.reset_all()
        logger.info(
            f"管理员 {session.user.id} 重置所有AI运行时覆盖",
            command="AI",
            session=session,
        )
        await MessageUtils.build_message(
            "已重置所有群组/用户级开关覆盖"
        ).finish()

    @staticmethod
    async def handle_clear_all_memory(
        session: Uninfo,
    ) -> None:
        """全局清空所有用户的所有bot人格记忆与对话记录

        需10级及以上权限。同时清空：
        - 所有用户所有人格的对话记录（ConversationRecord）
        - 所有用户所有人格的记忆数据及搜索索引（MemoryItem）
        """
        if not get_config("ENABLE_AI", False):
            return

        # 纯ORM操作，让异常自然向上传播暴露数据库问题
        record_count = await ConversationRecord.clear_all_records()
        memory_count = await memory_manager.clear_all_memory()

        logger.warning(
            f"管理员 {session.user.id} 全局清空记忆: "
            f"records={record_count} memories={memory_count}",
            command="AI",
            session=session,
        )
        await MessageUtils.build_message(
            f"已全局清空所有记忆数据\n"
            f"- 对话记录: {record_count} 条\n"
            f"- 记忆条目: {memory_count} 条\n"
            f"（所有用户的所有bot人格数据已被清除）"
        ).finish()
