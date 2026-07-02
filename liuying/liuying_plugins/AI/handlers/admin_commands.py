"""AI管理员命令

注册AI子功能运行时开关/功能体检等管理员命令。
统一通过 on_alconna + nonebot_plugin_uninfo 实现多平台支持。
权限通过 admin_check Rule 校验。

注意：本模块仅提供 AI 子功能管理，不重复实现流萤本体已有功能：
- ban/unban/黑名单查询: 使用 liuying.liuying_plugins.admin.ban
- 管理员等级设置: 使用 liuying.liuying_plugins.admin.bot_perm
- 插件整体开关: 使用 liuying.liuying_plugins.admin.plugin_switch

命令列表：
- 流萤AI状态: 查看所有AI子功能开关状态
- 流萤AI体检: 功能体检（健康检查）
- 流萤AI开关 [功能名] [on/off]: 全局AI子功能开关
- 流萤AI群开关 [群号] [功能名] [on/off]: 群组级AI子功能开关
- 流萤AI用户开关 [用户ID] [功能名] [on/off]: 用户级AI子功能开关
- 流萤AI重置: 重置所有运行时覆盖
- 全局清空记忆: 清空所有用户的所有bot人格记忆与对话记录（10级权限）

QZone相关命令已迁移到独立插件 nonebot_plugin_ai_qzone。
"""

from nonebot_plugin_alconna import (
    Alconna,
    Args,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from ..core.memory import memory_manager
from ..core.runtime import (
    FEATURE_LIST,
    runtime_switch,
)
from ..models.conversation_record import ConversationRecord

__all__ = ["setup_admin_matchers"]


_ADMIN_LEVEL = 5
"""AI管理命令基础等级"""


class AdminCommandsHelper:
    """AI管理员命令辅助工具类

    封装状态行格式化、开关状态解析等辅助方法。
    """

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


# 向后兼容别名
_format_status_line = AdminCommandsHelper._format_status_line
_parse_state = AdminCommandsHelper._parse_state


def setup_admin_matchers() -> None:
    """注册AI管理员命令matcher

    在插件启动时调用。所有命令均使用 admin_check(5) Rule 校验权限。
    """

    status_cmd = on_alconna(
        Alconna("流萤AI状态"),
        aliases={"AI状态", "流萤AI体检"},
        rule=admin_check(_ADMIN_LEVEL),
        priority=48,
        block=True,
    )

    switch_cmd = on_alconna(
        Alconna(
            "流萤AI开关",
            Args["feature", str]["state", str],
        ),
        aliases={"AI开关"},
        rule=admin_check(_ADMIN_LEVEL),
        priority=48,
        block=True,
    )

    group_switch_cmd = on_alconna(
        Alconna(
            "流萤AI群开关",
            Args["group_id", str]["feature", str]["state", str],
        ),
        aliases={"AI群开关"},
        rule=admin_check(_ADMIN_LEVEL),
        priority=48,
        block=True,
    )

    user_switch_cmd = on_alconna(
        Alconna(
            "流萤AI用户开关",
            Args["user_id", str]["feature", str]["state", str],
        ),
        aliases={"AI用户开关"},
        rule=admin_check(_ADMIN_LEVEL),
        priority=48,
        block=True,
    )

    reset_cmd = on_alconna(
        Alconna("流萤AI重置"),
        aliases={"AI重置"},
        rule=admin_check(10),
        priority=48,
        block=True,
    )

    clear_all_memory_cmd = on_alconna(
        Alconna("全局清空记忆"),
        aliases={"AI全局清空记忆", "流萤AI全局清空"},
        rule=admin_check(10),
        priority=48,
        block=True,
    )

    @status_cmd.handle()
    async def _handle_status(session: Uninfo) -> None:
        """查看功能开关状态"""
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
                _format_status_line(s.name, s.enabled, s.source)
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

    @switch_cmd.handle()
    async def _handle_switch(
        session: Uninfo, feature: str = "", state: str = ""
    ) -> None:
        """设置全局开关"""
        feature = (feature or "").strip().lower()
        enabled = _parse_state(state)
        if enabled is None:
            await MessageUtils.build_message(
                "状态值无效，请用 on/off"
            ).finish()
            return
        if feature not in FEATURE_LIST:
            await MessageUtils.build_message(
                f"未知功能: {feature}\n可用: {', '.join(FEATURE_LIST)}"
            ).finish()
            return

        ok = runtime_switch.set_global(feature, enabled)
        msg = (
            f"已设置全局开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @group_switch_cmd.handle()
    async def _handle_group_switch(
        session: Uninfo,
        group_id: str = "",
        feature: str = "",
        state: str = "",
    ) -> None:
        """设置群组级开关"""
        group_id = (group_id or "").strip()
        feature = (feature or "").strip().lower()
        enabled = _parse_state(state)

        if not group_id:
            await MessageUtils.build_message(
                "请提供群号"
            ).finish()
            return
        if enabled is None:
            await MessageUtils.build_message(
                "状态值无效，请用 on/off"
            ).finish()
            return
        if feature not in FEATURE_LIST:
            await MessageUtils.build_message(
                f"未知功能: {feature}"
            ).finish()
            return

        ok = runtime_switch.set_group(group_id, feature, enabled)
        msg = (
            f"已设置群 {group_id} 开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @user_switch_cmd.handle()
    async def _handle_user_switch(
        session: Uninfo,
        user_id: str = "",
        feature: str = "",
        state: str = "",
    ) -> None:
        """设置用户级开关"""
        user_id = (user_id or "").strip()
        feature = (feature or "").strip().lower()
        enabled = _parse_state(state)

        if not user_id:
            await MessageUtils.build_message(
                "请提供用户ID"
            ).finish()
            return
        if enabled is None:
            await MessageUtils.build_message(
                "状态值无效，请用 on/off"
            ).finish()
            return
        if feature not in FEATURE_LIST:
            await MessageUtils.build_message(
                f"未知功能: {feature}"
            ).finish()
            return

        ok = runtime_switch.set_user(user_id, feature, enabled)
        msg = (
            f"已设置用户 {user_id} 开关 {feature} = {enabled}"
            if ok
            else f"设置失败: {feature}"
        )
        await MessageUtils.build_message(msg).finish()

    @reset_cmd.handle()
    async def _handle_reset(session: Uninfo) -> None:
        """重置所有运行时覆盖"""
        runtime_switch.reset_all()
        logger.info(
            f"管理员 {session.user.id} 重置所有AI运行时覆盖",
            command="AI",
            session=session,
        )
        await MessageUtils.build_message(
            "已重置所有群组/用户级开关覆盖"
        ).finish()

    @clear_all_memory_cmd.handle()
    async def _handle_clear_all_memory(
        session: Uninfo,
    ) -> None:
        """全局清空所有用户的所有bot人格记忆与对话记录

        需10级及以上权限。同时清空：
        - 所有用户所有人格的对话记录（ConversationRecord）
        - 所有用户所有人格的记忆数据及搜索索引（MemoryItem）
        """
        err_msg = ""
        record_count = 0
        memory_count = 0
        try:
            record_count = await ConversationRecord.clear_all_records()
            memory_count = await memory_manager.clear_all_memory()
        except Exception as e:
            logger.error(
                f"全局清空记忆失败: {e}",
                command="AI",
                e=e,
                session=session,
            )
            err_msg = f"全局清空记忆失败: {e}"

        if err_msg:
            await MessageUtils.build_message(err_msg).finish()
            return

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
