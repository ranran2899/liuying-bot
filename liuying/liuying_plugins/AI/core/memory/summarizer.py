"""记忆摘要服务

提供会话级与每日级记忆摘要：将窗口内对话摘要成简洁记忆，
按天聚合对话与记忆生成每日摘要，支持 LLM 调用生成。
"""

from datetime import datetime, time

from liuying.utils.log import logger

from ...models.conversation_record import ConversationRecord
from ..llm import llm_helper
from .manager import memory_manager

_SESSION_SUMMARY_PROMPT = """请将以下对话记录摘要成一段简洁的记忆。

用户ID：{user_id}
对话记录：
{history}

要求：
1. 提取关键信息、事件和用户偏好
2. 保留重要细节（人名/地名/时间）
3. 不超过150字
4. 只返回摘要文本"""

_DAILY_SUMMARY_PROMPT = """请将以下一天内的对话聚合为每日摘要。

用户ID：{user_id}
日期：{date}
当日内容：
{content}

要求：
1. 按主题归纳当日重要事件与互动
2. 突出用户情绪、偏好与需求
3. 不超过200字
4. 只返回摘要文本"""

_MAX_HISTORY_RECORDS = 20
"""会话摘要最大记录数"""

_MAX_CONTENT_LENGTH = 2000
"""每日摘要输入内容最大长度"""

_MAX_STORE_LENGTH = 500
"""写入记忆的原始内容最大长度"""


class MemorySummarizer:
    """记忆摘要器

    生成会话级摘要（窗口内对话摘要成简洁记忆）与
    每日摘要（按天聚合对话生成当日摘要并写入记忆系统）。
    """

    async def summarize_session(
        self,
        user_id: str,
        records: list[ConversationRecord],
    ) -> str:
        """会话摘要

        将窗口内的对话记录摘要成简洁记忆。

        参数:
            user_id: 用户ID
            records: 对话记录列表

        返回:
            str: 摘要文本，无记录或失败时返回空串
        """
        if not records:
            return ""
        history = "\n".join(
            f"{r.role}: {r.content}"
            for r in records[-_MAX_HISTORY_RECORDS:]
        )
        prompt = _SESSION_SUMMARY_PROMPT.format(
            user_id=user_id, history=history
        )
        try:
            return await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
        except Exception as e:
            logger.warning(
                f"会话摘要生成失败: {e}", command="AI", e=e
            )
            return ""

    async def summarize_daily(self, user_id: str, date: str) -> str:
        """每日摘要

        按天聚合对话记录生成当日摘要，并写入记忆系统。

        参数:
            user_id: 用户ID
            date: 日期字符串，格式 YYYY-MM-DD

        返回:
            str: 每日摘要文本，无内容或失败时返回空串
        """
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(
                f"日期格式错误，需YYYY-MM-DD: {date}",
                command="AI",
            )
            return ""
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        records = await ConversationRecord.filter(
            user_id=user_id,
            create_time__gte=start,
            create_time__lte=end,
        ).order_by("create_time").all()
        if not records:
            return ""
        content = "\n".join(f"{r.role}: {r.content}" for r in records)
        prompt = _DAILY_SUMMARY_PROMPT.format(
            user_id=user_id,
            date=date,
            content=content[:_MAX_CONTENT_LENGTH],
        )
        try:
            summary = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
            await memory_manager.add(
                user_id=user_id,
                content=content[:_MAX_STORE_LENGTH],
                summary=summary,
                tier="semantic",
                salience=0.8,
                topic_tags=["daily_summary"],
            )
            logger.info(
                f"每日摘要生成完成: {user_id} {date}",
                command="AI",
            )
            return summary
        except Exception as e:
            logger.warning(
                f"每日摘要生成失败: {e}", command="AI", e=e
            )
            return ""


memory_summarizer = MemorySummarizer()
"""记忆摘要器单例"""
