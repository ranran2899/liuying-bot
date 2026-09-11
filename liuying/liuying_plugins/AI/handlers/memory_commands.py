"""记忆命令逻辑

查看记忆摘要、清空对话历史、清空记忆的业务处理。
"""

from nonebot_plugin_uninfo import Uninfo

from liuying.utils.message import MessageUtils

from ..agent.warmup_persona import persona_manager
from ..config import get_config
from ..core.memory import memory_manager
from ..models.conversation_record import ConversationRecord

__all__ = [
    "MemoryCommands",
]


class MemoryCommands:
    """记忆命令逻辑

    matcher 在插件 __init__ 统一注册，此处仅承接业务逻辑。
    """

    @staticmethod
    async def _resolve_scene(
        session: Uninfo,
    ) -> tuple[str, str | None, str]:
        """解析会话场景三元组

        参数:
            session: 会话信息

        返回:
            tuple[str, str | None, str]:
                (user_id, group_id, persona_name)，
                group_id 群聊为场景ID、私聊为None；
                persona_name 为用户当前激活人格
        """
        user_id = session.user.id
        group_id = session.scene.id if session.scene.is_group else None
        # get_user_persona_name 内部已捕获异常并回退默认人格
        persona_name = await persona_manager.get_user_persona_name(
            user_id
        )
        return user_id, group_id, persona_name

    @staticmethod
    async def handle_memory(session: Uninfo) -> None:
        """查看记忆摘要

        仅展示当前用户当前人格的记忆，确保人设间数据隔离。
        """
        if not get_config("ENABLE_AI", False):
            return

        user_id, group_id, persona_name = (
            await MemoryCommands._resolve_scene(session)
        )
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

    @staticmethod
    async def handle_clear(session: Uninfo) -> None:
        """清空对话历史

        仅清空当前用户当前人格的对话记录。
        """
        if not get_config("ENABLE_AI", False):
            return

        user_id, group_id, persona_name = (
            await MemoryCommands._resolve_scene(session)
        )
        count = await ConversationRecord.clear_history(
            user_id, group_id, persona_name=persona_name
        )
        await MessageUtils.build_message(
            f"已清空 {count} 条对话记录（人格: {persona_name}）"
        ).finish()

    @staticmethod
    async def handle_clear_memory(session: Uninfo) -> None:
        """清空记忆

        清除当前用户当前bot人格的所有记忆数据（含搜索索引）。
        """
        if not get_config("ENABLE_AI", False):
            return

        user_id, group_id, persona_name = (
            await MemoryCommands._resolve_scene(session)
        )
        # 纯ORM操作，让异常自然向上传播暴露数据库问题
        count = await memory_manager.clear_user_memory(
            user_id, persona_name=persona_name, group_id=group_id
        )
        await MessageUtils.build_message(
            f"已清空 {count} 条记忆（人格: {persona_name}）"
        ).finish()
