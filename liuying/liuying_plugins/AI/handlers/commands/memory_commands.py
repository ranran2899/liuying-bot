"""记忆命令处理

注册查看记忆摘要、清空对话历史、清空记忆等命令。
"""

from nonebot_plugin_alconna import (
    Alconna,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ...core.memory import memory_manager
from ...core.persona import persona_manager
from ...models.conversation_record import ConversationRecord

__all__ = ["setup_memory_commands"]


def setup_memory_commands() -> None:
    """注册记忆相关matcher

    - bot记忆: 查看当前用户当前人格的记忆摘要
    - 清空对话历史: 清空当前用户当前人格的对话记录
    - 清空记忆: 清空当前用户当前bot人格的所有记忆数据
    """
    memory_cmd = on_alconna(
        Alconna("bot记忆"),
        aliases={"AI记忆"},
        priority=49,
        block=True,
    )

    clear_cmd = on_alconna(
        Alconna("清空对话历史"),
        aliases={"bot清空对话", "清除对话"},
        priority=49,
        block=True,
    )

    clear_memory_cmd = on_alconna(
        Alconna("清空记忆"),
        aliases={"bot清空记忆", "清除记忆"},
        priority=49,
        block=True,
    )

    @memory_cmd.handle()
    async def _handle_memory(session: Uninfo) -> None:
        """查看记忆摘要

        仅展示当前用户当前人格的记忆，确保人设间数据隔离。
        """
        user_id = session.user.id
        group_id = (
            session.scene.id if session.scene.is_group else None
        )
        try:
            persona_name = await persona_manager.get_user_persona_name(
                user_id
            )
        except Exception:
            persona_name = persona_manager.get_active_persona_name()
        memories = await memory_manager.get_memory_summary(
            user_id, group_id, limit=10, persona_name=persona_name
        )
        if not memories:
            await MessageUtils.build_message("还没有相关记忆~").finish()
            return

        lines = [f"相关记忆（人格: {persona_name}）:"]
        for mem in memories:
            lines.append(f"- [{mem['tier']}] {mem['summary']}")
        await MessageUtils.build_message(
            "\n".join(lines)
        ).finish()

    @clear_cmd.handle()
    async def _handle_clear(session: Uninfo) -> None:
        """清空对话历史

        仅清空当前用户当前人格的对话记录。
        """
        user_id = session.user.id
        group_id = (
            session.scene.id if session.scene.is_group else None
        )
        try:
            persona_name = await persona_manager.get_user_persona_name(
                user_id
            )
        except Exception:
            persona_name = persona_manager.get_active_persona_name()
        count = await ConversationRecord.clear_history(
            user_id, group_id, persona_name=persona_name
        )
        await MessageUtils.build_message(
            f"已清空 {count} 条对话记录（人格: {persona_name}）"
        ).finish()

    @clear_memory_cmd.handle()
    async def _handle_clear_memory(session: Uninfo) -> None:
        """清空记忆

        清除当前用户当前bot人格的所有记忆数据（含搜索索引）。
        """
        user_id = session.user.id
        group_id = (
            session.scene.id if session.scene.is_group else None
        )
        try:
            persona_name = await persona_manager.get_user_persona_name(
                user_id
            )
        except Exception:
            persona_name = persona_manager.get_active_persona_name()

        err_msg = ""
        count = 0
        try:
            count = await memory_manager.clear_user_memory(
                user_id, persona_name=persona_name, group_id=group_id
            )
        except Exception as e:
            logger.warning(
                f"清空记忆失败: {e}", command="AI", e=e
            )
            err_msg = f"清空记忆失败: {e}"

        if err_msg:
            await MessageUtils.build_message(err_msg).finish()
            return

        await MessageUtils.build_message(
            f"已清空 {count} 条记忆（人格: {persona_name}）"
        ).finish()
